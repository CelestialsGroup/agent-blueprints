-- name: InsertWorkOrderAuthority :one
INSERT INTO agent.work_orders (
    tenant_id, work_order_id, state, active_work_version,
    child_admission_open, created_at, updated_at
) VALUES (
    sqlc.arg(tenant_id), sqlc.arg(work_order_id), sqlc.arg(state),
    sqlc.arg(active_work_version), sqlc.arg(child_admission_open),
    sqlc.arg(created_at), sqlc.arg(created_at)
)
ON CONFLICT DO NOTHING
RETURNING *;

-- name: GetWorkOrderAuthority :one
SELECT * FROM agent.work_orders
WHERE tenant_id = sqlc.arg(tenant_id)
  AND work_order_id = sqlc.arg(work_order_id);

-- name: InsertAgentRunAuthority :one
INSERT INTO agent.agent_runs (
    tenant_id, work_order_id, agent_run_id, run_kind,
    required_for_work_order_completion, state, created_at, updated_at
) VALUES (
    sqlc.arg(tenant_id), sqlc.arg(work_order_id), sqlc.arg(agent_run_id),
    sqlc.arg(run_kind), sqlc.arg(required_for_work_order_completion),
    sqlc.arg(state), sqlc.arg(created_at), sqlc.arg(created_at)
)
ON CONFLICT DO NOTHING
RETURNING *;

-- name: GetAgentRunAuthority :one
SELECT * FROM agent.agent_runs
WHERE tenant_id = sqlc.arg(tenant_id)
  AND agent_run_id = sqlc.arg(agent_run_id);

-- name: InsertAgentRuntimeRunAuthority :one
INSERT INTO agent.agent_runtime_runs (
    tenant_id, work_order_id, agent_run_id, runtime_run_id,
    state, created_at, updated_at
) VALUES (
    sqlc.arg(tenant_id), sqlc.arg(work_order_id), sqlc.arg(agent_run_id),
    sqlc.arg(runtime_run_id), sqlc.arg(state), sqlc.arg(created_at), sqlc.arg(created_at)
)
ON CONFLICT DO NOTHING
RETURNING *;

-- name: GetAgentRuntimeRunAuthority :one
SELECT * FROM agent.agent_runtime_runs
WHERE tenant_id = sqlc.arg(tenant_id)
  AND runtime_run_id = sqlc.arg(runtime_run_id);

-- name: InsertRuntimeInvocationAuthority :one
INSERT INTO agent.runtime_invocations (
    tenant_id, work_order_id, runtime_run_id, invocation_id,
    request_digest, created_at, updated_at
) VALUES (
    sqlc.arg(tenant_id), sqlc.arg(work_order_id), sqlc.arg(runtime_run_id),
    sqlc.arg(invocation_id), sqlc.arg(request_digest),
    sqlc.arg(created_at), sqlc.arg(created_at)
)
ON CONFLICT DO NOTHING
RETURNING *;

-- name: GetRuntimeInvocationAuthority :one
SELECT * FROM agent.runtime_invocations
WHERE tenant_id = sqlc.arg(tenant_id)
  AND invocation_id = sqlc.arg(invocation_id);

-- name: LockRuntimeInvocationForAttempt :one
SELECT * FROM agent.runtime_invocations
WHERE tenant_id = sqlc.arg(tenant_id)
  AND invocation_id = sqlc.arg(invocation_id)
FOR UPDATE;

-- name: AdvanceRuntimeInvocationAttemptCursor :one
UPDATE agent.runtime_invocations
SET last_attempt_number = sqlc.arg(attempt_number),
    current_fencing_token = sqlc.arg(fencing_token),
    updated_at = sqlc.arg(updated_at)
WHERE tenant_id = sqlc.arg(tenant_id)
  AND invocation_id = sqlc.arg(invocation_id)
  AND last_attempt_number = sqlc.arg(attempt_number) - 1
  AND current_fencing_token < sqlc.arg(fencing_token)
RETURNING *;

-- name: InsertRuntimeInvocationAttemptAuthority :one
INSERT INTO agent.runtime_invocation_attempts (
    tenant_id, work_order_id, runtime_run_id, invocation_id,
    invocation_attempt_id, attempt_number, fencing_token, created_at
) VALUES (
    sqlc.arg(tenant_id), sqlc.arg(work_order_id), sqlc.arg(runtime_run_id),
    sqlc.arg(invocation_id), sqlc.arg(invocation_attempt_id),
    sqlc.arg(attempt_number), sqlc.arg(fencing_token), sqlc.arg(created_at)
)
ON CONFLICT DO NOTHING
RETURNING *;

-- name: GetRuntimeInvocationAttemptAuthority :one
SELECT * FROM agent.runtime_invocation_attempts
WHERE tenant_id = sqlc.arg(tenant_id)
  AND invocation_attempt_id = sqlc.arg(invocation_attempt_id);

-- name: InsertWorkOrderControlRequestAuthority :one
INSERT INTO agent.work_order_control_requests (
    tenant_id, work_order_id, control_request_id, request_digest, action,
    expected_active_work_version, input_id, input_content_digest,
    approval_id, approval_decision, approval_comment, accepted_at
) VALUES (
    sqlc.arg(tenant_id), sqlc.arg(work_order_id), sqlc.arg(control_request_id),
    sqlc.arg(request_digest), sqlc.arg(action), sqlc.arg(expected_active_work_version),
    sqlc.narg(input_id), sqlc.narg(input_content_digest), sqlc.narg(approval_id),
    sqlc.narg(approval_decision), sqlc.arg(approval_comment), sqlc.arg(accepted_at)
)
ON CONFLICT DO NOTHING
RETURNING *;

-- name: GetWorkOrderControlRequestAuthority :one
SELECT * FROM agent.work_order_control_requests
WHERE tenant_id = sqlc.arg(tenant_id)
  AND control_request_id = sqlc.arg(control_request_id);

-- name: InsertWorkOrderControlInputAuthority :one
INSERT INTO agent.work_order_control_inputs (
    tenant_id, work_order_id, control_request_id, input_id,
    input_message_id, content_digest, accepted_at
) VALUES (
    sqlc.arg(tenant_id), sqlc.arg(work_order_id), sqlc.arg(control_request_id),
    sqlc.arg(input_id), sqlc.arg(input_message_id), sqlc.arg(content_digest),
    sqlc.arg(accepted_at)
)
ON CONFLICT DO NOTHING
RETURNING *;

-- name: GetWorkOrderControlInputAuthority :one
SELECT * FROM agent.work_order_control_inputs
WHERE tenant_id = sqlc.arg(tenant_id)
  AND control_request_id = sqlc.arg(control_request_id);

-- name: GetPlatformSafetyControllerAuthority :one
SELECT * FROM agent.platform_safety_controllers
WHERE tenant_id = sqlc.arg(tenant_id)
  AND issuer_subject_id = sqlc.arg(issuer_subject_id);

-- name: GetSafetyTriggerEvidenceAuthority :one
SELECT * FROM agent.safety_trigger_evidence
WHERE tenant_id = sqlc.arg(tenant_id)
  AND evidence_contract_id = sqlc.arg(evidence_contract_id)
  AND evidence_id = sqlc.arg(evidence_id);

-- name: InsertChildAdmissionDecisionAuthority :one
INSERT INTO agent.child_agent_run_admission_decisions (
    tenant_id, work_order_id, decision_id, decision_digest,
    spawn_request_id, spawn_request_digest, parent_agent_run_id,
    outcome, reason_codes, child_agent_run_id, runtime_run_id, decided_at
) VALUES (
    sqlc.arg(tenant_id), sqlc.arg(work_order_id), sqlc.arg(decision_id),
    sqlc.arg(decision_digest), sqlc.arg(spawn_request_id),
    sqlc.arg(spawn_request_digest), sqlc.arg(parent_agent_run_id),
    sqlc.arg(outcome), sqlc.arg(reason_codes), sqlc.narg(child_agent_run_id),
    sqlc.narg(runtime_run_id), sqlc.arg(decided_at)
)
ON CONFLICT DO NOTHING
RETURNING *;

-- name: GetChildAdmissionDecisionAuthority :one
SELECT * FROM agent.child_agent_run_admission_decisions
WHERE tenant_id = sqlc.arg(tenant_id)
  AND decision_id = sqlc.arg(decision_id);

-- name: InsertSystemSafetyControl :one
INSERT INTO agent.system_safety_controls (
    tenant_id, work_order_id, runtime_run_id, safety_control_id,
    action, reason, evidence_contract_id, evidence_id, evidence_digest,
    observed_at, evidence_admitted_at, issued_by, issuer_subject_id,
    issuer_admitted_at, issued_at, control_digest,
    outbox_message_id, outbox_payload_digest, outbox_destination,
    outbox_available_at, outbox_created_at
) VALUES (
    sqlc.arg(tenant_id), sqlc.arg(work_order_id), sqlc.arg(runtime_run_id),
    sqlc.arg(safety_control_id), sqlc.arg(action), sqlc.arg(reason),
    sqlc.arg(evidence_contract_id), sqlc.arg(evidence_id),
    sqlc.arg(evidence_digest), sqlc.arg(observed_at),
    sqlc.arg(evidence_admitted_at), sqlc.arg(issued_by),
    sqlc.arg(issuer_subject_id), sqlc.arg(issuer_admitted_at),
    sqlc.arg(issued_at), sqlc.arg(control_digest),
    sqlc.arg(outbox_message_id), sqlc.arg(outbox_payload_digest),
    sqlc.arg(outbox_destination), sqlc.arg(outbox_available_at),
    sqlc.arg(outbox_created_at)
)
ON CONFLICT DO NOTHING
RETURNING *;

-- name: GetSystemSafetyControl :one
SELECT * FROM agent.system_safety_controls
WHERE tenant_id = sqlc.arg(tenant_id)
  AND safety_control_id = sqlc.arg(safety_control_id);

-- name: LockRuntimeRunForCommand :one
SELECT * FROM agent.agent_runtime_runs
WHERE tenant_id = sqlc.arg(tenant_id)
  AND runtime_run_id = sqlc.arg(runtime_run_id)
FOR UPDATE;

-- name: InsertAgentRuntimeCommand :one
INSERT INTO agent.agent_runtime_commands (
    tenant_id, work_order_id, command_id, command_digest, runtime_run_id,
    command_sequence, type, authorized_control_request_id,
    system_safety_control_id, system_safety_control_digest,
    input_id, input_content_digest, approval_id, approval_decision,
    approval_comment, spawn_request_id, child_admission_decision_id,
    child_admission_decision_digest, spawn_outcome, spawn_reason_codes,
    child_agent_run_id,
    reason, invocation_id, invocation_attempt_id, fencing_token,
    idempotency_key, deadline_at, created_at,
    outbox_message_id, outbox_payload_digest, outbox_destination,
    outbox_available_at, outbox_created_at
) VALUES (
    sqlc.arg(tenant_id), sqlc.arg(work_order_id), sqlc.arg(command_id),
    sqlc.arg(command_digest), sqlc.arg(runtime_run_id),
    sqlc.arg(command_sequence), sqlc.arg(type),
    sqlc.narg(authorized_control_request_id), sqlc.narg(system_safety_control_id),
    sqlc.narg(system_safety_control_digest), sqlc.narg(input_id),
    sqlc.narg(input_content_digest), sqlc.narg(approval_id),
    sqlc.narg(approval_decision), sqlc.arg(approval_comment),
    sqlc.narg(spawn_request_id), sqlc.narg(child_admission_decision_id),
    sqlc.narg(child_admission_decision_digest), sqlc.narg(spawn_outcome),
    sqlc.narg(spawn_reason_codes), sqlc.narg(child_agent_run_id),
    sqlc.narg(reason), sqlc.arg(invocation_id),
    sqlc.arg(invocation_attempt_id), sqlc.arg(fencing_token),
    sqlc.arg(idempotency_key), sqlc.arg(deadline_at), sqlc.arg(created_at),
    sqlc.arg(outbox_message_id), sqlc.arg(outbox_payload_digest),
    sqlc.arg(outbox_destination), sqlc.arg(outbox_available_at),
    sqlc.arg(outbox_created_at)
)
ON CONFLICT DO NOTHING
RETURNING *;

-- name: GetAgentRuntimeCommand :one
SELECT * FROM agent.agent_runtime_commands
WHERE tenant_id = sqlc.arg(tenant_id)
  AND command_id = sqlc.arg(command_id);

-- name: AdvanceRuntimeCommandCursor :one
UPDATE agent.agent_runtime_runs
SET last_command_sequence = sqlc.arg(command_sequence),
    current_fencing_token = sqlc.arg(fencing_token),
    updated_at = sqlc.arg(updated_at)
WHERE tenant_id = sqlc.arg(tenant_id)
  AND runtime_run_id = sqlc.arg(runtime_run_id)
  AND last_command_sequence = sqlc.arg(command_sequence) - 1
  AND current_fencing_token < sqlc.arg(fencing_token)
  AND state NOT IN ('succeeded', 'failed', 'cancelled')
RETURNING *;

-- name: LockWorkOrder :one
SELECT * FROM agent.work_orders
WHERE tenant_id = sqlc.arg(tenant_id)
  AND work_order_id = sqlc.arg(work_order_id)
FOR UPDATE;

-- name: CloseWorkOrderChildAdmission :one
UPDATE agent.work_orders
SET child_admission_open = false,
    active_work_version = active_work_version + 1,
    updated_at = sqlc.arg(updated_at)
WHERE tenant_id = sqlc.arg(tenant_id)
  AND work_order_id = sqlc.arg(work_order_id)
  AND active_work_version = sqlc.arg(expected_active_work_version)
  AND state NOT IN ('completed', 'partial', 'failed', 'cancelled')
RETURNING *;

-- name: ListActiveAgentRunsForFanout :many
SELECT agent_run_id
FROM agent.agent_runs
WHERE tenant_id = sqlc.arg(tenant_id)
  AND work_order_id = sqlc.arg(work_order_id)
  AND state NOT IN ('succeeded', 'failed', 'cancelled')
ORDER BY agent_run_id;

-- name: ListActiveRuntimeTargetsForFanout :many
SELECT
    agent_runs.agent_run_id,
    runtime_runs.runtime_run_id,
    runtime_runs.current_fencing_token
FROM agent.agent_runs AS agent_runs
JOIN agent.agent_runtime_runs AS runtime_runs
  ON runtime_runs.tenant_id = agent_runs.tenant_id
 AND runtime_runs.work_order_id = agent_runs.work_order_id
 AND runtime_runs.agent_run_id = agent_runs.agent_run_id
WHERE agent_runs.tenant_id = sqlc.arg(tenant_id)
  AND agent_runs.work_order_id = sqlc.arg(work_order_id)
  AND agent_runs.state NOT IN ('succeeded', 'failed', 'cancelled')
  AND runtime_runs.state NOT IN ('succeeded', 'failed', 'cancelled')
ORDER BY agent_runs.agent_run_id, runtime_runs.runtime_run_id
FOR UPDATE OF runtime_runs;

-- name: InsertAgentRunControlFanout :one
INSERT INTO agent.agent_run_control_fanouts (
    tenant_id, work_order_id, fanout_id, action, authority_kind,
    authority_id, authority_digest, expected_active_work_version,
    control_request_id,
    safety_evidence_contract_id, safety_evidence_id,
    latest_version, latest_digest, created_at, updated_at
) VALUES (
    sqlc.arg(tenant_id), sqlc.arg(work_order_id), sqlc.arg(fanout_id),
    sqlc.arg(action), sqlc.arg(authority_kind), sqlc.arg(authority_id),
    sqlc.arg(authority_digest), sqlc.arg(expected_active_work_version),
    sqlc.narg(control_request_id),
    sqlc.narg(safety_evidence_contract_id), sqlc.narg(safety_evidence_id),
    1, sqlc.arg(fanout_digest), sqlc.arg(created_at), sqlc.arg(created_at)
)
ON CONFLICT DO NOTHING
RETURNING *;

-- name: GetAgentRunControlFanout :one
SELECT * FROM agent.agent_run_control_fanouts
WHERE tenant_id = sqlc.arg(tenant_id)
  AND fanout_id = sqlc.arg(fanout_id);

-- name: GetAgentRunControlFanoutVersion :one
SELECT * FROM agent.agent_run_control_fanout_versions
WHERE tenant_id = sqlc.arg(tenant_id)
  AND fanout_id = sqlc.arg(fanout_id)
  AND fanout_version = sqlc.arg(fanout_version);

-- name: ListAgentRunControlFanoutVersionTargets :many
SELECT
    versions.tenant_id,
    versions.fanout_id,
    versions.fanout_version,
    versions.authority_kind,
    versions.agent_run_id,
    versions.runtime_run_id,
    versions.target_fencing_token,
    versions.system_safety_control_id,
    versions.system_safety_control_digest,
    versions.control_state,
    targets.command_id
FROM agent.agent_run_control_fanout_target_versions AS versions
JOIN agent.agent_run_control_fanout_targets AS targets
  ON targets.tenant_id = versions.tenant_id
 AND targets.fanout_id = versions.fanout_id
 AND targets.agent_run_id = versions.agent_run_id
 AND targets.runtime_run_id = versions.runtime_run_id
 AND targets.target_fencing_token = versions.target_fencing_token
WHERE versions.tenant_id = sqlc.arg(tenant_id)
  AND versions.fanout_id = sqlc.arg(fanout_id)
  AND versions.fanout_version = sqlc.arg(fanout_version)
ORDER BY versions.agent_run_id, versions.runtime_run_id;

-- name: LockAgentRunControlFanout :one
SELECT * FROM agent.agent_run_control_fanouts
WHERE tenant_id = sqlc.arg(tenant_id)
  AND fanout_id = sqlc.arg(fanout_id)
FOR UPDATE;

-- name: InsertAgentRunControlFanoutTarget :one
INSERT INTO agent.agent_run_control_fanout_targets (
    tenant_id, work_order_id, fanout_id, authority_kind,
    agent_run_id, runtime_run_id,
    target_fencing_token, system_safety_control_id,
    system_safety_control_digest, command_id, control_state, updated_at
) VALUES (
    sqlc.arg(tenant_id), sqlc.arg(work_order_id), sqlc.arg(fanout_id),
    sqlc.arg(authority_kind),
    sqlc.arg(agent_run_id), sqlc.arg(runtime_run_id),
    sqlc.arg(target_fencing_token), sqlc.narg(system_safety_control_id),
    sqlc.narg(system_safety_control_digest), sqlc.arg(command_id),
    sqlc.arg(control_state), sqlc.arg(updated_at)
)
RETURNING *;

-- name: InsertAgentRunControlFanoutVersion :one
INSERT INTO agent.agent_run_control_fanout_versions (
    tenant_id, work_order_id, fanout_id, fanout_version,
    previous_fanout_version, previous_fanout_digest,
    fanout_digest, action, authority_kind,
    authority_id, authority_digest, created_at, updated_at
) VALUES (
    sqlc.arg(tenant_id), sqlc.arg(work_order_id), sqlc.arg(fanout_id),
    sqlc.arg(fanout_version), sqlc.narg(previous_fanout_version),
    sqlc.narg(previous_fanout_digest),
    sqlc.arg(fanout_digest), sqlc.arg(action), sqlc.arg(authority_kind),
    sqlc.arg(authority_id), sqlc.arg(authority_digest),
    sqlc.arg(created_at), sqlc.arg(updated_at)
)
RETURNING *;

-- name: InsertAgentRunControlFanoutTargetVersion :one
INSERT INTO agent.agent_run_control_fanout_target_versions (
    tenant_id, fanout_id, fanout_version, authority_kind,
    agent_run_id, runtime_run_id,
    target_fencing_token, system_safety_control_id,
    system_safety_control_digest, control_state
) VALUES (
    sqlc.arg(tenant_id), sqlc.arg(fanout_id), sqlc.arg(fanout_version),
    sqlc.arg(authority_kind),
    sqlc.arg(agent_run_id), sqlc.arg(runtime_run_id),
    sqlc.arg(target_fencing_token), sqlc.narg(system_safety_control_id),
    sqlc.narg(system_safety_control_digest), sqlc.arg(control_state)
)
RETURNING *;

-- name: ListAgentRunControlFanoutTargets :many
SELECT * FROM agent.agent_run_control_fanout_targets
WHERE tenant_id = sqlc.arg(tenant_id)
  AND fanout_id = sqlc.arg(fanout_id)
ORDER BY agent_run_id, runtime_run_id
FOR UPDATE;

-- name: ClaimAgentRunControlFanoutTargets :many
WITH eligibility_time AS MATERIALIZED (
    SELECT clock_timestamp() AS occurred_at
),
candidates AS MATERIALIZED (
    SELECT targets.tenant_id, targets.fanout_id, targets.agent_run_id
    FROM agent.agent_run_control_fanout_targets AS targets
    CROSS JOIN eligibility_time
    WHERE targets.tenant_id = sqlc.arg(tenant_id)
      AND targets.control_state IN ('pending', 'dispatched', 'outcome_unknown')
      AND (targets.claim_worker_id IS NULL OR targets.claim_expires_at <= eligibility_time.occurred_at)
    ORDER BY targets.updated_at, targets.fanout_id, targets.agent_run_id
    FOR UPDATE OF targets SKIP LOCKED
    LIMIT sqlc.arg(batch_size)
),
claim_time AS MATERIALIZED (
    SELECT clock_timestamp() AS occurred_at
    FROM (SELECT count(*) FROM candidates) AS locked_candidates
)
UPDATE agent.agent_run_control_fanout_targets AS targets
SET claim_worker_id = sqlc.arg(worker_id),
    claim_fencing_token = targets.claim_fencing_token + 1,
    claim_expires_at = claim_time.occurred_at + sqlc.arg(lease_duration)::interval,
    updated_at = claim_time.occurred_at
FROM candidates
CROSS JOIN claim_time
WHERE targets.tenant_id = candidates.tenant_id
  AND targets.fanout_id = candidates.fanout_id
  AND targets.agent_run_id = candidates.agent_run_id
RETURNING targets.*;

-- name: RenewAgentRunControlFanoutTargetLease :one
WITH locked_target AS MATERIALIZED (
    SELECT targets.tenant_id, targets.fanout_id, targets.agent_run_id,
           targets.claim_expires_at, targets.updated_at
    FROM agent.agent_run_control_fanout_targets AS targets
    WHERE targets.tenant_id = sqlc.arg(tenant_id)
      AND targets.fanout_id = sqlc.arg(fanout_id)
      AND targets.agent_run_id = sqlc.arg(agent_run_id)
      AND targets.claim_worker_id = sqlc.arg(worker_id)
      AND targets.claim_fencing_token = sqlc.arg(claim_fencing_token)
    FOR UPDATE OF targets
),
operation_time AS MATERIALIZED (
    SELECT clock_timestamp() AS occurred_at FROM locked_target
),
renewal_time AS MATERIALIZED (
    SELECT GREATEST(
        operation_time.occurred_at,
        locked_target.updated_at + interval '1 microsecond'
    ) AS occurred_at
    FROM locked_target
    CROSS JOIN operation_time
)
UPDATE agent.agent_run_control_fanout_targets AS targets
SET claim_expires_at = GREATEST(
        locked_target.claim_expires_at,
        renewal_time.occurred_at + sqlc.arg(lease_duration)::interval
    ),
    updated_at = renewal_time.occurred_at
FROM locked_target
CROSS JOIN operation_time
CROSS JOIN renewal_time
WHERE targets.tenant_id = locked_target.tenant_id
  AND targets.fanout_id = locked_target.fanout_id
  AND targets.agent_run_id = locked_target.agent_run_id
  AND locked_target.claim_expires_at > operation_time.occurred_at
RETURNING targets.*;

-- name: ProgressAgentRunControlFanoutTarget :one
WITH operation_time AS MATERIALIZED (
    SELECT GREATEST(
        clock_timestamp(),
        sqlc.arg(previous_updated_at)::timestamptz + interval '1 microsecond'
    ) AS occurred_at
)
UPDATE agent.agent_run_control_fanout_targets AS targets
SET control_state = sqlc.arg(control_state),
    claim_worker_id = NULL,
    claim_expires_at = NULL,
    updated_at = operation_time.occurred_at
FROM operation_time
WHERE targets.tenant_id = sqlc.arg(tenant_id)
  AND targets.fanout_id = sqlc.arg(fanout_id)
  AND targets.agent_run_id = sqlc.arg(agent_run_id)
  AND targets.control_state = sqlc.arg(expected_control_state)
  AND targets.claim_worker_id = sqlc.arg(worker_id)
  AND targets.claim_fencing_token = sqlc.arg(claim_fencing_token)
  AND targets.claim_expires_at > operation_time.occurred_at
RETURNING targets.*;

-- name: AdvanceAgentRunControlFanoutVersion :one
UPDATE agent.agent_run_control_fanouts
SET latest_version = sqlc.arg(next_version),
    latest_digest = sqlc.arg(next_digest),
    updated_at = sqlc.arg(updated_at)
WHERE tenant_id = sqlc.arg(tenant_id)
  AND fanout_id = sqlc.arg(fanout_id)
  AND latest_version = sqlc.arg(next_version) - 1
  AND latest_digest = sqlc.arg(previous_digest)
  AND updated_at < sqlc.arg(updated_at)
RETURNING *;
