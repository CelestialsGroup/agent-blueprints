# v0.8.3 to v0.8.4

- Uniform conformance-set admission makes every declared Provider kind executable through the same path.
- CapabilityDefinition digest, allowed Provider kind and conformance coverage are mandatory Run admission checks.
- InvocationRecord/state machine v2 adds Attempt binding, count bounds, reconciliation, manual decisions, cancellation evidence and risk-accepted abandon.
- Shared cancellation evidence forbids representing a completed external effect as cancelled.
- Strict I-JSON uses exact decimal-token integrality across languages and separates canonicalizer vectors from admission vectors.
- Compatibility covers additional Schema/OpenAPI narrowing classes and accepts only a fetched full commit SHA as baseline.
- Monorepo integration remains fail-closed until the Git-root Workflow and repository hygiene changes are actually committed.

The stable domain, persistence, Sandbox Slot and Adapter-private boundaries are unchanged.
