# PostgreSQL Sources

This directory owns hand-reviewed database source inputs. PostgreSQL is the
authority for current platform state, ledgers, Outbox, Inbox, idempotency,
fencing, and query metadata.

- `migration/` contains ordered SQL-first goose migrations.
- `query/` contains sqlc input queries.

Generated Go code belongs under `internal/generated/`; database dumps, build
artifacts, and runtime evidence do not belong here.

The current sequence implements B02.1 bootstrap, B02.2 durable Transport
messaging, and the bounded B02.3 runtime-control/safety ledgers. The B02.3
parent tables are authoritative only for the referenced control transaction
invariants; their presence does not claim complete WorkOrder or Run lifecycles.
Safety Controller and trigger-evidence rows are read-only to `agent_app` until
their authoritative parent slices exist. Command/control Outbox foreign keys
bind message identity, payload digest, destination, and issuance timestamps.
