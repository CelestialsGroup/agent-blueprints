# Persistence Adapters

Phase: **0B current priority**.

Implement pgx v5 transaction management, transaction-scoped PostgreSQL
TenantContext, sqlc-backed repositories, RLS verification hooks, CAS/fencing,
and mapping between database rows and domain values here.

Repositories must expose atomic use cases, not table-shaped CRUD. They may not
silently open nested transactions, omit tenant context, or leak pgx/sqlc types
into the domain layer.
