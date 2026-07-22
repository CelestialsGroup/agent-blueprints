# Agent Worker

Phase: **0B**.

This process hosts versioned Temporal Workflows and Activities for WorkOrder
orchestration, admission, reconciliation, and the Platform Safety Controller.
It must support deterministic Replay and Worker Build ID versioning.

Temporal History is orchestration truth, not the query model or ledger. Durable
current state, commands, fencing, and outbox records remain in PostgreSQL.
