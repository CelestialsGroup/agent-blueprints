# Migrations

Phase: **0B current priority**.

Write ordered goose SQL migrations here. The first sequence must establish
extensions, tenant context, Phase 0B tables, constraints and indexes, RLS,
Outbox/Inbox, CAS versions, fencing, ledgers, and verification queries.

Every migration needs empty-database upgrade evidence and a reviewed rollback
classification. Production evolution follows expand, backfill, verify, then
contract; unsafe down migrations must fail explicitly rather than lose data.
