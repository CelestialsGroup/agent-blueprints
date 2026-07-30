# Native Runtime Tests

Keep Python unit and component tests for the Native Runtime package here. Cover
deterministic command handling, cursor ordering, cancellation, checkpoint
compatibility, restart behavior, bounded inputs, and no-Sandbox execution.

The B03.2a0 tests use a bounded private executor and a real SQLite file. The
B03.2a1.0 tests add locked Strict I-JSON vectors, Schema and semantic admission,
EdDSA/ES256 JWS verification, negative token matrices, and authorized read
transactions. They do not substitute for the a1.1 real HTTP/mTLS process
boundary or the a2 Go adapter and Suite harness. B03.2a1.1.1 adds a separate
post-build matrix that installs the reproducible wheel, generates ephemeral test
PKI, exercises the real migrate/serve subprocesses and bounded TLS/HTTP
lifecycle, then discards every private test key. It does not enable or claim
Start, Command, Status, or Event transport by itself. B03.2a1.1.2 adds the
installed Start boundary; B03.2a1.1.3 adds installed Command plus real
transaction, lease and checkpoint crash recovery. B03.2a1.1.4 adds three real
installed Status/Event scenarios for immutable Status/default reads, strict
cursor resume/empty/410 expiry, invalid-signature oracle resistance, path
binding and admitted 404. The same read token is deliberately reused to prove
that reads do not persist mutation-JTI facts. Malformed Status/Event transport
cases are parser boundaries only and are not counted as HTTP conformance while
the locked OpenAPI omits authoritative 400 responses.

The locked Gate runs Ruff format/lint, mypy strict checking, and these tests in
one uv-frozen Python 3.14.6 environment. Durable tests also corrupt persisted
event documents deliberately to prove the SQLite mapper fails closed.
Installed tests exercise the built wheel from its installation directory;
source-tree imports cannot substitute for the tested process artifact.

Cross-provider Contract Suite execution and platform integration scenarios
belong under the repository-level `test/` directories.
