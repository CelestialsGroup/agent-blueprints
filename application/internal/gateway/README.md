# Governed Gateways

Phase: **0D-0E; only shared enforcement primitives may appear earlier**.

Platform-owned Capability/Model/Tool, Artifact, Egress, Credential, and Runtime
Gateway implementations belong behind this boundary. They enforce short-lived
operation tokens, request digests, policy, budget, permissions, fencing, and
audit before forwarding effects.

Connectors and SDKs are replaceable. They never become authorization, usage,
artifact, endpoint, or execution truth.
