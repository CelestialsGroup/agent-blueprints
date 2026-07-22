# Integration Tests

Use real pinned PostgreSQL, Temporal, Redis/Valkey, object storage, and process
boundaries where the behavior depends on them. Initial Phase 0B coverage must
include empty-database migration, RLS isolation, repository transactions,
Outbox/Inbox, CAS, fencing, and Redis-flush recovery.

Mocks are acceptable for unrelated boundaries but cannot prove database locks,
constraints, RLS, orchestration Replay, or provider retry behavior.
