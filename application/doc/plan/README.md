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
  the a1.1.1 mTLS Process Foundation candidate, and the independently validated
  a1.1.2 Start, a1.1.3 Command/recovery and a1.1.4 legal read/evidence-closure
  candidates; covers Strict
  I-JSON, Schema/semantic admission, JWS binding, migrations, process tests,
  evidence, rollback, and explicit authority boundaries. Malformed Status/Event
  HTTP 400 and all aggregate/production claims remain outside the closure.
- `B03.2a1.1.2-start-http-boundary.md`: approved execution plan and mandatory
  per-stage ledger for the Start-only HTTP boundary, including strict HTTP/1.1
  framing, pre-parse body limits, mTLS/JWS binding, closed Contract response
  mapping, installed-wheel controlled-fault evidence, rollback, stop conditions,
  and the completed full-Gate ledger.
- `B03.2a1.1.3-command-recovery-boundary.md`: implemented and independently
  validated execution plan and mandatory per-stage ledger for the Command-only
  HTTP boundary, transaction SIGKILL/SQLite reopen, installed test-worker lease
  recovery, and same-revision checkpoint crash consistency, with explicit
  production-worker, platform-authority, Status/Event, rollback, evidence, and
  maturity boundaries.
- `B03.2a1.1.4-read-boundary-evidence-closure.md`: implemented and independently
  validated execution plan and mandatory per-stage ledger for legal
  Status/Event HTTP reads, OpenAPI default descriptor normalization, cursor
  resume/expiry and final a1.1 Provider-local component evidence closure. The
  missing Status/Event HTTP 400 authority remains machine-readable blocked; Go
  adapter, platform authority, CanonicalEvent, production composition and
  aggregate conformance are excluded.
- `B03.2a2.0-framework-neutral-go-port-outcome-model.md`: implemented candidate
  and mandatory per-stage ledger for the first independently closable a2 slice:
  a framework-neutral Go Port, stable opaque values, closed read failure and
  mutation outcomes, and an explicit fresh-read/no-retry reconciliation
  requirement, with independent normal/Race evidence and complete checkpoint
  Gate. It excludes the strict HTTP adapter, installed cross-language process
  evidence, dynamic Suite closure, platform authority and production
  composition; those remain separately ordered a2.1-a2.3 or B03.2b/B03.2c work.
- `B03.2a2.1-strict-unwired-http-adapter.md`: implemented candidate and
  mandatory per-stage ledger for the next independently closable a2 slice: a
  harness-only five-operation HTTPS adapter with required locked Contract
  Schema/Runtime Event Registry validation, bounded exact response handling,
  capability immutability, one-dispatch Start/Command and typed known/unknown/
  not-dispatched outcomes. Independent normal/Race, real loopback mutual-TLS/
  HTTP evidence and the complete Application Gate pass; this completion status
  takes effect when the frozen plan state is included in a subsequent complete
  source-rebind Gate with exit 0. Status/Event 400, undeclared read 429,
  installed Native Runtime cross-language evidence, dynamic Suite closure,
  production authority and composition remain blocked or outside this slice.
