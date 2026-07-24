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
commit/rollback. B02.2 extends the same pinned harness with repeated Race runs
for safe empty Down/re-Up and refused data-bearing Down, Outbox/domain atomicity,
concurrent claim ownership, renewal, lease-expiry recovery, stale fencing,
row-lock waits crossing lease expiry, retry/terminal state, Inbox
replay/conflict/rollback, global Transport Message ID collision, exact
column-level messaging ACLs, immutable Outbox replay metadata, cross-tenant
denial, Unicode identifier parity, refused Down RLS restoration, and pool reuse.
Lease tests force database state rather than injecting a Worker wall clock.

Canonical source Inbox evidence is intentionally absent because the locked
Contract identifier profile is not representable in PostgreSQL text.

Each successful run emits a generated B02.2 evidence manifest
that binds its log, source digests, tool/image pins, and dependency lock.
