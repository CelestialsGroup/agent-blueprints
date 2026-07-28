# Persistence Adapters

Phase: **0B current priority**.

Implement pgx v5 transaction management, transaction-scoped PostgreSQL
TenantContext, sqlc-backed repositories, RLS verification hooks, CAS/fencing,
and mapping between database rows and domain values here.

Repositories must expose atomic use cases, not table-shaped CRUD. They may not
silently open nested transactions, omit tenant context, or leak pgx/sqlc types
into the domain layer.

`TransactionRunner.Run` begins a pgx transaction and executes parameterized
`set_config('agent.tenant_id', $1, true)` before constructing a tenant
repository. Empty/invalid Tenant IDs and nested runs fail before repository SQL.
The ClientApplication repository maps generated rows into domain values and
keeps explicit tenant predicates in every query. A transaction scope guard also
rejects retained Repository references after their callback has returned.
Repeated registration accepts an existing Tenant only when `display_name` and
`created_at` match; mismatched immutable metadata returns a typed conflict and
rolls back before any ClientApplication is inserted.

The B02.2 adapter extends the same Tenant transaction with Outbox enqueue and
adds atomic Outbox claim/renew/ack/fail/status use cases. Every completion checks
Worker, fencing token, state, and live lease against a single
PostgreSQL-generated operation time after locking the exact lease row; callers
cannot inject absolute lease times, and lock wait cannot preserve an expired
owner.
Duration inputs must survive PostgreSQL microsecond conversion exactly. New
Outbox rows preserve immutable initial availability separately from the mutable
retry cursor, and identity replay compares that initial time plus creation,
payload, digest, and destination. Cross-Tenant Transport Message ID reuse
returns a typed conflict before dispatch without revealing the existing row.
Inbox consume owns one transaction covering dedupe acquisition, the caller's
database effect, and completion; an effect error rolls all three back. Adapters
return messaging domain values and never expose generated rows.

The B02.3 adapter validates and bounds Tenant-qualified parent facts required
by runtime control, prelocks their deduplicated WorkOrder set in global order,
then admits each fact in a stable parent/identity order. It exposes atomic
SystemSafetyControl and AgentRuntimeCommand append plus AgentRunControlFanout
create/read/claim/renew/progress use cases. The read use case locks the root and
targets and verifies the latest domain digest, allowing reconciliation after a
committed progress response is lost. Command sequence and target fencing are
allocated under row locks.
Each accepted command/control row stores its unique Outbox identity, payload
digest, fixed destination, availability time, and creation time; an initially
deferred composite foreign key makes the transaction fail if the exact B02.2
Outbox row is absent. Replays require the original ledger digest and Outbox
binding. Fanout creation replay compares version one, immutable target
identity, command/control digests, and Outbox bindings even after progress has
advanced the latest version. Claims commit before any runtime side effect, and
stale or expired claim tokens cannot advance progress.

Platform Safety Controller and trigger-evidence parents are consumption-only in
B02.3: `agent_app` has no INSERT privilege and no generic authority-admission
method exists. System safety writes additionally require an injected authority
verifier before the transaction starts; missing production verification fails
closed. The current slice does not implement the authoritative evidence source,
reason-to-Contract map, or authenticated WorkloadIdentity adapter.

Fanout creation rejects an active AgentRun without a matching active RuntimeRun.
Database admission guards share the WorkOrder lock, so a new Run or accepted
Child Admission cannot race version one; a rejected late-spawn decision remains
an appendable denial receipt.

The B03.1 WorkflowRun repository records only a caller-confirmed durable
orchestration start. It validates framework-neutral domain values, locks the
Tenant-qualified WorkOrder, rejects terminal or time-inconsistent authority,
and appends one immutable binding. Exact replays return the persisted fact;
WorkflowRun ID, WorkOrder, or binding-digest reuse with different content fails
closed. The repository never contacts Temporal and exposes no pgx, sqlc, native
Run ID, namespace, endpoint, or History value.
