# Platform Safety Controller

Phase: **0B**.

Implement authorization-expiry, Business revocation, deadline, budget, and
emergency reduction decisions here. A decision atomically appends fenced
`SystemSafetyControl`, Platform Event, and command/control Outbox intent.

This controller is Platform-owned and reduction-only: it may pause or cancel,
but cannot resume, append input, approve, checkpoint, widen authorization, or
create new execution side effects.

B02.3 provides domain values and PostgreSQL persistence for the reduction-only
control fact, Runtime Command, and versioned AgentRun Control Fanout. It verifies
Contract digest vectors without copying schemas or semantic constraints into a
second authority. Persisted Safety Controller and trigger-evidence rows are
read-only FK targets for this slice; their authoritative admission and the
production authenticated authority verifier are absent, so unverified system
writes fail closed. Contract-valid Canonical Platform Event admission is also
absent, so the control/Event atomicity boundary remains explicitly unimplemented.
