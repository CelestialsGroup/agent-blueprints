# sqlc Queries

Phase: **0B current priority**.

Write explicit SQL used by transactional repositories here. Queries must make
CAS predicates, fencing checks, row locks, tenant scope, ordering, and affected
row expectations visible to review.

Do not encode domain state transitions only in generated code. Repository APIs
must hide pgx/sqlc types from the domain layer and execute under an explicit
transaction-scoped TenantContext.
