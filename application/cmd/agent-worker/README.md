# Agent Worker

Phase: **0B**.

This process hosts the versioned Temporal Workflow and PostgreSQL confirmation
Activity admitted by B03.1. It does not expose or dispatch a production
WorkOrder start path, perform Root Admission, or run the Platform Safety
Controller. Those responsibilities remain blocked on their authoritative
persistence and Contract inputs.

Temporal History is orchestration truth, not the query model or ledger. Durable
current state, commands, fencing, and outbox records remain in PostgreSQL.

Startup requires `AGENT_DATABASE_DSN`, `AGENT_TEMPORAL_ADDRESS`,
`AGENT_TEMPORAL_NAMESPACE`, `AGENT_TEMPORAL_TASK_QUEUE`,
`AGENT_TEMPORAL_ENGINE_VERSION`, `AGENT_WORKER_DEPLOYMENT`, and
`AGENT_WORKER_BUILD_ID`. The process never promotes a Worker Deployment version;
deployment routing remains an explicit operational action after Replay and
compatibility evidence.
