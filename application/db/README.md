# PostgreSQL Sources

This directory owns hand-reviewed database source inputs. PostgreSQL is the
authority for current platform state, ledgers, Outbox, Inbox, idempotency,
fencing, and query metadata.

- `migration/` contains ordered SQL-first goose migrations.
- `query/` contains sqlc input queries.

Generated Go code belongs under `internal/generated/`; database dumps, build
artifacts, and runtime evidence do not belong here.
