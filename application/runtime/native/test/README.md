# Native Runtime Tests

Keep Python unit and component tests for the Native Runtime package here. Cover
deterministic command handling, cursor ordering, cancellation, checkpoint
compatibility, restart behavior, bounded inputs, and no-Sandbox execution.

The B03.2a0 tests use a bounded private executor and a real SQLite file. The
B03.2a1.0 tests add locked Strict I-JSON vectors, Schema and semantic admission,
EdDSA/ES256 JWS verification, negative token matrices, and authorized read
transactions. They do not substitute for the a1.1 real HTTP/mTLS process
boundary or the a2 Go adapter and Suite harness.

The locked Gate runs Ruff format/lint, mypy strict checking, and these tests in
one uv-frozen Python 3.14.6 environment. Durable tests also corrupt persisted
event documents deliberately to prove the SQLite mapper fails closed.

Cross-provider Contract Suite execution and platform integration scenarios
belong under the repository-level `test/` directories.
