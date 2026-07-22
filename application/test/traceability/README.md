# Phase 0 Implementation Traceability

`phase0-implementation-evidence.json` is the Application-owned claim map for
every Contract enforcement whose status is `phase0_implementation_required`.
It references implementation and test files; it does not copy Contract rules.

The B01 scaffold intentionally contains no implementation claims. The
traceability Gate therefore reports every required mapping as `unimplemented`
while still proving that none is missing from the report. This is expected and
must not be described as Phase 0B completion.

A future `implemented` claim must:

- name one Contract `check_id`;
- reference non-documentation files inside this Application checkout;
- include migration plus integration-test evidence for DDL responsibilities;
- include a Conformance test reference with the matching case ID for
  Conformance responsibilities.

Generated reports belong under `build/evidence/`; they bind the dependency
lock, Contract Manifest, semantic-constraint file, evidence map, and every
referenced evidence file by SHA-256.
