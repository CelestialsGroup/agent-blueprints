# Durable Messaging

Phase: **0B current priority**.

Implement Outbox claiming, dispatch state, Transport Inbox deduplication,
retry classification, wakeup hints, and reconciliation scheduling here. The
database commit is authoritative; publication and consumption are at least
once.

Redis is permitted only as a wakeup optimization. A Redis flush or lost wakeup
must not lose committed work, authorization, event cursors, or ledger facts.

B02.2 provides domain-valued messages, exact payload digests, stable ASCII
failure kinds, lease/fencing values, and a transport dispatcher. Transport
Message IDs are globally unique across Tenants so valid Outbox rows cannot
collide only after reaching a global `(consumer, message_id)` Inbox. The
dispatcher depends on narrow Store and Transport ports, claims a
bounded committed batch, and starts a lease-shorter attempt budget before each
pre-send renewal so database latency reduces the remaining transport time. It
records only fenced success or classified failure. PostgreSQL owns lease time;
Workers provide only bounded, whole-microsecond lease/retry durations. No Redis
adapter or external Broker is part of this slice.

Canonical source identity/Dedupe Key support is not part of B02.2. The locked
Contract permits escaped NUL in source strings while PostgreSQL text cannot
represent it; Application does not tighten that Wire contract locally.

B02.3 extends this Outbox with immutable initial availability, leaving
`next_attempt_at` mutable for retries, and adds Tenant-qualified deferred foreign
keys from each accepted Runtime Command and System Safety Control to one fixed
Message ID, payload digest, destination, initial availability, and creation
time. A ledger replay cannot enqueue the same fact under a second Outbox
identity and still succeeds after retry scheduling. This proves committed intent
for the bounded control component, not Contract-valid Canonical Platform Event
persistence.
