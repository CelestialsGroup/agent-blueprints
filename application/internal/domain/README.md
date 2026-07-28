# Domain Kernel

Phase: **0B starts with the persistence spine aggregates**.

Organize pure Go packages here by ownership: Access, Conversation, WorkOrder and
execution identity, Provider resolution, command/safety control, and Canonical
Event first; Invocation, Sandbox, Artifact, Recording, and Usage follow their
Phase 0 milestones.

Domain code owns invariants, commands, decisions, and error taxonomy. It does
not own wire DTOs, SQL rows, Temporal history types, Provider-private objects,
or framework checkpoints. Add a child package only when its first behavior is
implemented; do not create empty layer trees.

The current `orchestration` package owns the framework-neutral WorkflowRun,
WorkflowDefinition, OrchestrationBinding, start request/receipt, digest,
idempotency, and conflict values consumed by B03.1. It intentionally contains
no Temporal or persistence SDK types.
