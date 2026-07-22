# Reference Runtime Probe

Phase: **0G, not implemented**.

This independent Go provider will implement only `runtime-core-v1` to prove that
AgentRuntimeProvider is replaceable. It must not import Native Runtime private
packages, checkpoint formats, event models, or state stores.

The probe is conformance evidence, not a product Runtime and not an adapter for
any third-party Agent framework.
