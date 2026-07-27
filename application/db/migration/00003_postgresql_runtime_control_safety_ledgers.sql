-- +goose Up
SET ROLE agent_migrator;

-- +goose StatementBegin
CREATE FUNCTION agent.valid_child_admission_reason_codes(
    outcome_value varchar,
    reason_codes_value varchar[]
) RETURNS boolean
LANGUAGE sql
IMMUTABLE
STRICT
PARALLEL SAFE
AS $valid_child_admission_reason_codes$
    SELECT cardinality(reason_codes_value) BETWEEN 1 AND 16
       AND cardinality(reason_codes_value) = (
           SELECT count(DISTINCT reason_code) FROM unnest(reason_codes_value) AS reason_code
       )
       AND reason_codes_value <@ ARRAY[
           'admitted', 'work_order_not_active', 'depth_limit', 'run_count_limit',
           'parallel_limit', 'budget_unavailable', 'policy_denied',
           'capability_unavailable', 'provider_unavailable', 'sandbox_unavailable',
           'workspace_conflict'
       ]::varchar[]
       AND (
           (outcome_value = 'accepted' AND reason_codes_value = ARRAY['admitted']::varchar[])
           OR (outcome_value = 'rejected' AND NOT reason_codes_value @> ARRAY['admitted']::varchar[])
       );
$valid_child_admission_reason_codes$;
-- +goose StatementEnd

ALTER FUNCTION agent.valid_child_admission_reason_codes(varchar, varchar[])
    OWNER TO agent_migrator;
REVOKE ALL ON FUNCTION agent.valid_child_admission_reason_codes(varchar, varchar[]) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION agent.valid_child_admission_reason_codes(varchar, varchar[]) TO agent_app;

-- +goose StatementBegin
CREATE FUNCTION agent.child_admission_reason_codes_key(reason_codes_value varchar[])
RETURNS varchar
LANGUAGE sql
IMMUTABLE
STRICT
PARALLEL SAFE
AS $child_admission_reason_codes_key$
    SELECT array_to_string(reason_codes_value, chr(31));
$child_admission_reason_codes_key$;
-- +goose StatementEnd

ALTER FUNCTION agent.child_admission_reason_codes_key(varchar[]) OWNER TO agent_migrator;
REVOKE ALL ON FUNCTION agent.child_admission_reason_codes_key(varchar[]) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION agent.child_admission_reason_codes_key(varchar[]) TO agent_app;

-- +goose StatementBegin
CREATE FUNCTION agent.enforce_work_order_control_update() RETURNS trigger
LANGUAGE plpgsql
AS $enforce_work_order_control_update$
BEGIN
    IF NEW.child_admission_open
       OR NEW.active_work_version <> OLD.active_work_version + 1
       OR NEW.updated_at < OLD.updated_at THEN
        RAISE EXCEPTION USING ERRCODE = '23514',
            MESSAGE = 'WorkOrder control update must only close admission and advance one version';
    END IF;
    RETURN NEW;
END
$enforce_work_order_control_update$;
-- +goose StatementEnd

-- +goose StatementBegin
CREATE FUNCTION agent.enforce_runtime_command_cursor_update() RETURNS trigger
LANGUAGE plpgsql
AS $enforce_runtime_command_cursor_update$
BEGIN
    IF NEW.last_command_sequence <> OLD.last_command_sequence + 1
       OR NEW.current_fencing_token <= OLD.current_fencing_token
       OR NEW.updated_at < OLD.updated_at THEN
        RAISE EXCEPTION USING ERRCODE = '23514',
            MESSAGE = 'Runtime command cursor must be contiguous with increasing fencing';
    END IF;
    RETURN NEW;
END
$enforce_runtime_command_cursor_update$;
-- +goose StatementEnd

-- +goose StatementBegin
CREATE FUNCTION agent.enforce_invocation_attempt_cursor_update() RETURNS trigger
LANGUAGE plpgsql
AS $enforce_invocation_attempt_cursor_update$
BEGIN
    IF NEW.last_attempt_number <> OLD.last_attempt_number + 1
       OR NEW.current_fencing_token <= OLD.current_fencing_token
       OR NEW.updated_at < OLD.updated_at THEN
        RAISE EXCEPTION USING ERRCODE = '23514',
            MESSAGE = 'Invocation Attempt cursor must be contiguous with increasing fencing';
    END IF;
    RETURN NEW;
END
$enforce_invocation_attempt_cursor_update$;
-- +goose StatementEnd

-- +goose StatementBegin
CREATE FUNCTION agent.enforce_open_work_order_admission() RETURNS trigger
LANGUAGE plpgsql
AS $enforce_open_work_order_admission$
DECLARE
    admission_open boolean;
BEGIN
    IF TG_TABLE_NAME = 'child_agent_run_admission_decisions'
       AND to_jsonb(NEW)->>'outcome' = 'rejected' THEN
        RETURN NEW;
    END IF;

    SELECT child_admission_open
    INTO admission_open
    FROM agent.work_orders
    WHERE tenant_id = NEW.tenant_id
      AND work_order_id = NEW.work_order_id
    FOR UPDATE;

    IF admission_open IS DISTINCT FROM true THEN
        RAISE EXCEPTION USING ERRCODE = '23514',
            MESSAGE = 'AgentRun and accepted Child Admission facts require an open WorkOrder admission window';
    END IF;
    RETURN NEW;
END
$enforce_open_work_order_admission$;
-- +goose StatementEnd

-- +goose StatementBegin
CREATE FUNCTION agent.enforce_fanout_version_update() RETURNS trigger
LANGUAGE plpgsql
AS $enforce_fanout_version_update$
BEGIN
    IF NEW.latest_version <> OLD.latest_version + 1
       OR NEW.latest_digest = OLD.latest_digest
       OR NEW.updated_at <= OLD.updated_at THEN
        RAISE EXCEPTION USING ERRCODE = '23514',
            MESSAGE = 'Fanout version cursor must be contiguous and monotonic';
    END IF;
    RETURN NEW;
END
$enforce_fanout_version_update$;
-- +goose StatementEnd

-- +goose StatementBegin
CREATE FUNCTION agent.enforce_fanout_target_update() RETURNS trigger
LANGUAGE plpgsql
AS $enforce_fanout_target_update$
DECLARE
    state_progress_valid boolean;
BEGIN
    state_progress_valid := NEW.control_state = OLD.control_state
        OR (OLD.control_state = 'pending' AND NEW.control_state IN (
            'dispatched', 'confirmed', 'terminal_before_control', 'outcome_unknown'
        ))
        OR (OLD.control_state = 'dispatched' AND NEW.control_state IN (
            'confirmed', 'terminal_before_control', 'outcome_unknown'
        ))
        OR (OLD.control_state = 'outcome_unknown' AND NEW.control_state IN (
            'confirmed', 'terminal_before_control'
        ));
    IF NOT state_progress_valid
       OR NEW.claim_fencing_token < OLD.claim_fencing_token
       OR NEW.claim_fencing_token > OLD.claim_fencing_token + 1
       OR NEW.updated_at <= OLD.updated_at THEN
        RAISE EXCEPTION USING ERRCODE = '23514',
            MESSAGE = 'Fanout target progress, lease fencing, and time must be monotonic';
    END IF;
    IF NEW.claim_fencing_token = OLD.claim_fencing_token + 1
       AND (NEW.claim_worker_id IS NULL OR NEW.claim_expires_at IS NULL) THEN
        RAISE EXCEPTION USING ERRCODE = '23514',
            MESSAGE = 'A new Fanout target lease requires an owner and expiry';
    END IF;
    IF NEW.claim_fencing_token = OLD.claim_fencing_token
       AND OLD.claim_worker_id IS NOT NULL
       AND NEW.claim_worker_id IS NOT NULL
       AND NEW.claim_worker_id <> OLD.claim_worker_id THEN
        RAISE EXCEPTION USING ERRCODE = '23514',
            MESSAGE = 'A Fanout target lease owner cannot change without new fencing';
    END IF;
    IF NEW.control_state <> OLD.control_state
       AND (NEW.claim_worker_id IS NOT NULL OR NEW.claim_expires_at IS NOT NULL) THEN
        RAISE EXCEPTION USING ERRCODE = '23514',
            MESSAGE = 'Fanout target progress must release its lease';
    END IF;
    RETURN NEW;
END
$enforce_fanout_target_update$;
-- +goose StatementEnd

ALTER FUNCTION agent.enforce_work_order_control_update() OWNER TO agent_migrator;
ALTER FUNCTION agent.enforce_runtime_command_cursor_update() OWNER TO agent_migrator;
ALTER FUNCTION agent.enforce_invocation_attempt_cursor_update() OWNER TO agent_migrator;
ALTER FUNCTION agent.enforce_open_work_order_admission() OWNER TO agent_migrator;
ALTER FUNCTION agent.enforce_fanout_version_update() OWNER TO agent_migrator;
ALTER FUNCTION agent.enforce_fanout_target_update() OWNER TO agent_migrator;
REVOKE ALL ON FUNCTION agent.enforce_work_order_control_update() FROM PUBLIC;
REVOKE ALL ON FUNCTION agent.enforce_runtime_command_cursor_update() FROM PUBLIC;
REVOKE ALL ON FUNCTION agent.enforce_invocation_attempt_cursor_update() FROM PUBLIC;
REVOKE ALL ON FUNCTION agent.enforce_open_work_order_admission() FROM PUBLIC;
REVOKE ALL ON FUNCTION agent.enforce_fanout_version_update() FROM PUBLIC;
REVOKE ALL ON FUNCTION agent.enforce_fanout_target_update() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION agent.enforce_work_order_control_update() TO agent_app;
GRANT EXECUTE ON FUNCTION agent.enforce_runtime_command_cursor_update() TO agent_app;
GRANT EXECUTE ON FUNCTION agent.enforce_invocation_attempt_cursor_update() TO agent_app;
GRANT EXECUTE ON FUNCTION agent.enforce_open_work_order_admission() TO agent_app;
GRANT EXECUTE ON FUNCTION agent.enforce_fanout_version_update() TO agent_app;
GRANT EXECUTE ON FUNCTION agent.enforce_fanout_target_update() TO agent_app;

-- This expand-only migration establishes the narrow authoritative execution and
-- authority facts required by B02.3, followed by append-only control ledgers.
-- It rewrites no existing row. Application mutations remain Tenant-scoped and
-- column-granted; immutable facts expose no UPDATE or DELETE privilege.
CREATE TABLE agent.work_orders (
    tenant_id varchar(200) NOT NULL,
    work_order_id varchar(200) NOT NULL,
    state varchar(32) NOT NULL,
    active_work_version bigint NOT NULL,
    child_admission_open boolean NOT NULL,
    work_sequence bigint NOT NULL DEFAULT 0,
    created_at timestamptz NOT NULL,
    updated_at timestamptz NOT NULL,
    CONSTRAINT work_orders_pk PRIMARY KEY (tenant_id, work_order_id),
    CONSTRAINT work_orders_identity_uk UNIQUE (work_order_id),
    CONSTRAINT work_orders_tenant_fk FOREIGN KEY (tenant_id)
        REFERENCES agent.tenants (tenant_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT work_orders_ids_not_blank CHECK (tenant_id <> '' AND work_order_id <> ''),
    CONSTRAINT work_orders_state CHECK (state IN (
        'accepted', 'queued', 'running', 'waiting', 'paused', 'cancel_requested',
        'cancelling', 'completed', 'partial', 'failed', 'cancelled'
    )),
    CONSTRAINT work_orders_versions CHECK (active_work_version >= 1 AND work_sequence >= 0),
    CONSTRAINT work_orders_terminal_admission CHECK (
        state NOT IN ('completed', 'partial', 'failed', 'cancelled') OR NOT child_admission_open
    ),
    CONSTRAINT work_orders_timestamps CHECK (updated_at >= created_at)
);

CREATE TABLE agent.agent_runs (
    tenant_id varchar(200) NOT NULL,
    work_order_id varchar(200) NOT NULL,
    agent_run_id varchar(200) NOT NULL,
    run_kind varchar(16) NOT NULL,
    required_for_work_order_completion boolean NOT NULL,
    state varchar(32) NOT NULL,
    created_at timestamptz NOT NULL,
    updated_at timestamptz NOT NULL,
    CONSTRAINT agent_runs_pk PRIMARY KEY (tenant_id, agent_run_id),
    CONSTRAINT agent_runs_identity_uk UNIQUE (agent_run_id),
    CONSTRAINT agent_runs_work_order_fk FOREIGN KEY (tenant_id, work_order_id)
        REFERENCES agent.work_orders (tenant_id, work_order_id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT agent_runs_ids_not_blank CHECK (
        tenant_id <> '' AND work_order_id <> '' AND agent_run_id <> ''
    ),
    CONSTRAINT agent_runs_kind CHECK (run_kind IN ('root', 'child')),
    CONSTRAINT agent_runs_state CHECK (state IN (
        'accepted', 'running', 'waiting_input', 'waiting_approval', 'paused',
        'cancel_requested', 'outcome_unknown', 'succeeded', 'failed', 'cancelled'
    )),
    CONSTRAINT agent_runs_timestamps CHECK (updated_at >= created_at),
    CONSTRAINT agent_runs_work_order_identity_uk UNIQUE (tenant_id, work_order_id, agent_run_id)
);

CREATE INDEX agent_runs_active_work_order_idx
    ON agent.agent_runs (tenant_id, work_order_id, agent_run_id)
    WHERE state NOT IN ('succeeded', 'failed', 'cancelled');

CREATE TABLE agent.agent_runtime_runs (
    tenant_id varchar(200) NOT NULL,
    work_order_id varchar(200) NOT NULL,
    agent_run_id varchar(200) NOT NULL,
    runtime_run_id varchar(200) NOT NULL,
    state varchar(32) NOT NULL,
    last_command_sequence bigint NOT NULL DEFAULT 0,
    current_fencing_token bigint NOT NULL DEFAULT 0,
    created_at timestamptz NOT NULL,
    updated_at timestamptz NOT NULL,
    completed_at timestamptz,
    CONSTRAINT agent_runtime_runs_pk PRIMARY KEY (tenant_id, runtime_run_id),
    CONSTRAINT agent_runtime_runs_identity_uk UNIQUE (runtime_run_id),
    CONSTRAINT agent_runtime_runs_agent_fk FOREIGN KEY (tenant_id, work_order_id, agent_run_id)
        REFERENCES agent.agent_runs (tenant_id, work_order_id, agent_run_id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT agent_runtime_runs_agent_uk UNIQUE (tenant_id, agent_run_id),
    CONSTRAINT agent_runtime_runs_scope_uk UNIQUE (
        tenant_id, work_order_id, agent_run_id, runtime_run_id
    ),
    CONSTRAINT agent_runtime_runs_work_order_scope_uk UNIQUE (
        tenant_id, work_order_id, runtime_run_id
    ),
    CONSTRAINT agent_runtime_runs_ids_not_blank CHECK (
        tenant_id <> '' AND work_order_id <> '' AND agent_run_id <> '' AND runtime_run_id <> ''
    ),
    CONSTRAINT agent_runtime_runs_state CHECK (state IN (
        'accepted', 'running', 'waiting_input', 'waiting_approval', 'paused',
        'cancel_requested', 'outcome_unknown', 'succeeded', 'failed', 'cancelled'
    )),
    CONSTRAINT agent_runtime_runs_cursors CHECK (
        last_command_sequence >= 0 AND current_fencing_token >= 0
    ),
    CONSTRAINT agent_runtime_runs_terminal_time CHECK (
        (state IN ('succeeded', 'failed', 'cancelled')) = (completed_at IS NOT NULL)
    ),
    CONSTRAINT agent_runtime_runs_timestamps CHECK (
        updated_at >= created_at AND (completed_at IS NULL OR completed_at >= created_at)
    )
);

CREATE INDEX agent_runtime_runs_active_work_order_idx
    ON agent.agent_runtime_runs (tenant_id, work_order_id, runtime_run_id)
    WHERE state NOT IN ('succeeded', 'failed', 'cancelled');

CREATE TABLE agent.runtime_invocations (
    tenant_id varchar(200) NOT NULL,
    work_order_id varchar(200) NOT NULL,
    runtime_run_id varchar(200) NOT NULL,
    invocation_id varchar(200) NOT NULL,
    request_digest varchar(71) NOT NULL,
    last_attempt_number bigint NOT NULL DEFAULT 0,
    current_fencing_token bigint NOT NULL DEFAULT 0,
    created_at timestamptz NOT NULL,
    updated_at timestamptz NOT NULL,
    CONSTRAINT runtime_invocations_pk PRIMARY KEY (tenant_id, invocation_id),
    CONSTRAINT runtime_invocations_identity_uk UNIQUE (invocation_id),
    CONSTRAINT runtime_invocations_runtime_fk FOREIGN KEY (
        tenant_id, work_order_id, runtime_run_id
    ) REFERENCES agent.agent_runtime_runs (
        tenant_id, work_order_id, runtime_run_id
    )
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT runtime_invocations_scope_uk UNIQUE (
        tenant_id, work_order_id, runtime_run_id, invocation_id
    ),
    CONSTRAINT runtime_invocations_command_digest_uk UNIQUE (
        tenant_id, work_order_id, runtime_run_id, invocation_id, request_digest
    ),
    CONSTRAINT runtime_invocations_ids_not_blank CHECK (
        tenant_id <> '' AND work_order_id <> '' AND runtime_run_id <> '' AND invocation_id <> ''
    ),
    CONSTRAINT runtime_invocations_digest CHECK (
        request_digest COLLATE "C" ~ '^sha256:[0-9a-f]{64}$'
    ),
    CONSTRAINT runtime_invocations_cursors CHECK (
        last_attempt_number >= 0 AND current_fencing_token >= 0
    ),
    CONSTRAINT runtime_invocations_timestamps CHECK (updated_at >= created_at)
);

CREATE TABLE agent.runtime_invocation_attempts (
    tenant_id varchar(200) NOT NULL,
    work_order_id varchar(200) NOT NULL,
    runtime_run_id varchar(200) NOT NULL,
    invocation_id varchar(200) NOT NULL,
    invocation_attempt_id varchar(200) NOT NULL,
    attempt_number bigint NOT NULL,
    fencing_token bigint NOT NULL,
    created_at timestamptz NOT NULL,
    CONSTRAINT runtime_invocation_attempts_pk PRIMARY KEY (tenant_id, invocation_attempt_id),
    CONSTRAINT runtime_invocation_attempts_identity_uk UNIQUE (invocation_attempt_id),
    CONSTRAINT runtime_invocation_attempts_invocation_fk FOREIGN KEY (
        tenant_id, work_order_id, runtime_run_id, invocation_id
    ) REFERENCES agent.runtime_invocations (
        tenant_id, work_order_id, runtime_run_id, invocation_id
    ) ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT runtime_invocation_attempts_sequence_uk UNIQUE (
        tenant_id, invocation_id, attempt_number
    ),
    CONSTRAINT runtime_invocation_attempts_fencing_uk UNIQUE (
        tenant_id, runtime_run_id, fencing_token
    ),
    CONSTRAINT runtime_invocation_attempts_command_scope_uk UNIQUE (
        tenant_id, work_order_id, runtime_run_id, invocation_id,
        invocation_attempt_id, fencing_token
    ),
    CONSTRAINT runtime_invocation_attempts_ids_not_blank CHECK (
        tenant_id <> '' AND work_order_id <> '' AND runtime_run_id <> ''
        AND invocation_id <> '' AND invocation_attempt_id <> ''
    ),
    CONSTRAINT runtime_invocation_attempts_numbers CHECK (
        attempt_number >= 1 AND fencing_token >= 1
    )
);

CREATE TABLE agent.work_order_control_requests (
    tenant_id varchar(200) NOT NULL,
    work_order_id varchar(200) NOT NULL,
    control_request_id varchar(200) NOT NULL,
    request_digest varchar(71) NOT NULL,
    action varchar(32) NOT NULL,
    expected_active_work_version bigint NOT NULL,
    input_id varchar(200),
    input_content_digest varchar(71),
    approval_id varchar(200),
    approval_decision varchar(16),
    approval_comment varchar(4000) NOT NULL DEFAULT '',
    accepted_at timestamptz NOT NULL,
    CONSTRAINT work_order_control_requests_pk PRIMARY KEY (tenant_id, control_request_id),
    CONSTRAINT work_order_control_requests_identity_uk UNIQUE (control_request_id),
    CONSTRAINT work_order_control_requests_work_order_fk FOREIGN KEY (tenant_id, work_order_id)
        REFERENCES agent.work_orders (tenant_id, work_order_id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT work_order_control_requests_authority_uk UNIQUE (
        tenant_id, work_order_id, control_request_id, action
    ),
    CONSTRAINT work_order_control_requests_scope_uk UNIQUE (
        tenant_id, work_order_id, control_request_id
    ),
    CONSTRAINT work_order_control_requests_authority_digest_uk UNIQUE (
        tenant_id, work_order_id, control_request_id, action, request_digest,
        expected_active_work_version
    ),
    CONSTRAINT work_order_control_requests_approval_binding_uk UNIQUE (
        tenant_id, work_order_id, control_request_id, action,
        approval_id, approval_decision, approval_comment
    ),
    CONSTRAINT work_order_control_requests_ids_not_blank CHECK (
        tenant_id <> '' AND work_order_id <> '' AND control_request_id <> ''
        AND (input_id IS NULL OR input_id <> '')
        AND (approval_id IS NULL OR approval_id <> '')
    ),
    CONSTRAINT work_order_control_requests_digest CHECK (
        request_digest COLLATE "C" ~ '^sha256:[0-9a-f]{64}$'
        AND (input_content_digest IS NULL OR input_content_digest COLLATE "C" ~ '^sha256:[0-9a-f]{64}$')
    ),
    CONSTRAINT work_order_control_requests_action CHECK (
        action IN ('append_input', 'interrupt', 'pause', 'resume', 'cancel', 'approval_decision')
    ),
    CONSTRAINT work_order_control_requests_version CHECK (expected_active_work_version >= 1),
    CONSTRAINT work_order_control_requests_shape CHECK (
        (action IN ('append_input', 'interrupt')
            AND input_id IS NOT NULL AND input_content_digest IS NOT NULL
            AND approval_id IS NULL AND approval_decision IS NULL AND approval_comment = '')
        OR (action = 'approval_decision'
            AND input_id IS NULL AND input_content_digest IS NULL
            AND approval_id IS NOT NULL AND approval_decision IN ('approve', 'reject'))
        OR (action IN ('pause', 'resume', 'cancel')
            AND input_id IS NULL AND input_content_digest IS NULL
            AND approval_id IS NULL AND approval_decision IS NULL AND approval_comment = '')
    )
);

CREATE TABLE agent.work_order_control_inputs (
    tenant_id varchar(200) NOT NULL,
    work_order_id varchar(200) NOT NULL,
    control_request_id varchar(200) NOT NULL,
    input_id varchar(200) NOT NULL,
    input_message_id varchar(200) NOT NULL,
    content_digest varchar(71) NOT NULL,
    accepted_at timestamptz NOT NULL,
    CONSTRAINT work_order_control_inputs_pk PRIMARY KEY (tenant_id, input_id),
    CONSTRAINT work_order_control_inputs_identity_uk UNIQUE (input_id),
    CONSTRAINT work_order_control_inputs_message_uk UNIQUE (input_message_id),
    CONSTRAINT work_order_control_inputs_request_uk UNIQUE (tenant_id, control_request_id),
    CONSTRAINT work_order_control_inputs_request_fk FOREIGN KEY (
        tenant_id, work_order_id, control_request_id
    ) REFERENCES agent.work_order_control_requests (
        tenant_id, work_order_id, control_request_id
    )
        ON UPDATE RESTRICT ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED,
    CONSTRAINT work_order_control_inputs_binding_uk UNIQUE (
        tenant_id, work_order_id, control_request_id, input_id, content_digest
    ),
    CONSTRAINT work_order_control_inputs_ids_not_blank CHECK (
        tenant_id <> '' AND work_order_id <> '' AND control_request_id <> ''
        AND input_id <> '' AND input_message_id <> ''
    ),
    CONSTRAINT work_order_control_inputs_digest CHECK (
        content_digest COLLATE "C" ~ '^sha256:[0-9a-f]{64}$'
    )
);

ALTER TABLE agent.work_order_control_requests
    ADD CONSTRAINT work_order_control_requests_input_fk FOREIGN KEY (
        tenant_id, work_order_id, control_request_id, input_id, input_content_digest
    ) REFERENCES agent.work_order_control_inputs (
        tenant_id, work_order_id, control_request_id, input_id, content_digest
    ) ON UPDATE RESTRICT ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED;

CREATE TABLE agent.platform_safety_controllers (
    tenant_id varchar(200) NOT NULL,
    issuer_subject_id varchar(200) NOT NULL,
    admitted_at timestamptz NOT NULL,
    admission_digest varchar(71) NOT NULL,
    CONSTRAINT platform_safety_controllers_pk PRIMARY KEY (tenant_id, issuer_subject_id),
    CONSTRAINT platform_safety_controllers_admission_uk UNIQUE (
        tenant_id, issuer_subject_id, admitted_at
    ),
    CONSTRAINT platform_safety_controllers_tenant_fk FOREIGN KEY (tenant_id)
        REFERENCES agent.tenants (tenant_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT platform_safety_controllers_ids_not_blank CHECK (
        tenant_id <> '' AND issuer_subject_id <> ''
    ),
    CONSTRAINT platform_safety_controllers_digest CHECK (
        admission_digest COLLATE "C" ~ '^sha256:[0-9a-f]{64}$'
    )
);

CREATE TABLE agent.safety_trigger_evidence (
    tenant_id varchar(200) NOT NULL,
    work_order_id varchar(200) NOT NULL,
    evidence_contract_id varchar(200) NOT NULL,
    evidence_id varchar(200) NOT NULL,
    evidence_digest varchar(71) NOT NULL,
    action varchar(16) NOT NULL,
    reason varchar(64) NOT NULL,
    observed_at timestamptz NOT NULL,
    admitted_at timestamptz NOT NULL,
    CONSTRAINT safety_trigger_evidence_pk PRIMARY KEY (
        tenant_id, evidence_contract_id, evidence_id
    ),
    CONSTRAINT safety_trigger_evidence_work_order_fk FOREIGN KEY (tenant_id, work_order_id)
        REFERENCES agent.work_orders (tenant_id, work_order_id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT safety_trigger_evidence_binding_uk UNIQUE (
        tenant_id, work_order_id, evidence_contract_id, evidence_id,
        evidence_digest, action, reason, observed_at
    ),
    CONSTRAINT safety_trigger_evidence_admission_uk UNIQUE (
        tenant_id, work_order_id, evidence_contract_id, evidence_id,
        evidence_digest, action, reason, observed_at, admitted_at
    ),
    CONSTRAINT safety_trigger_evidence_fanout_uk UNIQUE (
        tenant_id, work_order_id, evidence_contract_id, evidence_id,
        evidence_digest, action
    ),
    CONSTRAINT safety_trigger_evidence_ids_not_blank CHECK (
        tenant_id <> '' AND work_order_id <> '' AND evidence_contract_id <> '' AND evidence_id <> ''
    ),
    CONSTRAINT safety_trigger_evidence_contract CHECK (
        evidence_contract_id COLLATE "C" ~ '^urn:agent-platform:[a-z0-9-]+:v[0-9]+$'
    ),
    CONSTRAINT safety_trigger_evidence_digest CHECK (
        evidence_digest COLLATE "C" ~ '^sha256:[0-9a-f]{64}$'
    ),
    CONSTRAINT safety_trigger_evidence_reason CHECK (reason IN (
        'commercial_authorization_expired', 'commercial_authorization_revoked',
        'execution_deadline_exceeded', 'policy_revoked', 'tenant_suspended',
        'provider_admission_revoked', 'budget_exhausted', 'reconciliation_stop',
        'operator_emergency_stop', 'platform_shutdown'
    )),
    CONSTRAINT safety_trigger_evidence_action CHECK (action IN ('pause', 'cancel')),
    CONSTRAINT safety_trigger_evidence_hard_reason_cancel CHECK (
        reason NOT IN (
            'commercial_authorization_expired', 'commercial_authorization_revoked',
            'execution_deadline_exceeded', 'policy_revoked', 'tenant_suspended',
            'provider_admission_revoked', 'budget_exhausted', 'platform_shutdown'
        ) OR action = 'cancel'
    ),
    CONSTRAINT safety_trigger_evidence_timestamps CHECK (observed_at <= admitted_at)
);

CREATE TABLE agent.child_agent_run_admission_decisions (
    tenant_id varchar(200) NOT NULL,
    work_order_id varchar(200) NOT NULL,
    decision_id varchar(200) NOT NULL,
    decision_digest varchar(71) NOT NULL,
    spawn_request_id varchar(200) NOT NULL,
    spawn_request_digest varchar(71) NOT NULL,
    parent_agent_run_id varchar(200) NOT NULL,
    outcome varchar(16) NOT NULL,
    reason_codes varchar(64)[] NOT NULL,
    reason_codes_key varchar(1039) GENERATED ALWAYS AS (
        agent.child_admission_reason_codes_key(reason_codes)
    ) STORED,
    child_agent_run_id varchar(200),
    runtime_run_id varchar(200),
    decided_at timestamptz NOT NULL,
    CONSTRAINT child_agent_run_admission_decisions_pk PRIMARY KEY (tenant_id, decision_id),
    CONSTRAINT child_agent_run_admission_decisions_identity_uk UNIQUE (decision_id),
    CONSTRAINT child_agent_run_admission_decisions_spawn_uk UNIQUE (
        tenant_id, work_order_id, spawn_request_id
    ),
    CONSTRAINT child_agent_run_admission_decisions_work_order_fk FOREIGN KEY (tenant_id, work_order_id)
        REFERENCES agent.work_orders (tenant_id, work_order_id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT child_agent_run_admission_decisions_parent_fk FOREIGN KEY (
        tenant_id, work_order_id, parent_agent_run_id
    ) REFERENCES agent.agent_runs (tenant_id, work_order_id, agent_run_id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT child_agent_run_admission_decisions_child_fk FOREIGN KEY (
        tenant_id, work_order_id, child_agent_run_id, runtime_run_id
    ) REFERENCES agent.agent_runtime_runs (
        tenant_id, work_order_id, agent_run_id, runtime_run_id
    ) ON UPDATE RESTRICT ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED,
    CONSTRAINT child_agent_run_admission_decisions_command_uk UNIQUE (
        tenant_id, work_order_id, decision_id, decision_digest,
        spawn_request_id, outcome, reason_codes_key, child_agent_run_id
    ),
    CONSTRAINT child_agent_run_admission_decisions_command_base_uk UNIQUE (
        tenant_id, work_order_id, decision_id, decision_digest,
        spawn_request_id, outcome, reason_codes_key
    ),
    CONSTRAINT child_agent_run_admission_decisions_ids_not_blank CHECK (
        tenant_id <> '' AND work_order_id <> '' AND decision_id <> ''
        AND spawn_request_id <> '' AND parent_agent_run_id <> ''
        AND (child_agent_run_id IS NULL OR child_agent_run_id <> '')
        AND (runtime_run_id IS NULL OR runtime_run_id <> '')
    ),
    CONSTRAINT child_agent_run_admission_decisions_digests CHECK (
        decision_digest COLLATE "C" ~ '^sha256:[0-9a-f]{64}$'
        AND spawn_request_digest COLLATE "C" ~ '^sha256:[0-9a-f]{64}$'
    ),
    CONSTRAINT child_agent_run_admission_decisions_outcome CHECK (outcome IN ('accepted', 'rejected')),
    CONSTRAINT child_agent_run_admission_decisions_reason_codes CHECK (
        agent.valid_child_admission_reason_codes(outcome, reason_codes)
    ),
    CONSTRAINT child_agent_run_admission_decisions_shape CHECK (
        (outcome = 'accepted' AND child_agent_run_id IS NOT NULL AND runtime_run_id IS NOT NULL)
        OR (outcome = 'rejected' AND child_agent_run_id IS NULL AND runtime_run_id IS NULL)
    )
);

ALTER TABLE agent.outbox_messages
    ADD COLUMN IF NOT EXISTS initial_available_at timestamptz,
    ADD CONSTRAINT outbox_messages_initial_available_at_check CHECK (
        initial_available_at IS NULL OR initial_available_at >= created_at
    ),
    ADD CONSTRAINT outbox_messages_control_binding_uk UNIQUE (
        tenant_id, message_id, payload_digest
    ),
    ADD CONSTRAINT outbox_messages_control_delivery_binding_uk UNIQUE (
        tenant_id, message_id, payload_digest, destination, initial_available_at, created_at
    );

CREATE TABLE agent.system_safety_controls (
    tenant_id varchar(200) NOT NULL,
    work_order_id varchar(200) NOT NULL,
    runtime_run_id varchar(200) NOT NULL,
    safety_control_id varchar(200) NOT NULL,
    action varchar(16) NOT NULL,
    reason varchar(64) NOT NULL,
    evidence_contract_id varchar(200) NOT NULL,
    evidence_id varchar(200) NOT NULL,
    evidence_digest varchar(71) NOT NULL,
    observed_at timestamptz NOT NULL,
    evidence_admitted_at timestamptz NOT NULL,
    issued_by varchar(64) NOT NULL,
    issuer_subject_id varchar(200) NOT NULL,
    issuer_admitted_at timestamptz NOT NULL,
    issued_at timestamptz NOT NULL,
    control_digest varchar(71) NOT NULL,
    outbox_message_id varchar(200) NOT NULL,
    outbox_payload_digest varchar(71) NOT NULL,
    outbox_destination varchar(200) NOT NULL,
    outbox_available_at timestamptz NOT NULL,
    outbox_created_at timestamptz NOT NULL,
    CONSTRAINT system_safety_controls_pk PRIMARY KEY (tenant_id, safety_control_id),
    CONSTRAINT system_safety_controls_identity_uk UNIQUE (safety_control_id),
    CONSTRAINT system_safety_controls_digest_uk UNIQUE (control_digest),
    CONSTRAINT system_safety_controls_outbox_uk UNIQUE (outbox_message_id),
    CONSTRAINT system_safety_controls_runtime_fk FOREIGN KEY (tenant_id, runtime_run_id)
        REFERENCES agent.agent_runtime_runs (tenant_id, runtime_run_id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT system_safety_controls_runtime_scope_fk FOREIGN KEY (
        tenant_id, work_order_id, runtime_run_id
    ) REFERENCES agent.agent_runtime_runs (
        tenant_id, work_order_id, runtime_run_id
    ) ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT system_safety_controls_controller_fk FOREIGN KEY (
        tenant_id, issuer_subject_id, issuer_admitted_at
    ) REFERENCES agent.platform_safety_controllers (
        tenant_id, issuer_subject_id, admitted_at
    ) ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT system_safety_controls_evidence_fk FOREIGN KEY (
        tenant_id, work_order_id, evidence_contract_id, evidence_id,
        evidence_digest, action, reason, observed_at, evidence_admitted_at
    ) REFERENCES agent.safety_trigger_evidence (
        tenant_id, work_order_id, evidence_contract_id, evidence_id,
        evidence_digest, action, reason, observed_at, admitted_at
    ) ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT system_safety_controls_outbox_fk FOREIGN KEY (
        tenant_id, outbox_message_id, outbox_payload_digest,
        outbox_destination, outbox_available_at, outbox_created_at
    ) REFERENCES agent.outbox_messages (
        tenant_id, message_id, payload_digest,
        destination, initial_available_at, created_at
    ) ON UPDATE RESTRICT ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED,
    CONSTRAINT system_safety_controls_command_uk UNIQUE (
        tenant_id, work_order_id, runtime_run_id, safety_control_id, control_digest, action
    ),
    CONSTRAINT system_safety_controls_target_uk UNIQUE (
        tenant_id, work_order_id, runtime_run_id, safety_control_id, control_digest
    ),
    CONSTRAINT system_safety_controls_ids_not_blank CHECK (
        tenant_id <> '' AND work_order_id <> '' AND runtime_run_id <> ''
        AND safety_control_id <> '' AND issuer_subject_id <> ''
        AND outbox_message_id <> ''
    ),
    CONSTRAINT system_safety_controls_action CHECK (action IN ('pause', 'cancel')),
    CONSTRAINT system_safety_controls_reason CHECK (reason IN (
        'commercial_authorization_expired', 'commercial_authorization_revoked',
        'execution_deadline_exceeded', 'policy_revoked', 'tenant_suspended',
        'provider_admission_revoked', 'budget_exhausted', 'reconciliation_stop',
        'operator_emergency_stop', 'platform_shutdown'
    )),
    CONSTRAINT system_safety_controls_hard_reason_cancel CHECK (
        reason NOT IN (
            'commercial_authorization_expired', 'commercial_authorization_revoked',
            'execution_deadline_exceeded', 'policy_revoked', 'tenant_suspended',
            'provider_admission_revoked', 'budget_exhausted', 'platform_shutdown'
        ) OR action = 'cancel'
    ),
    CONSTRAINT system_safety_controls_issuer CHECK (issued_by = 'platform_safety_controller'),
    CONSTRAINT system_safety_controls_digest CHECK (
        evidence_digest COLLATE "C" ~ '^sha256:[0-9a-f]{64}$'
        AND control_digest COLLATE "C" ~ '^sha256:[0-9a-f]{64}$'
        AND outbox_payload_digest COLLATE "C" ~ '^sha256:[0-9a-f]{64}$'
    ),
    CONSTRAINT system_safety_controls_timestamps CHECK (
        observed_at <= evidence_admitted_at
        AND evidence_admitted_at <= issued_at
        AND issuer_admitted_at <= issued_at
        AND outbox_available_at = issued_at
        AND outbox_created_at = issued_at
    ),
    CONSTRAINT system_safety_controls_outbox_destination CHECK (
        outbox_destination = 'agent-runtime-control'
    )
);

CREATE TABLE agent.agent_runtime_commands (
    tenant_id varchar(200) NOT NULL,
    work_order_id varchar(200) NOT NULL,
    command_id varchar(200) NOT NULL,
    command_digest varchar(71) NOT NULL,
    runtime_run_id varchar(200) NOT NULL,
    command_sequence bigint NOT NULL,
    type varchar(32) NOT NULL,
    authorized_control_request_id varchar(200),
    system_safety_control_id varchar(200),
    system_safety_control_digest varchar(71),
    input_id varchar(200),
    input_content_digest varchar(71),
    approval_id varchar(200),
    approval_decision varchar(16),
    approval_comment varchar(4000) NOT NULL DEFAULT '',
    spawn_request_id varchar(200),
    child_admission_decision_id varchar(200),
    child_admission_decision_digest varchar(71),
    spawn_outcome varchar(16),
    spawn_reason_codes varchar(64)[],
    spawn_reason_codes_key varchar(1039) GENERATED ALWAYS AS (
        agent.child_admission_reason_codes_key(spawn_reason_codes)
    ) STORED,
    child_agent_run_id varchar(200),
    reason varchar(1000),
    invocation_id varchar(200) NOT NULL,
    invocation_attempt_id varchar(200) NOT NULL,
    fencing_token bigint NOT NULL,
    idempotency_key varchar(200) NOT NULL,
    deadline_at timestamptz NOT NULL,
    created_at timestamptz NOT NULL,
    outbox_message_id varchar(200) NOT NULL,
    outbox_payload_digest varchar(71) NOT NULL,
    outbox_destination varchar(200) NOT NULL,
    outbox_available_at timestamptz NOT NULL,
    outbox_created_at timestamptz NOT NULL,
    CONSTRAINT agent_runtime_commands_pk PRIMARY KEY (tenant_id, command_id),
    CONSTRAINT agent_runtime_commands_identity_uk UNIQUE (command_id),
    CONSTRAINT agent_runtime_commands_digest_uk UNIQUE (command_digest),
    CONSTRAINT agent_runtime_commands_outbox_uk UNIQUE (outbox_message_id),
    CONSTRAINT agent_runtime_commands_sequence_uk UNIQUE (
        tenant_id, runtime_run_id, command_sequence
    ),
    CONSTRAINT agent_runtime_commands_idempotency_uk UNIQUE (
        tenant_id, runtime_run_id, idempotency_key
    ),
    CONSTRAINT agent_runtime_commands_fanout_target_uk UNIQUE (
        tenant_id, work_order_id, runtime_run_id, command_id, fencing_token
    ),
    CONSTRAINT agent_runtime_commands_runtime_fk FOREIGN KEY (
        tenant_id, work_order_id, runtime_run_id
    ) REFERENCES agent.agent_runtime_runs (
        tenant_id, work_order_id, runtime_run_id
    )
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT agent_runtime_commands_attempt_fk FOREIGN KEY (
        tenant_id, work_order_id, runtime_run_id, invocation_id,
        invocation_attempt_id, fencing_token
    ) REFERENCES agent.runtime_invocation_attempts (
        tenant_id, work_order_id, runtime_run_id, invocation_id,
        invocation_attempt_id, fencing_token
    ) ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT agent_runtime_commands_invocation_digest_fk FOREIGN KEY (
        tenant_id, work_order_id, runtime_run_id, invocation_id, command_digest
    ) REFERENCES agent.runtime_invocations (
        tenant_id, work_order_id, runtime_run_id, invocation_id, request_digest
    ) ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT agent_runtime_commands_outbox_fk FOREIGN KEY (
        tenant_id, outbox_message_id, outbox_payload_digest,
        outbox_destination, outbox_available_at, outbox_created_at
    ) REFERENCES agent.outbox_messages (
        tenant_id, message_id, payload_digest,
        destination, initial_available_at, created_at
    ) ON UPDATE RESTRICT ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED,
    CONSTRAINT agent_runtime_commands_control_fk FOREIGN KEY (
        tenant_id, work_order_id, authorized_control_request_id, type
    ) REFERENCES agent.work_order_control_requests (
        tenant_id, work_order_id, control_request_id, action
    ) ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT agent_runtime_commands_input_fk FOREIGN KEY (
        tenant_id, work_order_id, authorized_control_request_id, input_id, input_content_digest
    ) REFERENCES agent.work_order_control_inputs (
        tenant_id, work_order_id, control_request_id, input_id, content_digest
    ) ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT agent_runtime_commands_safety_fk FOREIGN KEY (
        tenant_id, work_order_id, runtime_run_id, system_safety_control_id,
        system_safety_control_digest, type
    ) REFERENCES agent.system_safety_controls (
        tenant_id, work_order_id, runtime_run_id, safety_control_id,
        control_digest, action
    ) ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT agent_runtime_commands_child_decision_fk FOREIGN KEY (
        tenant_id, work_order_id, child_admission_decision_id,
        child_admission_decision_digest, spawn_request_id, spawn_outcome,
        spawn_reason_codes_key
    ) REFERENCES agent.child_agent_run_admission_decisions (
        tenant_id, work_order_id, decision_id, decision_digest,
        spawn_request_id, outcome, reason_codes_key
    ) ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT agent_runtime_commands_accepted_child_fk FOREIGN KEY (
        tenant_id, work_order_id, child_admission_decision_id,
        child_admission_decision_digest, spawn_request_id, spawn_outcome,
        spawn_reason_codes_key, child_agent_run_id
    ) REFERENCES agent.child_agent_run_admission_decisions (
        tenant_id, work_order_id, decision_id, decision_digest,
        spawn_request_id, outcome, reason_codes_key, child_agent_run_id
    ) ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT agent_runtime_commands_approval_fk FOREIGN KEY (
        tenant_id, work_order_id, authorized_control_request_id, type,
        approval_id, approval_decision, approval_comment
    ) REFERENCES agent.work_order_control_requests (
        tenant_id, work_order_id, control_request_id, action,
        approval_id, approval_decision, approval_comment
    ) ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT agent_runtime_commands_ids_not_blank CHECK (
        tenant_id <> '' AND work_order_id <> '' AND command_id <> ''
        AND runtime_run_id <> '' AND invocation_id <> ''
        AND invocation_attempt_id <> '' AND char_length(idempotency_key) >= 16
        AND outbox_message_id <> ''
        AND (reason IS NULL OR reason <> '')
    ),
    CONSTRAINT agent_runtime_commands_digests CHECK (
        command_digest COLLATE "C" ~ '^sha256:[0-9a-f]{64}$'
        AND (system_safety_control_digest IS NULL OR system_safety_control_digest COLLATE "C" ~ '^sha256:[0-9a-f]{64}$')
        AND (input_content_digest IS NULL OR input_content_digest COLLATE "C" ~ '^sha256:[0-9a-f]{64}$')
        AND (child_admission_decision_digest IS NULL OR child_admission_decision_digest COLLATE "C" ~ '^sha256:[0-9a-f]{64}$')
        AND outbox_payload_digest COLLATE "C" ~ '^sha256:[0-9a-f]{64}$'
    ),
    CONSTRAINT agent_runtime_commands_numbers CHECK (
        command_sequence >= 1 AND fencing_token >= 1
    ),
    CONSTRAINT agent_runtime_commands_type CHECK (type IN (
        'append_input', 'interrupt', 'pause', 'resume', 'cancel',
        'approval_decision', 'checkpoint', 'subagent_spawn_decision'
    )),
    CONSTRAINT agent_runtime_commands_deadline CHECK (
        deadline_at > created_at
        AND outbox_available_at = created_at
        AND outbox_created_at = created_at
        AND outbox_available_at <= deadline_at
    ),
    CONSTRAINT agent_runtime_commands_outbox_destination CHECK (
        outbox_destination = 'agent-runtime-control'
    ),
    CONSTRAINT agent_runtime_commands_non_spawn_shape CHECK (
        type = 'subagent_spawn_decision'
        OR (spawn_request_id IS NULL
            AND child_admission_decision_id IS NULL
            AND child_admission_decision_digest IS NULL
            AND spawn_outcome IS NULL
            AND spawn_reason_codes IS NULL
            AND child_agent_run_id IS NULL)
    ),
    CONSTRAINT agent_runtime_commands_non_input_shape CHECK (
        type IN ('append_input', 'interrupt')
        OR (input_id IS NULL AND input_content_digest IS NULL)
    ),
    CONSTRAINT agent_runtime_commands_non_approval_shape CHECK (
        type = 'approval_decision'
        OR (approval_id IS NULL AND approval_decision IS NULL AND approval_comment = '')
    ),
    CONSTRAINT agent_runtime_commands_authority_shape CHECK (
        (type IN ('append_input', 'interrupt')
            AND authorized_control_request_id IS NOT NULL
            AND input_id IS NOT NULL AND input_content_digest IS NOT NULL
            AND system_safety_control_id IS NULL AND system_safety_control_digest IS NULL
            AND approval_id IS NULL AND approval_decision IS NULL
            AND child_admission_decision_id IS NULL)
        OR (type = 'approval_decision'
            AND authorized_control_request_id IS NOT NULL
            AND approval_id IS NOT NULL AND approval_decision IN ('approve', 'reject')
            AND input_id IS NULL AND input_content_digest IS NULL
            AND system_safety_control_id IS NULL AND system_safety_control_digest IS NULL
            AND child_admission_decision_id IS NULL)
        OR (type IN ('pause', 'cancel')
            AND ((authorized_control_request_id IS NOT NULL
                    AND system_safety_control_id IS NULL AND system_safety_control_digest IS NULL)
                OR (authorized_control_request_id IS NULL
                    AND system_safety_control_id IS NOT NULL
                    AND system_safety_control_digest IS NOT NULL))
            AND input_id IS NULL AND input_content_digest IS NULL
            AND approval_id IS NULL AND approval_decision IS NULL
            AND child_admission_decision_id IS NULL)
        OR (type = 'resume'
            AND authorized_control_request_id IS NOT NULL
            AND system_safety_control_id IS NULL AND system_safety_control_digest IS NULL
            AND input_id IS NULL AND input_content_digest IS NULL
            AND approval_id IS NULL AND approval_decision IS NULL
            AND child_admission_decision_id IS NULL)
        OR (type = 'checkpoint'
            AND authorized_control_request_id IS NULL
            AND system_safety_control_id IS NULL AND system_safety_control_digest IS NULL
            AND input_id IS NULL AND input_content_digest IS NULL
            AND approval_id IS NULL AND approval_decision IS NULL
            AND child_admission_decision_id IS NULL)
        OR (type = 'subagent_spawn_decision'
            AND authorized_control_request_id IS NULL
            AND system_safety_control_id IS NULL AND system_safety_control_digest IS NULL
            AND input_id IS NULL AND input_content_digest IS NULL
            AND approval_id IS NULL AND approval_decision IS NULL
            AND spawn_request_id IS NOT NULL
            AND child_admission_decision_id IS NOT NULL
            AND child_admission_decision_digest IS NOT NULL
            AND spawn_outcome IN ('accepted', 'rejected')
            AND spawn_reason_codes IS NOT NULL
            AND agent.valid_child_admission_reason_codes(spawn_outcome, spawn_reason_codes)
            AND ((spawn_outcome = 'accepted' AND child_agent_run_id IS NOT NULL)
                OR (spawn_outcome = 'rejected' AND child_agent_run_id IS NULL)))
    )
);

CREATE INDEX agent_runtime_commands_runtime_idx
    ON agent.agent_runtime_commands (tenant_id, runtime_run_id, command_sequence);

CREATE UNIQUE INDEX agent_runtime_commands_system_safety_control_uk
    ON agent.agent_runtime_commands (tenant_id, system_safety_control_id)
    WHERE system_safety_control_id IS NOT NULL;

CREATE TABLE agent.agent_run_control_fanouts (
    tenant_id varchar(200) NOT NULL,
    work_order_id varchar(200) NOT NULL,
    fanout_id varchar(200) NOT NULL,
    action varchar(16) NOT NULL,
    authority_kind varchar(32) NOT NULL,
    authority_id varchar(200) NOT NULL,
    authority_digest varchar(71) NOT NULL,
    expected_active_work_version bigint NOT NULL,
    control_request_id varchar(200),
    safety_evidence_contract_id varchar(200),
    safety_evidence_id varchar(200),
    latest_version bigint NOT NULL,
    latest_digest varchar(71) NOT NULL,
    created_at timestamptz NOT NULL,
    updated_at timestamptz NOT NULL,
    CONSTRAINT agent_run_control_fanouts_pk PRIMARY KEY (tenant_id, fanout_id),
    CONSTRAINT agent_run_control_fanouts_identity_uk UNIQUE (fanout_id),
    CONSTRAINT agent_run_control_fanouts_authority_uk UNIQUE (
        tenant_id, work_order_id, authority_kind, authority_id, authority_digest
    ),
    CONSTRAINT agent_run_control_fanouts_target_authority_uk UNIQUE (
        tenant_id, work_order_id, fanout_id, authority_kind
    ),
    CONSTRAINT agent_run_control_fanouts_version_authority_uk UNIQUE (
        tenant_id, work_order_id, fanout_id, action, authority_kind,
        authority_id, authority_digest, created_at
    ),
    CONSTRAINT agent_run_control_fanouts_work_order_fk FOREIGN KEY (tenant_id, work_order_id)
        REFERENCES agent.work_orders (tenant_id, work_order_id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT agent_run_control_fanouts_control_fk FOREIGN KEY (
        tenant_id, work_order_id, control_request_id, action, authority_digest,
        expected_active_work_version
    ) REFERENCES agent.work_order_control_requests (
        tenant_id, work_order_id, control_request_id, action, request_digest,
        expected_active_work_version
    ) ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT agent_run_control_fanouts_safety_evidence_fk FOREIGN KEY (
        tenant_id, work_order_id, safety_evidence_contract_id,
        safety_evidence_id, authority_digest, action
    ) REFERENCES agent.safety_trigger_evidence (
        tenant_id, work_order_id, evidence_contract_id,
        evidence_id, evidence_digest, action
    ) ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT agent_run_control_fanouts_ids_not_blank CHECK (
        tenant_id <> '' AND work_order_id <> '' AND fanout_id <> ''
        AND authority_id <> ''
    ),
    CONSTRAINT agent_run_control_fanouts_action CHECK (action IN ('pause', 'cancel')),
    CONSTRAINT agent_run_control_fanouts_authority_kind CHECK (
        authority_kind IN ('work_order_control_request', 'system_safety_trigger')
    ),
    CONSTRAINT agent_run_control_fanouts_digest CHECK (
        authority_digest COLLATE "C" ~ '^sha256:[0-9a-f]{64}$'
        AND latest_digest COLLATE "C" ~ '^sha256:[0-9a-f]{64}$'
    ),
    CONSTRAINT agent_run_control_fanouts_version CHECK (
        latest_version >= 1 AND expected_active_work_version >= 1
    ),
    CONSTRAINT agent_run_control_fanouts_authority_shape CHECK (
        (authority_kind = 'work_order_control_request'
            AND control_request_id = authority_id
            AND safety_evidence_contract_id IS NULL AND safety_evidence_id IS NULL)
        OR (authority_kind = 'system_safety_trigger'
            AND control_request_id IS NULL
            AND safety_evidence_id = authority_id
            AND safety_evidence_contract_id IS NOT NULL)
    ),
    CONSTRAINT agent_run_control_fanouts_timestamps CHECK (updated_at >= created_at)
);

CREATE UNIQUE INDEX agent_run_control_fanouts_user_authority_uk
    ON agent.agent_run_control_fanouts (tenant_id, work_order_id, control_request_id)
    WHERE authority_kind = 'work_order_control_request';

CREATE UNIQUE INDEX agent_run_control_fanouts_system_authority_uk
    ON agent.agent_run_control_fanouts (
        tenant_id, work_order_id, safety_evidence_contract_id, safety_evidence_id
    ) WHERE authority_kind = 'system_safety_trigger';

CREATE TABLE agent.agent_run_control_fanout_targets (
    tenant_id varchar(200) NOT NULL,
    work_order_id varchar(200) NOT NULL,
    fanout_id varchar(200) NOT NULL,
    authority_kind varchar(32) NOT NULL,
    agent_run_id varchar(200) NOT NULL,
    runtime_run_id varchar(200) NOT NULL,
    target_fencing_token bigint NOT NULL,
    system_safety_control_id varchar(200),
    system_safety_control_digest varchar(71),
    command_id varchar(200) NOT NULL,
    control_state varchar(32) NOT NULL,
    claim_fencing_token bigint NOT NULL DEFAULT 0,
    claim_worker_id varchar(200),
    claim_expires_at timestamptz,
    updated_at timestamptz NOT NULL,
    CONSTRAINT agent_run_control_fanout_targets_pk PRIMARY KEY (
        tenant_id, fanout_id, agent_run_id
    ),
    CONSTRAINT agent_run_control_fanout_targets_runtime_uk UNIQUE (
        tenant_id, fanout_id, runtime_run_id
    ),
    CONSTRAINT agent_run_control_fanout_targets_snapshot_identity_uk UNIQUE (
        tenant_id, fanout_id, agent_run_id, runtime_run_id, target_fencing_token
    ),
    CONSTRAINT agent_run_control_fanout_targets_snapshot_safety_uk UNIQUE (
        tenant_id, fanout_id, agent_run_id, runtime_run_id, target_fencing_token,
        system_safety_control_id, system_safety_control_digest
    ),
    CONSTRAINT agent_run_control_fanout_targets_command_uk UNIQUE (command_id),
    CONSTRAINT agent_run_control_fanout_targets_fanout_fk FOREIGN KEY (tenant_id, fanout_id)
        REFERENCES agent.agent_run_control_fanouts (tenant_id, fanout_id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT agent_run_control_fanout_targets_authority_fk FOREIGN KEY (
        tenant_id, work_order_id, fanout_id, authority_kind
    ) REFERENCES agent.agent_run_control_fanouts (
        tenant_id, work_order_id, fanout_id, authority_kind
    ) ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT agent_run_control_fanout_targets_runtime_fk FOREIGN KEY (
        tenant_id, work_order_id, agent_run_id, runtime_run_id
    ) REFERENCES agent.agent_runtime_runs (
        tenant_id, work_order_id, agent_run_id, runtime_run_id
    ) ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT agent_run_control_fanout_targets_safety_fk FOREIGN KEY (
        tenant_id, work_order_id, runtime_run_id, system_safety_control_id,
        system_safety_control_digest
    ) REFERENCES agent.system_safety_controls (
        tenant_id, work_order_id, runtime_run_id, safety_control_id,
        control_digest
    ) ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT agent_run_control_fanout_targets_command_fk FOREIGN KEY (
        tenant_id, work_order_id, runtime_run_id, command_id, target_fencing_token
    ) REFERENCES agent.agent_runtime_commands (
        tenant_id, work_order_id, runtime_run_id, command_id, fencing_token
    ) ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT agent_run_control_fanout_targets_ids_not_blank CHECK (
        tenant_id <> '' AND work_order_id <> '' AND fanout_id <> ''
        AND agent_run_id <> '' AND runtime_run_id <> '' AND command_id <> ''
    ),
    CONSTRAINT agent_run_control_fanout_targets_digests CHECK (
        system_safety_control_digest IS NULL
        OR system_safety_control_digest COLLATE "C" ~ '^sha256:[0-9a-f]{64}$'
    ),
    CONSTRAINT agent_run_control_fanout_targets_state CHECK (control_state IN (
        'pending', 'dispatched', 'confirmed', 'terminal_before_control', 'outcome_unknown'
    )),
    CONSTRAINT agent_run_control_fanout_targets_tokens CHECK (
        target_fencing_token >= 1 AND claim_fencing_token >= 0
    ),
    CONSTRAINT agent_run_control_fanout_targets_claim CHECK (
        (claim_worker_id IS NULL AND claim_expires_at IS NULL)
        OR (claim_worker_id IS NOT NULL AND claim_worker_id <> ''
            AND claim_expires_at IS NOT NULL AND claim_expires_at > updated_at)
    ),
    CONSTRAINT agent_run_control_fanout_targets_safety_pair CHECK (
        (authority_kind = 'system_safety_trigger'
            AND system_safety_control_id IS NOT NULL
            AND system_safety_control_digest IS NOT NULL)
        OR (authority_kind = 'work_order_control_request'
            AND system_safety_control_id IS NULL
            AND system_safety_control_digest IS NULL)
    )
);

CREATE INDEX agent_run_control_fanout_targets_claim_idx
    ON agent.agent_run_control_fanout_targets (
        tenant_id, control_state, claim_expires_at, updated_at, fanout_id, agent_run_id
    ) WHERE control_state IN ('pending', 'dispatched', 'outcome_unknown');

CREATE TABLE agent.agent_run_control_fanout_versions (
    tenant_id varchar(200) NOT NULL,
    work_order_id varchar(200) NOT NULL,
    fanout_id varchar(200) NOT NULL,
    fanout_version bigint NOT NULL,
    previous_fanout_version bigint,
    previous_fanout_digest varchar(71),
    fanout_digest varchar(71) NOT NULL,
    action varchar(16) NOT NULL,
    authority_kind varchar(32) NOT NULL,
    authority_id varchar(200) NOT NULL,
    authority_digest varchar(71) NOT NULL,
    created_at timestamptz NOT NULL,
    updated_at timestamptz NOT NULL,
    CONSTRAINT agent_run_control_fanout_versions_pk PRIMARY KEY (
        tenant_id, fanout_id, fanout_version
    ),
    CONSTRAINT agent_run_control_fanout_versions_digest_uk UNIQUE (fanout_digest),
    CONSTRAINT agent_run_control_fanout_versions_fanout_fk FOREIGN KEY (tenant_id, fanout_id)
        REFERENCES agent.agent_run_control_fanouts (tenant_id, fanout_id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT agent_run_control_fanout_versions_authority_fk FOREIGN KEY (
        tenant_id, work_order_id, fanout_id, action, authority_kind,
        authority_id, authority_digest, created_at
    ) REFERENCES agent.agent_run_control_fanouts (
        tenant_id, work_order_id, fanout_id, action, authority_kind,
        authority_id, authority_digest, created_at
    ) ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT agent_run_control_fanout_versions_identity_uk UNIQUE (
        tenant_id, fanout_id, fanout_version, fanout_digest
    ),
    CONSTRAINT agent_run_control_fanout_versions_target_authority_uk UNIQUE (
        tenant_id, fanout_id, fanout_version, authority_kind
    ),
    CONSTRAINT agent_run_control_fanout_versions_predecessor_fk FOREIGN KEY (
        tenant_id, fanout_id, previous_fanout_version, previous_fanout_digest
    ) REFERENCES agent.agent_run_control_fanout_versions (
        tenant_id, fanout_id, fanout_version, fanout_digest
    ) ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT agent_run_control_fanout_versions_digests CHECK (
        fanout_digest COLLATE "C" ~ '^sha256:[0-9a-f]{64}$'
        AND (previous_fanout_digest IS NULL
            OR previous_fanout_digest COLLATE "C" ~ '^sha256:[0-9a-f]{64}$')
        AND authority_digest COLLATE "C" ~ '^sha256:[0-9a-f]{64}$'
    ),
    CONSTRAINT agent_run_control_fanout_versions_predecessor CHECK (
        (fanout_version = 1 AND previous_fanout_version IS NULL AND previous_fanout_digest IS NULL)
        OR (fanout_version > 1
            AND previous_fanout_version = fanout_version - 1
            AND previous_fanout_digest IS NOT NULL)
    ),
    CONSTRAINT agent_run_control_fanout_versions_timestamps CHECK (
        fanout_version >= 1 AND updated_at >= created_at
    )
);

ALTER TABLE agent.agent_run_control_fanouts
    ADD CONSTRAINT agent_run_control_fanouts_latest_version_fk FOREIGN KEY (
        tenant_id, fanout_id, latest_version, latest_digest
    ) REFERENCES agent.agent_run_control_fanout_versions (
        tenant_id, fanout_id, fanout_version, fanout_digest
    ) ON UPDATE RESTRICT ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED;

CREATE TABLE agent.agent_run_control_fanout_target_versions (
    tenant_id varchar(200) NOT NULL,
    fanout_id varchar(200) NOT NULL,
    fanout_version bigint NOT NULL,
    authority_kind varchar(32) NOT NULL,
    agent_run_id varchar(200) NOT NULL,
    runtime_run_id varchar(200) NOT NULL,
    target_fencing_token bigint NOT NULL,
    system_safety_control_id varchar(200),
    system_safety_control_digest varchar(71),
    control_state varchar(32) NOT NULL,
    CONSTRAINT agent_run_control_fanout_target_versions_pk PRIMARY KEY (
        tenant_id, fanout_id, fanout_version, agent_run_id
    ),
    CONSTRAINT agent_run_control_fanout_target_versions_runtime_uk UNIQUE (
        tenant_id, fanout_id, fanout_version, runtime_run_id
    ),
    CONSTRAINT agent_run_control_fanout_target_versions_version_fk FOREIGN KEY (
        tenant_id, fanout_id, fanout_version
    ) REFERENCES agent.agent_run_control_fanout_versions (
        tenant_id, fanout_id, fanout_version
    ) ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT agent_run_control_fanout_target_versions_authority_fk FOREIGN KEY (
        tenant_id, fanout_id, fanout_version, authority_kind
    ) REFERENCES agent.agent_run_control_fanout_versions (
        tenant_id, fanout_id, fanout_version, authority_kind
    ) ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT agent_run_control_fanout_target_versions_target_fk FOREIGN KEY (
        tenant_id, fanout_id, agent_run_id, runtime_run_id, target_fencing_token
    ) REFERENCES agent.agent_run_control_fanout_targets (
        tenant_id, fanout_id, agent_run_id, runtime_run_id, target_fencing_token
    ) ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT agent_run_control_fanout_target_versions_safety_fk FOREIGN KEY (
        tenant_id, fanout_id, agent_run_id, runtime_run_id, target_fencing_token,
        system_safety_control_id, system_safety_control_digest
    ) REFERENCES agent.agent_run_control_fanout_targets (
        tenant_id, fanout_id, agent_run_id, runtime_run_id, target_fencing_token,
        system_safety_control_id, system_safety_control_digest
    ) ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT agent_run_control_fanout_target_versions_state CHECK (control_state IN (
        'pending', 'dispatched', 'confirmed', 'terminal_before_control', 'outcome_unknown'
    )),
    CONSTRAINT agent_run_control_fanout_target_versions_fencing CHECK (target_fencing_token >= 1),
    CONSTRAINT agent_run_control_fanout_target_versions_safety_pair CHECK (
        (authority_kind = 'system_safety_trigger'
            AND system_safety_control_id IS NOT NULL
            AND system_safety_control_digest IS NOT NULL)
        OR (authority_kind = 'work_order_control_request'
            AND system_safety_control_id IS NULL
            AND system_safety_control_digest IS NULL)
    )
);

CREATE TRIGGER work_orders_control_update_guard
BEFORE UPDATE ON agent.work_orders
FOR EACH ROW EXECUTE FUNCTION agent.enforce_work_order_control_update();

CREATE TRIGGER agent_runtime_runs_command_cursor_guard
BEFORE UPDATE ON agent.agent_runtime_runs
FOR EACH ROW EXECUTE FUNCTION agent.enforce_runtime_command_cursor_update();

CREATE TRIGGER runtime_invocations_attempt_cursor_guard
BEFORE UPDATE ON agent.runtime_invocations
FOR EACH ROW EXECUTE FUNCTION agent.enforce_invocation_attempt_cursor_update();

CREATE TRIGGER agent_runs_open_admission_guard
AFTER INSERT ON agent.agent_runs
FOR EACH ROW EXECUTE FUNCTION agent.enforce_open_work_order_admission();

CREATE TRIGGER agent_runtime_runs_open_admission_guard
AFTER INSERT ON agent.agent_runtime_runs
FOR EACH ROW EXECUTE FUNCTION agent.enforce_open_work_order_admission();

CREATE TRIGGER child_admission_decisions_open_admission_guard
AFTER INSERT ON agent.child_agent_run_admission_decisions
FOR EACH ROW EXECUTE FUNCTION agent.enforce_open_work_order_admission();

CREATE TRIGGER agent_run_control_fanouts_version_guard
BEFORE UPDATE ON agent.agent_run_control_fanouts
FOR EACH ROW EXECUTE FUNCTION agent.enforce_fanout_version_update();

CREATE TRIGGER agent_run_control_fanout_targets_update_guard
BEFORE UPDATE ON agent.agent_run_control_fanout_targets
FOR EACH ROW EXECUTE FUNCTION agent.enforce_fanout_target_update();

-- Every B02.3 table is Tenant-qualified and fails closed when TenantContext is
-- missing or invalid. RLS is defense in depth; every query also carries Tenant.
ALTER TABLE agent.work_orders ENABLE ROW LEVEL SECURITY;
ALTER TABLE agent.work_orders FORCE ROW LEVEL SECURITY;
ALTER TABLE agent.agent_runs ENABLE ROW LEVEL SECURITY;
ALTER TABLE agent.agent_runs FORCE ROW LEVEL SECURITY;
ALTER TABLE agent.agent_runtime_runs ENABLE ROW LEVEL SECURITY;
ALTER TABLE agent.agent_runtime_runs FORCE ROW LEVEL SECURITY;
ALTER TABLE agent.runtime_invocations ENABLE ROW LEVEL SECURITY;
ALTER TABLE agent.runtime_invocations FORCE ROW LEVEL SECURITY;
ALTER TABLE agent.runtime_invocation_attempts ENABLE ROW LEVEL SECURITY;
ALTER TABLE agent.runtime_invocation_attempts FORCE ROW LEVEL SECURITY;
ALTER TABLE agent.work_order_control_requests ENABLE ROW LEVEL SECURITY;
ALTER TABLE agent.work_order_control_requests FORCE ROW LEVEL SECURITY;
ALTER TABLE agent.work_order_control_inputs ENABLE ROW LEVEL SECURITY;
ALTER TABLE agent.work_order_control_inputs FORCE ROW LEVEL SECURITY;
ALTER TABLE agent.platform_safety_controllers ENABLE ROW LEVEL SECURITY;
ALTER TABLE agent.platform_safety_controllers FORCE ROW LEVEL SECURITY;
ALTER TABLE agent.safety_trigger_evidence ENABLE ROW LEVEL SECURITY;
ALTER TABLE agent.safety_trigger_evidence FORCE ROW LEVEL SECURITY;
ALTER TABLE agent.child_agent_run_admission_decisions ENABLE ROW LEVEL SECURITY;
ALTER TABLE agent.child_agent_run_admission_decisions FORCE ROW LEVEL SECURITY;
ALTER TABLE agent.system_safety_controls ENABLE ROW LEVEL SECURITY;
ALTER TABLE agent.system_safety_controls FORCE ROW LEVEL SECURITY;
ALTER TABLE agent.agent_runtime_commands ENABLE ROW LEVEL SECURITY;
ALTER TABLE agent.agent_runtime_commands FORCE ROW LEVEL SECURITY;
ALTER TABLE agent.agent_run_control_fanouts ENABLE ROW LEVEL SECURITY;
ALTER TABLE agent.agent_run_control_fanouts FORCE ROW LEVEL SECURITY;
ALTER TABLE agent.agent_run_control_fanout_targets ENABLE ROW LEVEL SECURITY;
ALTER TABLE agent.agent_run_control_fanout_targets FORCE ROW LEVEL SECURITY;
ALTER TABLE agent.agent_run_control_fanout_versions ENABLE ROW LEVEL SECURITY;
ALTER TABLE agent.agent_run_control_fanout_versions FORCE ROW LEVEL SECURITY;
ALTER TABLE agent.agent_run_control_fanout_target_versions ENABLE ROW LEVEL SECURITY;
ALTER TABLE agent.agent_run_control_fanout_target_versions FORCE ROW LEVEL SECURITY;

-- +goose StatementBegin
DO $create_b023_rls$
DECLARE
    table_name text;
BEGIN
    FOREACH table_name IN ARRAY ARRAY[
        'work_orders', 'agent_runs', 'agent_runtime_runs', 'runtime_invocations',
        'runtime_invocation_attempts', 'work_order_control_requests',
        'work_order_control_inputs', 'platform_safety_controllers',
        'safety_trigger_evidence', 'child_agent_run_admission_decisions',
        'system_safety_controls', 'agent_runtime_commands',
        'agent_run_control_fanouts', 'agent_run_control_fanout_targets',
        'agent_run_control_fanout_versions', 'agent_run_control_fanout_target_versions'
    ] LOOP
        EXECUTE format(
            'CREATE POLICY %I ON agent.%I FOR ALL TO agent_app USING (' ||
            'tenant_id = CASE WHEN length(current_setting(''agent.tenant_id'', true)) BETWEEN 1 AND 200 ' ||
            'THEN current_setting(''agent.tenant_id'', true) ELSE NULL END) WITH CHECK (' ||
            'tenant_id = CASE WHEN length(current_setting(''agent.tenant_id'', true)) BETWEEN 1 AND 200 ' ||
            'THEN current_setting(''agent.tenant_id'', true) ELSE NULL END)',
            table_name || '_tenant_isolation', table_name
        );
    END LOOP;
END
$create_b023_rls$;
-- +goose StatementEnd

ALTER TABLE agent.work_orders OWNER TO agent_migrator;
ALTER TABLE agent.agent_runs OWNER TO agent_migrator;
ALTER TABLE agent.agent_runtime_runs OWNER TO agent_migrator;
ALTER TABLE agent.runtime_invocations OWNER TO agent_migrator;
ALTER TABLE agent.runtime_invocation_attempts OWNER TO agent_migrator;
ALTER TABLE agent.work_order_control_requests OWNER TO agent_migrator;
ALTER TABLE agent.work_order_control_inputs OWNER TO agent_migrator;
ALTER TABLE agent.platform_safety_controllers OWNER TO agent_migrator;
ALTER TABLE agent.safety_trigger_evidence OWNER TO agent_migrator;
ALTER TABLE agent.child_agent_run_admission_decisions OWNER TO agent_migrator;
ALTER TABLE agent.system_safety_controls OWNER TO agent_migrator;
ALTER TABLE agent.agent_runtime_commands OWNER TO agent_migrator;
ALTER TABLE agent.agent_run_control_fanouts OWNER TO agent_migrator;
ALTER TABLE agent.agent_run_control_fanout_targets OWNER TO agent_migrator;
ALTER TABLE agent.agent_run_control_fanout_versions OWNER TO agent_migrator;
ALTER TABLE agent.agent_run_control_fanout_target_versions OWNER TO agent_migrator;

GRANT SELECT ON TABLE
    agent.work_orders, agent.agent_runs, agent.agent_runtime_runs,
    agent.runtime_invocations, agent.runtime_invocation_attempts,
    agent.work_order_control_requests, agent.work_order_control_inputs,
    agent.platform_safety_controllers, agent.safety_trigger_evidence,
    agent.child_agent_run_admission_decisions, agent.system_safety_controls,
    agent.agent_runtime_commands, agent.agent_run_control_fanouts,
    agent.agent_run_control_fanout_targets, agent.agent_run_control_fanout_versions,
    agent.agent_run_control_fanout_target_versions
TO agent_app;

GRANT INSERT (
    tenant_id, work_order_id, state, active_work_version,
    child_admission_open, created_at, updated_at
) ON agent.work_orders TO agent_app;
GRANT INSERT (
    tenant_id, work_order_id, agent_run_id, run_kind,
    required_for_work_order_completion, state, created_at, updated_at
) ON agent.agent_runs TO agent_app;
GRANT INSERT (
    tenant_id, work_order_id, agent_run_id, runtime_run_id,
    state, created_at, updated_at
) ON agent.agent_runtime_runs TO agent_app;
GRANT INSERT (
    tenant_id, work_order_id, runtime_run_id, invocation_id,
    request_digest, created_at, updated_at
) ON agent.runtime_invocations TO agent_app;
GRANT UPDATE (
    last_attempt_number, current_fencing_token, updated_at
) ON agent.runtime_invocations TO agent_app;
GRANT INSERT (
    tenant_id, work_order_id, runtime_run_id, invocation_id,
    invocation_attempt_id, attempt_number, fencing_token, created_at
) ON agent.runtime_invocation_attempts TO agent_app;
GRANT INSERT (
    tenant_id, work_order_id, control_request_id, request_digest, action,
    expected_active_work_version, input_id, input_content_digest,
    approval_id, approval_decision, approval_comment, accepted_at
) ON agent.work_order_control_requests TO agent_app;
GRANT INSERT (
    tenant_id, work_order_id, control_request_id, input_id,
    input_message_id, content_digest, accepted_at
) ON agent.work_order_control_inputs TO agent_app;
GRANT INSERT (initial_available_at) ON agent.outbox_messages TO agent_app;
-- Safety Controller identity and trigger evidence are written only by their
-- future authoritative parent slices. B02.3's Application role consumes them.
GRANT INSERT (
    tenant_id, work_order_id, decision_id, decision_digest,
    spawn_request_id, spawn_request_digest, parent_agent_run_id,
    outcome, reason_codes, child_agent_run_id, runtime_run_id, decided_at
) ON agent.child_agent_run_admission_decisions TO agent_app;
GRANT INSERT (
    tenant_id, work_order_id, runtime_run_id, safety_control_id,
    action, reason, evidence_contract_id, evidence_id, evidence_digest,
    observed_at, evidence_admitted_at, issued_by, issuer_subject_id,
    issuer_admitted_at, issued_at, control_digest,
    outbox_message_id, outbox_payload_digest, outbox_destination,
    outbox_available_at, outbox_created_at
) ON agent.system_safety_controls TO agent_app;
GRANT INSERT (
    tenant_id, work_order_id, command_id, command_digest, runtime_run_id,
    command_sequence, type, authorized_control_request_id,
    system_safety_control_id, system_safety_control_digest,
    input_id, input_content_digest, approval_id, approval_decision,
    approval_comment, spawn_request_id, child_admission_decision_id,
    child_admission_decision_digest, spawn_outcome, spawn_reason_codes,
    child_agent_run_id, reason, invocation_id, invocation_attempt_id,
    fencing_token, idempotency_key, deadline_at, created_at,
    outbox_message_id, outbox_payload_digest, outbox_destination,
    outbox_available_at, outbox_created_at
) ON agent.agent_runtime_commands TO agent_app;
GRANT INSERT (
    tenant_id, work_order_id, fanout_id, action, authority_kind,
    authority_id, authority_digest, expected_active_work_version,
    control_request_id,
    safety_evidence_contract_id, safety_evidence_id,
    latest_version, latest_digest, created_at, updated_at
) ON agent.agent_run_control_fanouts TO agent_app;
GRANT INSERT (
    tenant_id, work_order_id, fanout_id, authority_kind, agent_run_id,
    runtime_run_id, target_fencing_token, system_safety_control_id,
    system_safety_control_digest, command_id, control_state, updated_at
) ON agent.agent_run_control_fanout_targets TO agent_app;
GRANT INSERT (
    tenant_id, work_order_id, fanout_id, fanout_version,
    previous_fanout_version, previous_fanout_digest,
    fanout_digest, action, authority_kind,
    authority_id, authority_digest, created_at, updated_at
) ON agent.agent_run_control_fanout_versions TO agent_app;
GRANT INSERT (
    tenant_id, fanout_id, fanout_version, authority_kind, agent_run_id,
    runtime_run_id, target_fencing_token, system_safety_control_id,
    system_safety_control_digest, control_state
) ON agent.agent_run_control_fanout_target_versions TO agent_app;

GRANT UPDATE (
    active_work_version, child_admission_open, updated_at
) ON agent.work_orders TO agent_app;
GRANT UPDATE (
    last_command_sequence, current_fencing_token, updated_at
) ON agent.agent_runtime_runs TO agent_app;
GRANT UPDATE (latest_version, latest_digest, updated_at)
    ON agent.agent_run_control_fanouts TO agent_app;
GRANT UPDATE (
    control_state, claim_fencing_token, claim_worker_id, claim_expires_at, updated_at
) ON agent.agent_run_control_fanout_targets TO agent_app;

RESET ROLE;

-- +goose Down
SET ROLE agent_migrator;

ALTER TABLE agent.work_orders NO FORCE ROW LEVEL SECURITY;
ALTER TABLE agent.agent_runs NO FORCE ROW LEVEL SECURITY;
ALTER TABLE agent.agent_runtime_runs NO FORCE ROW LEVEL SECURITY;
ALTER TABLE agent.runtime_invocations NO FORCE ROW LEVEL SECURITY;
ALTER TABLE agent.runtime_invocation_attempts NO FORCE ROW LEVEL SECURITY;
ALTER TABLE agent.work_order_control_requests NO FORCE ROW LEVEL SECURITY;
ALTER TABLE agent.work_order_control_inputs NO FORCE ROW LEVEL SECURITY;
ALTER TABLE agent.platform_safety_controllers NO FORCE ROW LEVEL SECURITY;
ALTER TABLE agent.safety_trigger_evidence NO FORCE ROW LEVEL SECURITY;
ALTER TABLE agent.child_agent_run_admission_decisions NO FORCE ROW LEVEL SECURITY;
ALTER TABLE agent.system_safety_controls NO FORCE ROW LEVEL SECURITY;
ALTER TABLE agent.agent_runtime_commands NO FORCE ROW LEVEL SECURITY;
ALTER TABLE agent.agent_run_control_fanouts NO FORCE ROW LEVEL SECURITY;
ALTER TABLE agent.agent_run_control_fanout_targets NO FORCE ROW LEVEL SECURITY;
ALTER TABLE agent.agent_run_control_fanout_versions NO FORCE ROW LEVEL SECURITY;
ALTER TABLE agent.agent_run_control_fanout_target_versions NO FORCE ROW LEVEL SECURITY;

-- +goose StatementBegin
DO $safe_empty_down$
BEGIN
    IF EXISTS (SELECT 1 FROM agent.work_orders)
       OR EXISTS (SELECT 1 FROM agent.agent_runs)
       OR EXISTS (SELECT 1 FROM agent.agent_runtime_runs)
       OR EXISTS (SELECT 1 FROM agent.runtime_invocations)
       OR EXISTS (SELECT 1 FROM agent.runtime_invocation_attempts)
       OR EXISTS (SELECT 1 FROM agent.work_order_control_requests)
       OR EXISTS (SELECT 1 FROM agent.work_order_control_inputs)
       OR EXISTS (SELECT 1 FROM agent.platform_safety_controllers)
       OR EXISTS (SELECT 1 FROM agent.safety_trigger_evidence)
       OR EXISTS (SELECT 1 FROM agent.child_agent_run_admission_decisions)
       OR EXISTS (SELECT 1 FROM agent.system_safety_controls)
       OR EXISTS (SELECT 1 FROM agent.agent_runtime_commands)
       OR EXISTS (SELECT 1 FROM agent.agent_run_control_fanouts)
       OR EXISTS (SELECT 1 FROM agent.agent_run_control_fanout_targets)
       OR EXISTS (SELECT 1 FROM agent.agent_run_control_fanout_versions)
       OR EXISTS (SELECT 1 FROM agent.agent_run_control_fanout_target_versions) THEN
        RAISE EXCEPTION USING
            ERRCODE = '0A000',
            MESSAGE = '00003_postgresql_runtime_control_safety_ledgers contains authoritative data and is forward-only';
    END IF;
END
$safe_empty_down$;
-- +goose StatementEnd

DROP TABLE agent.agent_run_control_fanout_target_versions;
ALTER TABLE agent.agent_run_control_fanouts
    DROP CONSTRAINT agent_run_control_fanouts_latest_version_fk;
DROP TABLE agent.agent_run_control_fanout_versions;
DROP TABLE agent.agent_run_control_fanout_targets;
DROP TABLE agent.agent_run_control_fanouts;
DROP TABLE agent.agent_runtime_commands;
DROP TABLE agent.system_safety_controls;
ALTER TABLE agent.outbox_messages
    DROP CONSTRAINT outbox_messages_control_delivery_binding_uk,
    DROP CONSTRAINT outbox_messages_control_binding_uk,
    DROP CONSTRAINT outbox_messages_initial_available_at_check;
DROP TABLE agent.child_agent_run_admission_decisions;
DROP TABLE agent.safety_trigger_evidence;
DROP TABLE agent.platform_safety_controllers;
ALTER TABLE agent.work_order_control_requests
    DROP CONSTRAINT work_order_control_requests_input_fk;
DROP TABLE agent.work_order_control_inputs;
DROP TABLE agent.work_order_control_requests;
DROP TABLE agent.runtime_invocation_attempts;
DROP TABLE agent.runtime_invocations;
DROP TABLE agent.agent_runtime_runs;
DROP TABLE agent.agent_runs;
DROP TABLE agent.work_orders;
DROP FUNCTION agent.enforce_fanout_target_update();
DROP FUNCTION agent.enforce_fanout_version_update();
DROP FUNCTION agent.enforce_invocation_attempt_cursor_update();
DROP FUNCTION agent.enforce_open_work_order_admission();
DROP FUNCTION agent.enforce_runtime_command_cursor_update();
DROP FUNCTION agent.enforce_work_order_control_update();
DROP FUNCTION agent.child_admission_reason_codes_key(varchar[]);
DROP FUNCTION agent.valid_child_admission_reason_codes(varchar, varchar[]);

RESET ROLE;
