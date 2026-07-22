# Agent Access

Phase: **0B composition root; lifecycle skeleton exists**.

This process owns the public Agent Access HTTP boundary. It will validate
identity, tenant context, request contract/digest bindings, idempotency, body
limits, and authorization before invoking the modular Go kernel.

HTTP handlers must not contain transaction logic or treat middleware context as
authorization truth. OpenAPI remains in the external Contract checkout.
