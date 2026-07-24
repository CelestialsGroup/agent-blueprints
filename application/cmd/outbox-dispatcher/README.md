# Outbox Dispatcher

Phase: **0B**.

This process claims committed PostgreSQL outbox rows with bounded batches and
`FOR UPDATE SKIP LOCKED`, publishes them at least once, and records delivery
progress without hiding unknown outcomes.

Consumers still require Inbox deduplication. Redis may wake the dispatcher but
cannot replace the durable outbox or become delivery truth.

B02.2 implements the PostgreSQL store and transport-independent dispatcher
service under `internal/`; this directory does not yet contain a deployable
composition root, external transport adapter, polling loop, or Redis wakeup.
