# Agent Runtime Port

Phase: **0B Core Profile**.

Implement the platform-side AgentRuntimeProvider client, operation digest and
token binding, Start/Status/Command/Cursor Event handling, retry classification,
and fenced attempt reconciliation here.

This package consumes generated Contract transport types but exposes stable
platform values to the kernel. Native Runtime internals, private checkpoint
formats, and provider runtime IDs must not leak through this boundary.
