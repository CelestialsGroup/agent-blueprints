# Agent Migrate

Phase: **0B**.

This process runs pinned, SQL-first goose migrations as an independent job. It
will support explicit `up`, compatibility rollback, and verification commands
used by empty-database and upgrade tests.

The API and workers must never auto-migrate on startup. Destructive contract
migrations require expand/backfill/verify evidence before they can run.
