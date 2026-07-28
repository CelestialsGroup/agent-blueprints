# Phase 0 Implementation Traceability

`phase0-implementation-evidence.json` is the Application-owned claim map for
every Contract enforcement whose status is `phase0_implementation_required`.
It references implementation and test files; it does not copy Contract rules.

B01 intentionally contained no implementation claims. B02.2 also makes no
Phase 0 implementation claim: its only candidate, Canonical source Inbox
uniqueness, is blocked because the locked Contract accepts escaped NUL in source
identifiers while PostgreSQL text cannot represent it. B03.1 claims only
`workflow_run_optional_unique_binding`, whose complete DDL responsibility is
covered by the immutable unique WorkOrder binding and real PostgreSQL negative,
concurrency, and rollback tests. Broader WorkflowRun, RootBinding, orchestration,
stable semantic, and lifecycle Check IDs remain explicitly unimplemented.

A future `implemented` claim must:

- name one Contract `check_id`;
- reference non-documentation files inside this Application checkout;
- include migration plus integration-test evidence for DDL responsibilities;
- include a Conformance test reference with the matching case ID for
  Conformance responsibilities.

Generated reports belong under `build/evidence/`; they bind the dependency
lock, Contract Manifest, semantic-constraint file, evidence map, and every
referenced evidence file by SHA-256.
