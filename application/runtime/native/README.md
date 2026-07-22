# Native Runtime

Phase: **0B Core Profile; 0D General/Governed expansion**.

This Python package is the primary self-developed Agent Runtime. The 0B slice
implements Start, Status, Cursor Event, user Cancel, fenced safety Cancel,
minimal Checkpoint/Restart, and `sandboxes=[]` execution under `runtime-core-v1`.

The internal Agent Loop, context, and skill design is private and replaceable.
It must use platform Gateways for governed effects, persist no platform truth,
and expose no third-party Thread or Checkpoint model through public contracts.
