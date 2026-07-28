-- name: InsertWorkflowRun :one
INSERT INTO agent.workflow_runs (
    tenant_id, workflow_run_id, work_order_id,
    workflow_id, workflow_version, workflow_definition_build_id,
    workflow_definition_digest, orchestration_engine_id,
    orchestration_engine_version, workflow_execution_id,
    native_execution_reference_digest, worker_deployment, worker_build_id,
    versioning_behavior, orchestration_binding_digest, created_at
) VALUES (
    sqlc.arg(tenant_id), sqlc.arg(workflow_run_id), sqlc.arg(work_order_id),
    sqlc.arg(workflow_id), sqlc.arg(workflow_version),
    sqlc.arg(workflow_definition_build_id), sqlc.arg(workflow_definition_digest),
    sqlc.arg(orchestration_engine_id), sqlc.arg(orchestration_engine_version),
    sqlc.arg(workflow_execution_id), sqlc.arg(native_execution_reference_digest),
    sqlc.arg(worker_deployment), sqlc.arg(worker_build_id),
    sqlc.arg(versioning_behavior), sqlc.arg(orchestration_binding_digest),
    sqlc.arg(created_at)
)
ON CONFLICT DO NOTHING
RETURNING *;

-- name: GetWorkflowRunByID :one
SELECT *
FROM agent.workflow_runs
WHERE tenant_id = sqlc.arg(tenant_id)
  AND workflow_run_id = sqlc.arg(workflow_run_id);

-- name: GetWorkflowRunByWorkOrderID :one
SELECT *
FROM agent.workflow_runs
WHERE tenant_id = sqlc.arg(tenant_id)
  AND work_order_id = sqlc.arg(work_order_id);
