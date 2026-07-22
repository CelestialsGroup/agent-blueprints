# Runtime Gateway

Phase: **0E, not implemented**.

This process will mediate short-lived RuntimeSession connections, opaque route
references, channel generations, cursor sequences, ACK windows, control
digests, and recording gates.

It must never expose raw Sandbox endpoints or treat an in-memory connection as
session truth. Browser/Desktop recording stays disabled until its privacy and
capacity gates are satisfied.
