# Migrations

Phase: **0B current priority**.

Write ordered goose SQL migrations here. The first sequence must establish
extensions, tenant context, Phase 0B tables, constraints and indexes, RLS,
Outbox/Inbox, CAS versions, fencing, ledgers, and verification queries.

Every migration needs empty-database upgrade evidence and a reviewed rollback
classification. Production evolution follows expand, backfill, verify, then
contract; unsafe down migrations must fail explicitly rather than lose data.

`00001_agent_bootstrap.sql` is a bootstrap-admin migration. It creates the
NOLOGIN `agent_migrator` and `agent_app` group roles, then the
minimal Tenant/ClientApplication tables. A deployment system provisions LOGIN
identities and grants exactly one group role; passwords and workload identities
never belong in migrations.

The fixed group roles are cluster-global and are bound to the first bootstrapped
database name. Bootstrap rejects a different Agent database in that cluster;
deploy another PostgreSQL cluster when another Agent database is required.
After bootstrap, goose connects as an external Migrator Login and every
migration must explicitly `SET ROLE agent_migrator` around DDL so created
objects remain owned by the NOLOGIN group role. The Login must never be granted
`agent_app`.

The bootstrap changes cluster roles, ownership, and database privileges, so its
Down section is explicitly forward-only. Integration tests verify that Down is
rejected without changing the applied version or schema, and that a repeated Up
is a no-op. Recovery requires a reviewed forward migration.

`00002_postgresql_durable_messaging.sql` adds the Tenant-qualified Outbox and
Transport Inbox, globally unique Transport Message IDs, claim/reconciliation
indexes, enabled/forced RLS, and exact Application grants. Durable tables expose
table-level `SELECT` plus only the column-level `INSERT`/`UPDATE` permissions used
by reviewed sqlc statements; immutable identity, payload, and creation fields do
not receive update permission. Its Down is safe only for empty tables. The owner
temporarily removes FORCE inside the Down transaction to perform the all-row
emptiness guard; a non-empty result raises and rolls the RLS change and goose
version back atomically. Digest and stable failure-kind checks use PostgreSQL's
built-in `C` collation for locale-independent ASCII semantics, and a leased row
must expire strictly after its last update.

Canonical source identity columns are deliberately absent until the locked
Contract closes its PostgreSQL string-representation gap.
