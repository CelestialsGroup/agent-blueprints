-- +goose Up
SET ROLE agent_migrator;

-- WorkflowRun is the immutable PostgreSQL identity written only after the
-- orchestration adapter confirms that the durable execution exists. Native
-- namespace, endpoint, Run ID, and History remain adapter-private.
CREATE TABLE agent.workflow_runs (
    tenant_id varchar(200) NOT NULL,
    workflow_run_id varchar(200) NOT NULL,
    work_order_id varchar(200) NOT NULL,
    workflow_id varchar(200) NOT NULL,
    workflow_version varchar(200) NOT NULL,
    workflow_definition_build_id varchar(200) NOT NULL,
    workflow_definition_digest varchar(71) NOT NULL,
    orchestration_engine_id varchar(64) NOT NULL,
    orchestration_engine_version varchar(64) NOT NULL,
    workflow_execution_id varchar(200) NOT NULL,
    native_execution_reference_digest varchar(71) NOT NULL,
    worker_deployment varchar(200) NOT NULL,
    worker_build_id varchar(200) NOT NULL,
    versioning_behavior varchar(32) NOT NULL,
    orchestration_binding_digest varchar(71) NOT NULL,
    created_at timestamptz NOT NULL,
    CONSTRAINT workflow_runs_pk PRIMARY KEY (tenant_id, workflow_run_id),
    CONSTRAINT workflow_runs_identity_uk UNIQUE (workflow_run_id),
    CONSTRAINT workflow_runs_work_order_uk UNIQUE (tenant_id, work_order_id),
    CONSTRAINT workflow_runs_binding_digest_uk UNIQUE (orchestration_binding_digest),
    CONSTRAINT workflow_runs_work_order_fk FOREIGN KEY (tenant_id, work_order_id)
        REFERENCES agent.work_orders (tenant_id, work_order_id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT workflow_runs_ids_not_blank CHECK (
        tenant_id <> ''
        AND workflow_run_id <> ''
        AND work_order_id <> ''
        AND workflow_id <> ''
        AND workflow_version <> ''
        AND workflow_definition_build_id <> ''
        AND orchestration_engine_id <> ''
        AND orchestration_engine_version <> ''
        AND workflow_execution_id <> ''
        AND worker_deployment <> ''
        AND worker_build_id <> ''
    ),
    CONSTRAINT workflow_runs_digests CHECK (
        workflow_definition_digest COLLATE "C" ~ '^sha256:[0-9a-f]{64}$'
        AND native_execution_reference_digest COLLATE "C" ~ '^sha256:[0-9a-f]{64}$'
        AND orchestration_binding_digest COLLATE "C" ~ '^sha256:[0-9a-f]{64}$'
    ),
    CONSTRAINT workflow_runs_versioning_behavior CHECK (
        versioning_behavior IN ('pinned', 'compatible_upgrade')
    ),
    CONSTRAINT workflow_runs_created_at_finite CHECK (
        created_at > '-infinity'::timestamptz
        AND created_at < 'infinity'::timestamptz
    )
);

ALTER TABLE agent.workflow_runs ENABLE ROW LEVEL SECURITY;
ALTER TABLE agent.workflow_runs FORCE ROW LEVEL SECURITY;

CREATE POLICY workflow_runs_tenant_isolation
ON agent.workflow_runs
FOR ALL
TO agent_app
USING (
    tenant_id = CASE
        WHEN length(current_setting('agent.tenant_id', true)) BETWEEN 1 AND 200
        THEN current_setting('agent.tenant_id', true)
        ELSE NULL
    END
)
WITH CHECK (
    tenant_id = CASE
        WHEN length(current_setting('agent.tenant_id', true)) BETWEEN 1 AND 200
        THEN current_setting('agent.tenant_id', true)
        ELSE NULL
    END
);

ALTER TABLE agent.workflow_runs OWNER TO agent_migrator;
REVOKE ALL ON TABLE agent.workflow_runs FROM PUBLIC, agent_app;
GRANT SELECT ON TABLE agent.workflow_runs TO agent_app;
GRANT INSERT (
    tenant_id, workflow_run_id, work_order_id,
    workflow_id, workflow_version, workflow_definition_build_id,
    workflow_definition_digest, orchestration_engine_id,
    orchestration_engine_version, workflow_execution_id,
    native_execution_reference_digest, worker_deployment, worker_build_id,
    versioning_behavior, orchestration_binding_digest, created_at
) ON agent.workflow_runs TO agent_app;

RESET ROLE;

-- +goose Down
SET ROLE agent_migrator;

ALTER TABLE agent.workflow_runs NO FORCE ROW LEVEL SECURITY;

-- +goose StatementBegin
DO $safe_empty_down$
BEGIN
    IF EXISTS (SELECT 1 FROM agent.workflow_runs) THEN
        RAISE EXCEPTION USING
            ERRCODE = '0A000',
            MESSAGE = '00004_temporal_orchestration_replay_foundation contains authoritative data and is forward-only';
    END IF;
END
$safe_empty_down$;
-- +goose StatementEnd

DROP TABLE agent.workflow_runs;

RESET ROLE;
