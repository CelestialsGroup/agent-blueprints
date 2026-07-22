# Temporal Orchestration

Phase: **0B after the persistence transaction boundaries exist**.

Implement versioned Workflows, Activities, task-queue routing, Continue-as-New
policy, Worker Build ID compatibility, and Replay fixtures here. Workflow code
must be deterministic and interact with PostgreSQL or Providers only through
Activities.

Temporal owns durable orchestration history. PostgreSQL remains authoritative
for current state, ledgers, commands, fencing, and query projections.
