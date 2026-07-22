# Storage Ports

Phase: **0B starts with object references and non-authoritative wakeup/cache**.

Define ports and adapters for S3-compatible object storage plus Redis/Valkey
cache, presence, and wakeup here. PostgreSQL stores immutable object metadata,
digests, ownership, and lifecycle state; object storage holds Artifact and
Recording bytes.

Object keys are not authorization. Redis must never hold the only copy of a
ledger, authorization decision, terminal state, cursor, or durable command.
