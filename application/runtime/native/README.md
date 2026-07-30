# Native Runtime

Phase: **0B Core Profile; 0D General/Governed expansion**.

This Python package is the primary self-developed Agent Runtime. The 0B slice
implements Start, Status, Cursor Event, user Cancel, fenced safety Cancel,
minimal Checkpoint/Restart, and `sandboxes=[]` execution under `runtime-core-v1`.

The internal Agent Loop, context, and skill design is private and replaceable.
It must use platform Gateways for governed effects, persist no platform truth,
and expose no third-party Thread or Checkpoint model through public contracts.

B03.2-P0 admits generated transport projections and independently tested Draft
2020-12, JOSE, and JCS dependencies. B03.2a0 adds the Provider-local durable
kernel: immutable configuration, explicit SQLite migration, transactional
Start/Status/Command/Event behavior, cancellation proof, same-revision
Checkpoint/Restart, recoverable execution work, and `sandboxes=[]`.

B03.2a0 accepts values already admitted by a future secure transport boundary.
B03.2a1.0 adds an HTTP-independent secure admission core: bounded Strict I-JSON,
locked Draft 2020-12 validation, nested digest and root semantic checks,
EdDSA/ES256 compact JWS verification, immutable public-key configuration,
Provider-local security bindings, and authorized Status/Event reads.
B03.2a1.1.1 adds separate installed-wheel migration and serve entry points, an
immutable file/environment configuration snapshot, a loopback-only bounded
standard-library HTTP/1.1 + TLS process, test-PKI mTLS caller extraction,
Capabilities, health/readiness, and bounded SIGTERM drain. The B03.2a1.1.2
candidate adds only `POST /v1/runs`: strict HTTP/1.1 framing, the Contract
8 MiB pre-parse body limit, bounded Bearer extraction, exact mTLS subject/JWS
binding, reuse of `SecureAdmissionCore.start`, and locked RunStatus/
StandardError response validation. B03.2a1.1.3 adds exact Command HTTP,
transaction/response-loss recovery, real expired work-lease reclaim and
same-revision checkpoint crash consistency through installed test processes.
B03.2a1.1.4 adds only legal Status/Event GET targets, OpenAPI default
normalization, repeated read tokens without mutation-JTI persistence, ordered
EventPage responses, cursor resume/empty-page behavior, and explicit bounded
410 recovery after real Provider-local retention. The locked OpenAPI has no
authoritative Status/Event 400 response, so malformed-read transport verdicts
remain machine-readable blocked rather than being inferred from implementation.
The Go adapter, production composition, Platform authority, CanonicalEvent,
production Safety Controller, and aggregate Conformance remain unimplemented
or unclaimed.

The Native Runtime quality toolchain is exact: `ruff==0.16.0`,
`mypy==2.3.0` in strict mode, and standard-library `unittest` under the pinned
Python 3.14.6 toolchain. The Application Gate checks Ruff format and lint, mypy
over `src/` and `test/`, all 69 source unit/component tests, installed-wheel
foundation 5/5, Start 26/26, Command 7/7, read file 7/7, transaction 3/3,
lease 2/2 and checkpoint 2/2 tests, the frozen uv lock, and byte-identical
reproducible wheels. The read file contains four source-boundary and three real
TLS/HTTP/SQLite process tests. Recovery evidence uses real parent-driven
SIGKILL windows and remains limited to the installed test executor, local
SQLite/filesystem, and same revision. Generated Contract transport modules
remain under their separate zero-diff regeneration and fixture-parity Gate.
