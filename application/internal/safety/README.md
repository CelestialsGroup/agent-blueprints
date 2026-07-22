# Platform Safety Controller

Phase: **0B**.

Implement authorization-expiry, Business revocation, deadline, budget, and
emergency reduction decisions here. A decision atomically appends fenced
`SystemSafetyControl`, Platform Event, and command/control Outbox intent.

This controller is Platform-owned and reduction-only: it may pause or cancel,
but cannot resume, append input, approve, checkpoint, widen authorization, or
create new execution side effects.
