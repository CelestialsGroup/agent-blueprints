CREATE TABLE provider_metadata (
    singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
    provider_revision_id TEXT NOT NULL,
    runtime_revision TEXT NOT NULL,
    configuration_digest TEXT NOT NULL CHECK (length(configuration_digest) = 71),
    configured_at TEXT NOT NULL
) STRICT;

CREATE TABLE runtime_runs (
    runtime_run_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    conversation_id TEXT NOT NULL,
    work_order_id TEXT NOT NULL,
    workflow_run_id TEXT NOT NULL,
    agent_run_id TEXT NOT NULL,
    start_request_digest TEXT NOT NULL CHECK (length(start_request_digest) = 71),
    run_manifest_digest TEXT NOT NULL CHECK (length(run_manifest_digest) = 71),
    runtime_authorization_digest TEXT NOT NULL CHECK (length(runtime_authorization_digest) = 71),
    workspace_revision_id TEXT NOT NULL,
    workspace_revision_digest TEXT NOT NULL CHECK (length(workspace_revision_digest) = 71),
    status TEXT NOT NULL CHECK (status IN (
        'accepted', 'running', 'waiting_input', 'waiting_approval', 'paused',
        'cancel_requested', 'succeeded', 'failed', 'cancelled', 'outcome_unknown'
    )),
    observed_fencing_token INTEGER NOT NULL CHECK (observed_fencing_token >= 1),
    last_command_sequence INTEGER NOT NULL DEFAULT 0 CHECK (last_command_sequence >= 0),
    last_event_sequence INTEGER NOT NULL DEFAULT 0 CHECK (last_event_sequence >= 0),
    earliest_event_sequence INTEGER NOT NULL DEFAULT 1 CHECK (earliest_event_sequence >= 1),
    checkpoint_manifest_json TEXT,
    cancellation_evidence_reference TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    completed_at TEXT
) STRICT;

CREATE TABLE start_idempotency (
    idempotency_key TEXT PRIMARY KEY,
    request_digest TEXT NOT NULL CHECK (length(request_digest) = 71),
    runtime_run_id TEXT NOT NULL UNIQUE REFERENCES runtime_runs(runtime_run_id) ON DELETE RESTRICT,
    accepted_at TEXT NOT NULL
) STRICT;

CREATE TABLE consumed_mutation_jtis (
    issuer TEXT NOT NULL,
    jti TEXT NOT NULL,
    operation TEXT NOT NULL CHECK (operation IN ('start', 'submit_command')),
    request_digest TEXT NOT NULL CHECK (length(request_digest) = 71),
    runtime_run_id TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    consumed_at TEXT NOT NULL,
    PRIMARY KEY (issuer, jti)
) STRICT;

CREATE TABLE runtime_commands (
    runtime_run_id TEXT NOT NULL REFERENCES runtime_runs(runtime_run_id) ON DELETE RESTRICT,
    command_id TEXT NOT NULL,
    command_digest TEXT NOT NULL CHECK (length(command_digest) = 71),
    command_sequence INTEGER NOT NULL CHECK (command_sequence >= 1),
    type TEXT NOT NULL CHECK (type IN ('pause', 'resume', 'cancel', 'checkpoint')),
    invocation_id TEXT NOT NULL,
    invocation_attempt_id TEXT NOT NULL,
    fencing_token INTEGER NOT NULL CHECK (fencing_token >= 1),
    idempotency_key TEXT NOT NULL,
    authority_mode TEXT NOT NULL CHECK (authority_mode IN ('execution', 'safety_control')),
    authorized_control_request_id TEXT,
    system_safety_control_id TEXT,
    system_safety_control_digest TEXT,
    deadline_at TEXT NOT NULL,
    accepted_at TEXT NOT NULL,
    PRIMARY KEY (runtime_run_id, command_id),
    UNIQUE (runtime_run_id, command_sequence),
    UNIQUE (runtime_run_id, idempotency_key)
) STRICT;

CREATE TABLE runtime_events (
    runtime_run_id TEXT NOT NULL REFERENCES runtime_runs(runtime_run_id) ON DELETE RESTRICT,
    event_sequence INTEGER NOT NULL CHECK (event_sequence >= 1),
    event_id TEXT NOT NULL,
    type TEXT NOT NULL,
    occurred_at TEXT NOT NULL,
    data_version INTEGER NOT NULL CHECK (data_version = 1),
    data_json TEXT NOT NULL,
    source_cursor TEXT NOT NULL,
    PRIMARY KEY (runtime_run_id, event_sequence),
    UNIQUE (runtime_run_id, event_id)
) STRICT;

CREATE TABLE checkpoint_manifests (
    checkpoint_id TEXT PRIMARY KEY,
    runtime_run_id TEXT NOT NULL REFERENCES runtime_runs(runtime_run_id) ON DELETE RESTRICT,
    command_id TEXT NOT NULL,
    manifest_digest TEXT NOT NULL CHECK (length(manifest_digest) = 71),
    manifest_json TEXT NOT NULL,
    content_digest TEXT NOT NULL CHECK (length(content_digest) = 71),
    content_reference TEXT NOT NULL,
    size_bytes INTEGER NOT NULL CHECK (size_bytes >= 0),
    created_at TEXT NOT NULL,
    UNIQUE (runtime_run_id, command_id),
    UNIQUE (runtime_run_id, manifest_digest)
) STRICT;

CREATE TABLE execution_work (
    work_id TEXT PRIMARY KEY,
    runtime_run_id TEXT NOT NULL REFERENCES runtime_runs(runtime_run_id) ON DELETE RESTRICT,
    kind TEXT NOT NULL CHECK (kind IN ('start', 'cancel', 'checkpoint')),
    command_id TEXT,
    state TEXT NOT NULL CHECK (state IN ('pending', 'processing', 'completed')),
    lease_owner TEXT,
    lease_token INTEGER NOT NULL DEFAULT 0 CHECK (lease_token >= 0),
    lease_expires_at TEXT,
    attempt_count INTEGER NOT NULL DEFAULT 0 CHECK (attempt_count >= 0),
    restore_checkpoint_json TEXT,
    last_error_code TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    completed_at TEXT,
    UNIQUE (runtime_run_id, kind, command_id)
) STRICT;

CREATE INDEX execution_work_claim_idx
    ON execution_work(state, lease_expires_at, created_at, work_id);
CREATE INDEX runtime_events_read_idx
    ON runtime_events(runtime_run_id, event_sequence);
