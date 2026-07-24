# Implementation Plans

Plans in this directory translate accepted Blueprint and Contract
responsibilities into an ordered Application delivery slice. They do not copy
architecture, schemas, semantic constraints, or Conformance Suites into a
second authority.

Each plan records scope and exclusions, exact governed inputs, implementation
steps, validation evidence, rollback classification, review decisions, and
properties that remain unproven. Status reflects only the named slice and must
not be promoted to a wider phase or production-readiness claim.

Current plans:

- `B02.1-postgresql-bootstrap.md`: PostgreSQL roles, TenantContext, RLS, and the
  initial Tenant/ClientApplication repository slice.
- `B02.2-postgresql-durable-messaging.md`: transactional Outbox/Inbox, leased
  dispatch, Transport dedupe, Contract-gap boundary, and real-PostgreSQL recovery
  evidence.
