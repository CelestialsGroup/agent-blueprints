# Phase 0 Implementation Traceability

`phase0-implementation-evidence.json` is the Application-owned claim map for
every Contract enforcement whose status is `phase0_implementation_required`.
It references implementation and test files; it does not copy Contract rules.

B01 intentionally contained no implementation claims. B02.2 also makes no
Phase 0 implementation claim: its only candidate, Canonical source Inbox
uniqueness, is blocked because the locked Contract accepts escaped NUL in source
identifiers while PostgreSQL text cannot represent it. Transport Outbox/Inbox
component evidence remains valid, but all mapped Phase 0 responsibilities stay
explicitly unimplemented.

A future `implemented` claim must:

- name one Contract `check_id`;
- reference non-documentation files inside this Application checkout;
- include migration plus integration-test evidence for DDL responsibilities;
- include a Conformance test reference with the matching case ID for
  Conformance responsibilities.

Generated reports belong under `build/evidence/`; they bind the dependency
lock, Contract Manifest, semantic-constraint file, evidence map, and every
referenced evidence file by SHA-256.
