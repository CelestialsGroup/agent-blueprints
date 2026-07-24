# sqlc Queries

Phase: **0B current priority**.

Write explicit SQL used by transactional repositories here. Queries must make
CAS predicates, fencing checks, row locks, tenant scope, ordering, and affected
row expectations visible to review.

Do not encode domain state transitions only in generated code. Repository APIs
must hide pgx/sqlc types from the domain layer and execute under an explicit
transaction-scoped TenantContext.

The B02.1 queries always carry `tenant_id` even though RLS is also enabled.
Tenant creation uses `INSERT ... ON CONFLICT DO NOTHING RETURNING`; a conflict
is followed by a fresh scoped read so the Repository can enforce immutable
Tenant metadata before attempting the ClientApplication insert.
Regenerate with the pinned sqlc image through `make validate-implementation`;
the Gate compares a clean regeneration with `internal/generated/agentdb`.

`durable_messaging.sql` keeps global Transport enqueue identity checks, bounded ordered
`FOR UPDATE SKIP LOCKED` claims, live-lease fencing predicates, retry scheduling,
and Transport Inbox identity lookup visible. Lease mutations lock the exact
Worker/token row before materializing one PostgreSQL `clock_timestamp()`, so lock
wait cannot preserve an already-expired owner. They accept bounded
whole-microsecond duration inputs. A claim transaction never contains transport
I/O; fenced result writes are separate transactions.
