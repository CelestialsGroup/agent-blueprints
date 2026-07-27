# Implementation Decisions

Record decisions that affect code organization, dependency selection,
deployment, or operations without changing architecture meaning. Each decision
should include context, chosen option, rejected options, compatibility impact,
rollback path, and the governing Blueprint/Contract revisions.

If a decision changes ownership, wire behavior, an invariant, or a maturity
claim, stop and change the upstream Blueprint or Contract first.

Current records:

- `0001-postgresql-bootstrap.md`: PostgreSQL roles, toolchain, topology, and
  B02.1 migration boundary.
- `0002-postgresql-durable-messaging.md`: B02.2 Outbox/Inbox state, lease/fencing,
  encoded storage guard, and rollback boundary.
- `0003-postgresql-runtime-control-safety-ledgers.md`: B02.3 narrow authority
  parents, command/control Outbox bindings, Fanout versions/leases, and rollback
  boundary.
