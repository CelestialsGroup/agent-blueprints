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
- `B02.3-postgresql-runtime-control-safety-ledgers.md`: bounded PostgreSQL
  Runtime Command, System Safety Control, and AgentRun Control Fanout ledgers,
  their narrow authority parents, recovery evidence, and unproved boundaries.
- `B03.1-temporal-orchestration-replay-foundation.md`: bounded Temporal
  dependency admission, adapter, WorkflowRun start-confirmation, worker
  versioning, real-Temporal recovery, and deterministic Replay foundation.
- `B03.2-native-runtime-core-conformance-safety-integration.md`: staged Runtime
  Contract projection and dependency admission, Native Runtime Core component,
  Go Provider adapter, platform authority prerequisites, and fenced System
  Cancel integration plan with explicit Conformance evidence boundaries.
- `B03.2a1-secure-provider-process.md`: approved split plan, validated a1.0/a1.1.0,
  and the a1.1.1 mTLS Process Foundation candidate; covers Strict
  I-JSON, Schema/semantic admission, JWS binding, migrations, process tests,
  evidence, rollback, and explicit authority boundaries.
