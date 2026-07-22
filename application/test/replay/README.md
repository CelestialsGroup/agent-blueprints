# Replay Tests

Store sanitized, versioned Temporal histories and event/cursor replay scenarios
needed to detect incompatible Workflow or projection changes. Replay tests must
run before Worker Build ID promotion.

Fixtures contain no secrets, prompts, user content, Provider endpoints, or
mutable production identifiers. A successful Replay is compatibility evidence,
not end-to-end or production-recovery proof.
