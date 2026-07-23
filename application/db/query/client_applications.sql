-- name: EnsureTenant :one
INSERT INTO agent.tenants (
    tenant_id,
    display_name,
    created_at
) VALUES (
    $1,
    $2,
    $3
)
ON CONFLICT (tenant_id) DO NOTHING
RETURNING tenant_id, display_name, created_at;

-- name: GetTenant :one
SELECT tenant_id, display_name, created_at
FROM agent.tenants
WHERE tenant_id = $1;

-- name: CreateClientApplication :one
INSERT INTO agent.client_applications (
    tenant_id,
    client_app_id,
    display_name,
    created_at
) VALUES (
    $1,
    $2,
    $3,
    $4
)
RETURNING tenant_id, client_app_id, display_name, created_at;

-- name: GetClientApplication :one
SELECT tenant_id, client_app_id, display_name, created_at
FROM agent.client_applications
WHERE tenant_id = $1
  AND client_app_id = $2;
