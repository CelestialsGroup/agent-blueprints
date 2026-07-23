# Persistence Adapters

Phase: **0B current priority**.

Implement pgx v5 transaction management, transaction-scoped PostgreSQL
TenantContext, sqlc-backed repositories, RLS verification hooks, CAS/fencing,
and mapping between database rows and domain values here.

Repositories must expose atomic use cases, not table-shaped CRUD. They may not
silently open nested transactions, omit tenant context, or leak pgx/sqlc types
into the domain layer.

`TransactionRunner.Run` begins a pgx transaction and executes parameterized
`set_config('agent.tenant_id', $1, true)` before constructing a tenant
repository. Empty/invalid Tenant IDs and nested runs fail before repository SQL.
The ClientApplication repository maps generated rows into domain values and
keeps explicit tenant predicates in every query. A transaction scope guard also
rejects retained Repository references after their callback has returned.
Repeated registration accepts an existing Tenant only when `display_name` and
`created_at` match; mismatched immutable metadata returns a typed conflict and
rolls back before any ClientApplication is inserted.
