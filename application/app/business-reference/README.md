# Business Reference

Phase: **0C, not implemented**.

This application will prove the Business/Agent Platform boundary with a small,
independent User, Organization, Membership, Entitlement, Quota Reservation,
Commercial Authorization, WorkSession, and Settlement flow.

- `api/` will be an independent Go module and deployable API.
- `web/` will be the Next.js reference UI.
- `db/` will own Business-only migrations and queries.

The subsystem uses a separate PostgreSQL database and signing keys. It is a
reference integration, not the Agent Platform's source of truth for pricing,
payment, balance, or membership, and it must never share migrations, database
connections, or signing authority with the Agent Platform.
