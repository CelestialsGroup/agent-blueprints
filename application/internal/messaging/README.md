# Durable Messaging

Phase: **0B current priority**.

Implement Outbox claiming, dispatch state, Inbox source-identity deduplication,
retry classification, wakeup hints, and reconciliation scheduling here. The
database commit is authoritative; publication and consumption are at least
once.

Redis is permitted only as a wakeup optimization. A Redis flush or lost wakeup
must not lose committed work, authorization, event cursors, or ledger facts.
