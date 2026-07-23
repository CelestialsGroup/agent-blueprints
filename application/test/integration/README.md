# Integration Tests

Use real pinned PostgreSQL, Temporal, Redis/Valkey, object storage, and process
boundaries where the behavior depends on them. Initial Phase 0B coverage must
include empty-database migration, RLS isolation, repository transactions,
Outbox/Inbox, CAS, fencing, and Redis-flush recovery.

Mocks are acceptable for unrelated boundaries but cannot prove database locks,
constraints, RLS, orchestration Replay, or provider retry behavior.

The current PostgreSQL suite is run by `script/test_postgres_integration.sh`.
It creates an isolated Docker network and a disposable digest-pinned PostgreSQL
container; it never uses a database installed on the development machine. The
suite covers the bootstrap lifecycle, database-bound cluster roles, the real
Migrator Login path, exact Application ACLs, missing and invalid TenantContext,
cross-tenant reads/writes, immutable Tenant metadata conflicts, DDL/RLS bypass
attempts, nested transactions, rollback, and single-connection pool reuse after
commit/rollback. Each successful run emits a generated B02.1 evidence manifest
that binds its log, source digests, tool/image pins, and dependency lock.
