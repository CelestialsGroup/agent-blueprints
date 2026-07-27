# 0003 PostgreSQL Runtime Control And Safety Ledgers

Date: 2026-07-27

Status: implemented candidate awaiting review. This decision applies only to
the bounded B02.3 PostgreSQL component. It does not claim complete parent
lifecycles, Canonical Platform Event atomicity, Phase 0B, reliability approval,
formal freeze, security approval, or production readiness.

## Context

The locked Blueprint requires PostgreSQL-authoritative runtime control and
safety facts with Tenant isolation, append-only ledgers, transactional Outbox,
idempotency, fencing, recoverable Fanout, and reconciliation. The locked
Contract owns the exact AgentRuntimeCommand, SystemSafetyControl, and
AgentRunControlFanout shapes, digests, state semantics, and authority rules.
B02.1 provides roles, RLS, TenantContext, transactions, and the real PostgreSQL
harness; B02.2 provides the durable Outbox.

The B02.3 leaves require authoritative WorkOrder, Run, Invocation/Attempt,
user-control, system-evidence/controller, and Child Admission facts. No prior
migration contained those parents, and nullable IDs or generic registries would
not close their reference or lock invariants. Canonical Platform Event admission
also remains absent, while the B02.2 Canonical source representation gap is
unchanged.

## Decision

Migration `00003` introduces narrow Tenant-qualified parent facts for only the
relationships and cursors consumed by this slice. They are authoritative rows,
foreign keys, state bounds, and admission use cases, but are not declarations of
complete WorkOrder, WorkflowRun, AgentRun, RuntimeRun, Invocation, or Child
Admission lifecycle implementation.

SystemSafetyControl is an Application-append-only ledger, but its write path is
disabled unless the composition root supplies an authenticated control-plane
authority verifier. Verification occurs before the database transaction; a
missing or rejecting verifier fails closed. The Application Role cannot insert
Platform Safety Controller or trigger-evidence parent rows. Validated writes
bind one active RuntimeRun, one persisted controller identity, and one immutable
same-WorkOrder evidence fact. Database allowlists and domain validation permit
only reduction actions; system resume, input, approval, checkpoint, or other
authority expansion has no accepted shape. B02.3 does not provide the
production verifier, authoritative parent admission, or a guessed
reason-to-evidence Contract map.

AgentRuntimeCommand binds exactly one permitted user, system, Child Admission,
or checkpoint authority shape. Tenant-qualified foreign keys bind the authority,
RuntimeRun, Invocation/Attempt, request digest, and target action. Allocation
locks the RuntimeRun cursor and requires the next sequence plus a strictly higher
fencing token. Command ID, digest, sequence, idempotency key, and target fencing
are unique at their governed scopes. A SystemSafetyControl can authorize only
one Runtime Command, preventing a new command identity from duplicating the
same reduction side effect.

Every accepted command and system safety control stores a unique Outbox Message
ID, payload digest, fixed `agent-runtime-control` destination, availability
time, and creation time. A Tenant-qualified foreign key references the matching
B02.2 Outbox tuple and is deferrable initially deferred.
The repository may therefore append the ledger before enqueueing in the same
transaction, but commit cannot retain either side alone. Replay requires the
same ledger digest and the same Outbox binding; a second Message ID fails closed.

AgentRunControlFanout closes later Child admission under the WorkOrder lock,
materializes every immutable active AgentRun with a matching locked RuntimeRun,
allocates target fencing, appends commands and any system controls with Outbox
facts, and stores version one atomically. Admission triggers take the same
WorkOrder lock and reject new Run or accepted Child Admission facts after the
snapshot closes, so membership cannot race the snapshot; rejected late-spawn
decisions remain appendable as denial receipts. Progress
claims use ordered `FOR UPDATE SKIP LOCKED`, PostgreSQL lease time, and a claim
fencing token. Each successful progress mutation appends a full snapshot with a
contiguous version and predecessor digest before advancing the root cursor.
Database triggers reject identity changes and state regression. Creation replay
reads version one plus immutable target, command/control, and Outbox bindings,
so later progress cannot invalidate a valid retry or hide an internal command-ID
conflict that is outside the public Fanout digest.

All new tables are owned by the NOLOGIN Migrator Role, enable and force RLS, and
give the non-owner Application Role table-level SELECT plus only reviewed insert
or mutable-state columns. Safety controller/evidence tables are read-only to the
Application Role. Repository APIs expose domain values, bound and stably order
authority batches before row locking, keep authority verification and network
I/O outside transactions, and do not retain process-global mutable authority.
Admission prelocks the complete deduplicated WorkOrder set in global ID order,
preventing both within-category and cross-category batch lock inversion.
Invocation and Attempt creation times are distinct immutable facts and are both
checked on replay.

The PostgreSQL schema remains named `agent`, while several table names also
begin with `agent_`. sqlc's default concatenation produced misleading
`AgentAgent...` Go types. `sqlc.yaml` now owns explicit deterministic renames;
generated files remain generated and the database vocabulary is unchanged.

## Alternatives Rejected

- Unchecked strings, polymorphic nullable references, generic ID registries, or
  test-only parents: none proves same-Tenant authority or lock ownership.
- Expanding into complete WorkOrder, Workflow, Run, Child Admission, or Event
  models: exceeds this independent slice and would create unreviewed semantics.
- An internal event named Platform Event: it would replace rather than implement
  the locked Contract fact.
- Process-memory sequence, Fanout targets, claims, or replay identity: none is
  recoverable or authoritative after a crash.
- Worker wall-clock lease timestamps or network I/O under row locks: both weaken
  fencing and transaction bounds.
- Redis, Temporal, or Broker state to close database invariants: unnecessary and
  outside the accepted dependency boundary.
- Treating a successful generic Contract-ID regex or an Application-supplied
  issuer string as safety authority: neither proves evidence type or current
  authenticated WorkloadIdentity.

## Compatibility And Rollback

The migration is additive and changes no public endpoint. Empty B02.3 tables may
be removed and re-applied. Once any parent, command, control, Fanout, target, or
version row exists, Down refuses before destructive DDL; recovery requires a
reviewed forward migration. The Outbox binding unique constraint is removed only
after all referencing empty B02.3 tables are dropped. The additive immutable
Outbox `initial_available_at` column remains after an empty Down for current
binary/B02.2 read compatibility and is reused by a repeated Up.

No dependency or image is added. pgx, goose, sqlc, Go, and PostgreSQL remain at
the exact B02.1/B02.2 pins. Any later change to authority, digest, sequencing,
fencing, Fanout state, Outbox binding, or Canonical Event behavior requires an
explicit compatibility review against the locked Blueprint and Contract.

External WorkOrderControlRequest intake and ExecutionGrant consumption, Safety
Controller workload authentication/policy evaluation, and complete parent state
transitions remain outside this decision. Their absence limits the maturity
claim. The locked AgentRuntimeCommand Contract leaves several indexed IDs
unbounded, SystemSafetyControl does not bound `evidence_contract_id`, and some
identifier strings permit U+0000. PostgreSQL indexed text in this slice is
bounded to 200 runes and cannot store U+0000. Application rejection is an
explicit fail-closed subset, not a complete wire-conformance claim.
