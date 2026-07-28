# Temporal Orchestration

Phase: **0B bounded B03.1 foundation implemented**.

Implement versioned Workflows, Activities, task-queue routing, Continue-as-New
policy, Worker Build ID compatibility, and Replay fixtures here. Workflow code
must be deterministic and interact with PostgreSQL or Providers only through
Activities.

Temporal owns durable orchestration history. PostgreSQL remains authoritative
for current state, ledgers, commands, fencing, and query projections.

The current adapter derives a stable `work-order/<work_order_id>` Workflow ID,
uses fail-on-conflict start policy, reconciles unknown Start outcomes through
Describe, and returns only a digest of the native execution reference. The
deterministic Workflow schedules one idempotent PostgreSQL confirmation
Activity, then accepts bounded test control for completion or Continue-as-New.
The Worker uses a fixed Deployment, immutable Build ID, and pinned Versioning
Behavior. Production WorkOrder Start remains deliberately unwired until its
authoritative persisted intent and admission transaction exist.
