# Agent Migrate

Phase: **0B**.

This process runs pinned, SQL-first goose migrations as an independent job. It
will support explicit `up`, compatibility rollback, and verification commands
used by empty-database and upgrade tests.

The API and workers must never auto-migrate on startup. Destructive contract
migrations require expand/backfill/verify evidence before they can run.

The first migration is the one-time bootstrap-admin exception because PostgreSQL
role creation requires cluster-level authority. It creates NOLOGIN group roles
and transfers table ownership to `agent_migrator`. After bootstrap,
deployment-specific LOGIN identities are provisioned outside SQL and future
migrations connect through a Migrator member Login. Every later migration must
explicitly `SET ROLE agent_migrator` around DDL so ownership is assigned to the
NOLOGIN group rather than the Login. Application identities receive only
`agent_app` and cannot execute DDL or bypass RLS.
