# v0.8.2 to v0.8.3

- Supply-chain hygiene checks governed Git-tracked files, so generated virtual-environment bytecode cannot fail the official command order; tracked bytecode and `.DS_Store` are rejected.
- WorkOrder and Invocation gained governed JSON state machines; Schema/state-machine equality, reachability, and terminal closure are executable semantic checks.
- Sandbox cancellation separates intent, evidence, confirmation, and terminal commit; uncertain effects remain reconcilable and abandon requires explicit risk acceptance.
- RunManifest admission consumes authoritative Scenario/Registry context and verifies exact capability coverage, Revision/Decision self-digests, latest certification, ProviderInstance bindings, and immutable snapshots.
- Compatibility detects the reported Schema/OpenAPI narrowing cases and uses protected CI variables with fail-closed baseline handling.
- Strict I-JSON rejects unsafe integral values regardless of integer, decimal, or exponent token spelling through 5 valid and 7 invalid shared vectors.
- Sandbox aggregate invariants require active Attempt identity, enforce attempt bounds semantically/database-side, and bind manual abandon to `risk_accepted=true`.
- Git-root Workflow activation is an explicit repository integration requirement; copying a nested workflow without committing it is not admission.

These changes preserve the Business/Platform and Provider/Adapter boundaries. They are contract/repository hardening, not production reliability proof.
