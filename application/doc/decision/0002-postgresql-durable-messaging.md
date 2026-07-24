# 0002 PostgreSQL Durable Messaging

Date: 2026-07-23

Status: implemented candidate awaiting review. This decision applies only to
B02.2 and does not freeze a Broker, Redis provider, public event envelope, or
production topology.

## Context

The locked Blueprint requires PostgreSQL-authoritative transactional Outbox and
Inbox, at-least-once delivery, idempotent consumers, leased
`FOR UPDATE SKIP LOCKED` claims, fencing, reconciliation, RLS, and no network I/O
inside database transactions. The locked Contract additionally defines
transport Inbox identity and the Canonical Event source tuple/Dedupe Key. The
locked Canonical string schemas permit escaped NUL while PostgreSQL identifiers
cannot represent it, so that source-identity sub-scope cannot be implemented
without an upstream Contract decision. B02.1 already provides separate database
roles and transaction-local TenantContext.

## Decision

Use two Tenant-qualified PostgreSQL tables owned by `agent_migrator`:

- `outbox_messages` stores exact encoded bytes and SHA-256, with an internal
  1 MiB storage limit. Its state is `pending`, `leased`, `succeeded`, or
  `terminal_failed`; every claim increments both attempt and fencing token.
  Its Transport Message ID is globally unique across Tenants.
- `transport_inbox_messages` stores globally scoped transport identity, payload
  digest, and atomic completion state.

Lease renewal, acknowledgement, retryable failure, and terminal failure require
the same Worker, fencing token, `leased` state, and an unexpired lease. Expired
claims are reclaimed with a higher token. The dispatcher claims and commits
before calling its transport port, then records a fenced result in a separate
transaction. Each result mutation locks the exact lease row before materializing
its PostgreSQL operation time, so time spent waiting for that row lock cannot
preserve an owner whose lease has since expired.

PostgreSQL, not a Worker wall clock, supplies one operation timestamp for Claim,
Renew, Ack, and Fail. Workers submit only duration values: leases are limited to
five minutes and retry delays to 24 hours, both at PostgreSQL's microsecond
precision. The dispatcher starts one attempt deadline before renewing each row,
then uses the remaining budget for transport. Because that total budget is
shorter than the lease, renewal latency cannot move the transport deadline past
the database lease. Renewal loss or exhausted budget prevents the send.

The Application Role has table-level `SELECT` but only column-level `INSERT` and
`UPDATE` grants for the fields used by the reviewed sqlc statements. Identity,
payload, digest, destination, and creation-time columns cannot be updated through
that role.

Inbox acquisition, database side effect, and completion share one Tenant
transaction. `(consumer, message_id)` is globally unique as required by the
transport identity. Matching global Outbox uniqueness prevents two Tenants from
committing messages that would collide only after delivery. A conflicting
Tenant cannot read the existing row.

Failure kinds use a stable lowercase ASCII snake-case domain value and the same
database constraint. Raw transport error text is never a valid failure kind.

Canonical source identity and Dedupe Key persistence are deferred. Tightening
Contract strings or selecting a stable database encoding is an upstream Wire
decision, not a local Application workaround.

The 1 MiB ceiling is an Application-private queue guard, not a Wire Contract
limit. Public adapters must still enforce their operation-specific encoded-body
limit before enqueue. Large content remains an immutable reference and digest.

## Alternatives Rejected

- Broker plus database dual writes: cannot atomically preserve committed intent.
- Redis Stream, Pub/Sub, lock, or process memory as delivery truth: violates the
  accepted authority and loss-recovery boundary.
- Holding the claim transaction during network delivery: expands lock duration
  and violates the transaction rule.
- Worker identity without a fencing token: an expired Worker could acknowledge a
  newer owner's delivery.
- Worker-supplied absolute lease timestamps: clock skew could reclaim early or
  let an actually expired owner complete a message.
- One unrenewed lease for a sequential batch: later rows could be sent after a
  new Worker reclaimed them.
- Canonical source Inbox in B02.2: the locked Contract/PostgreSQL representation
  gap must be closed upstream before Application implementation.
- Full CanonicalEvent/Registry admission in B02.2: exceeds this slice and would
  conflate source dedupe with Event schema and Projection acceptance.

## Compatibility And Rollback

This is an additive migration and introduces no public API. Empty tables may be
removed by Down. Once either table contains durable facts, Down refuses and
recovery requires a reviewed forward migration. The current pgx/goose/sqlc and
PostgreSQL pins are reused unchanged; no new dependency rollback path is needed.

Changing message identity, payload hashing, source Dedupe semantics, state
meaning, or fencing behavior is not a local refactor. It requires an explicit
compatibility review and, where public behavior changes, coordinated
Blueprint/Contract work before Application changes.
