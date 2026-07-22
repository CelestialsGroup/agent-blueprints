# Outbox Dispatcher

Phase: **0B**.

This process claims committed PostgreSQL outbox rows with bounded batches and
`FOR UPDATE SKIP LOCKED`, publishes them at least once, and records delivery
progress without hiding unknown outcomes.

Consumers still require Inbox deduplication. Redis may wake the dispatcher but
cannot replace the durable outbox or become delivery truth.
