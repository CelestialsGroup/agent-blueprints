# Replay Tests

Store sanitized, versioned Temporal histories and event/cursor replay scenarios
needed to detect incompatible Workflow or projection changes. Replay tests must
run before Worker Build ID promotion.

Fixtures contain no secrets, prompts, user content, Provider endpoints, or
mutable production identifiers. A successful Replay is compatibility evidence,
not end-to-end or production-recovery proof.

`work_order_replay_test.go` replays every versioned fixture through the pinned
Temporal SDK, decodes every History payload before scanning prohibited terms,
and verifies that the initial Workflow input binds the exact SHA-256 of the
current Workflow definition source. A definition change therefore requires an
explicitly reviewed compatible fixture update before Worker promotion.
