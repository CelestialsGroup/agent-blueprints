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

B02.3 extends that harness with empty/repeated Up and safe Down/Re-Up, refused
data-bearing Down, exact RLS/ACL/ownership checks, reduction-only safety actions,
three mutually exclusive command authority paths, digest and Outbox-binding
conflicts including destination/issuance time, contiguous sequence and fencing,
one command per SystemSafetyControl, concurrent sequence/digest conflicts,
WorkOrder-first parent admission and stable opposite-order Invocation
admission, atomic Outbox rollback, complete
Fanout target capture, missing-RuntimeRun and late accepted-admission rejection,
late rejected-decision persistence, concurrent claims and same-target progress,
lease expiry recovery, stale-token rejection, monotonic snapshots, replay after version progress,
post-commit snapshot reconciliation, cross-Tenant read/write/claim/progress denial,
and pool TenantContext cleanup.
It also proves that `agent_app` cannot admit Safety Controller/evidence rows and
that missing system-authority verification fails closed; administrator-seeded
test parents do not prove a production identity/evidence source.
The PostgreSQL catalog check also confirms that no internal Platform Event table
was invented. The suite runs three times under Go's race detector. It does not
substitute mocks for database locks, constraints, RLS, transactions, or recovery.

Canonical source Inbox evidence is intentionally absent because the locked
Contract identifier profile is not representable in PostgreSQL text. The
AgentRuntimeCommand Contract also leaves several indexed IDs unbounded; the
Application's 200-rune/U+0000 rejection is a tested implementation subset, not
full wire conformance.

Each successful run emits a generated B02.3 evidence manifest under
`build/evidence/b02.3` that binds its log, source digests, tool/image pins, and
dependency lock. It retains B02.1/B02.2 regression evidence but makes no
Canonical Platform Event, complete lifecycle, Phase 0B, reliability, freeze, or
production claim.
