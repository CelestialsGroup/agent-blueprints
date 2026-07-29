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
HTTP serving, Strict I-JSON, JWS/mTLS admission, the Go adapter, production
composition, Platform authority, and aggregate Conformance remain unimplemented.

The Native Runtime quality toolchain is exact: `ruff==0.16.0`,
`mypy==2.3.0` in strict mode, and standard-library `unittest` under the pinned
Python 3.14.6 toolchain. The Application Gate checks Ruff format and lint, mypy
over `src/` and `test/`, all 23 unit/component tests, the frozen uv lock, and a
reproducible wheel. Generated Contract transport modules remain under their
separate zero-diff regeneration and fixture-parity Gate.
