CREATE TABLE provider_security_metadata (
    singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
    security_configuration_digest TEXT NOT NULL CHECK (length(security_configuration_digest) = 71),
    contract_source_revision TEXT NOT NULL CHECK (length(contract_source_revision) = 64),
    contract_manifest_digest TEXT NOT NULL CHECK (length(contract_manifest_digest) = 71),
    runtime_suite_digest TEXT NOT NULL CHECK (length(runtime_suite_digest) = 71),
    schema_closure_digest TEXT NOT NULL CHECK (length(schema_closure_digest) = 71),
    configured_at TEXT NOT NULL
) STRICT;

CREATE TABLE runtime_security_bindings (
    runtime_run_id TEXT PRIMARY KEY REFERENCES runtime_runs(runtime_run_id) ON DELETE RESTRICT,
    tenant_id TEXT NOT NULL,
    provider_revision_id TEXT NOT NULL,
    agent_run_id TEXT NOT NULL,
    workflow_run_id TEXT NOT NULL,
    work_order_id TEXT NOT NULL,
    run_manifest_digest TEXT NOT NULL CHECK (length(run_manifest_digest) = 71),
    runtime_authorization_digest TEXT NOT NULL CHECK (length(runtime_authorization_digest) = 71),
    policy_decision_digest TEXT NOT NULL CHECK (length(policy_decision_digest) = 71),
    execution_budget_digest TEXT NOT NULL CHECK (length(execution_budget_digest) = 71),
    effective_permissions_digest TEXT NOT NULL CHECK (length(effective_permissions_digest) = 71),
    authorization_issued_at TEXT NOT NULL,
    authorization_expires_at TEXT NOT NULL,
    policy_decided_at TEXT NOT NULL,
    policy_expires_at TEXT NOT NULL,
    budget_created_at TEXT NOT NULL,
    budget_expires_at TEXT NOT NULL,
    commercial_authorization_expires_at TEXT NOT NULL,
    artifact_grants_not_before TEXT,
    artifact_grants_expire_at TEXT,
    bound_at TEXT NOT NULL,
    CHECK (
        (artifact_grants_not_before IS NULL AND artifact_grants_expire_at IS NULL)
        OR
        (artifact_grants_not_before IS NOT NULL AND artifact_grants_expire_at IS NOT NULL)
    )
) STRICT;
