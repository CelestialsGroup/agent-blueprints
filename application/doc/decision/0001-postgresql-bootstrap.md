# B02.1 PostgreSQL Bootstrap Selection

Date: 2026-07-23

Status: accepted for the B02.1 implementation slice. This records component
selection and test evidence requirements, not 0B completion or production
approval.

## Locked Inputs

| Input | Pin | License / source |
|---|---|---|
| pgx v5 | `v5.10.0` | MIT, `github.com/jackc/pgx` tag from 2026-06-03 |
| goose v3 | `v3.27.2` | MIT, official 2026-06-30 release; Linux arm64 binary SHA-256 is locked |
| sqlc | `v1.31.1` | MIT, official 2026-04-22 release and OCI index digest |
| Staticcheck | `2026.1` / module `v0.7.0` | MIT, official 2026-02-13 release; Linux arm64 archive SHA-256 is locked |
| PostgreSQL | `18.4-bookworm` | PostgreSQL License, official image index digest `sha256:1961f96e6029a02c3812d7cb329a3b03a3ac2bb067058dec17b0f5596aca9296` |

The executable values live in `toolchain/toolchain.env`; licenses, public source
URLs, package URLs, and component ownership live in `toolchain/third-party.json`.
The PostgreSQL digest is the multi-architecture official image index. Docker
selects its immutable platform manifest for the host architecture.

## Admission Review

| Input | Maintenance / security source | Alternatives reviewed | Rollback boundary |
|---|---|---|---|
| pgx v5 | Active tagged releases; GitHub Security Advisories | `database/sql` with pgx stdlib | Revert `go.mod`/`go.sum`, regenerate, rerun real-PostgreSQL tests |
| goose v3 | Active official releases; GitHub Security Advisories | golang-migrate, Atlas | Restore the prior verified binary only after version-table compatibility tests |
| sqlc | Active official releases; GitHub Security Advisories | hand-written pgx adapters, sqlx | Restore image digest and generated tree together; require zero generation diff |
| Staticcheck | Active official releases; GitHub Security Advisories | `go vet` only, golangci-lint | Restore the prior verified archive without suppressing analyzer failures |
| PostgreSQL | Supported by the PostgreSQL versioning policy and security page | PostgreSQL 17, developer-installed server | Restore a backup into the prior admitted image; never downgrade a data directory in place |

The machine-enforced forms, review date, exact URLs, and per-component strategy
are in `toolchain/third-party.json`. The supply-chain Gate rejects any of these
five admissions when maintenance status, security review source, alternatives,
or rollback strategy is absent.

## Decision

Use pgx v5 for explicit pool/transaction control, sqlc for reviewed SQL and
rebuildable adapters, and SQL-first goose migrations. Use a real disposable
PostgreSQL container for DDL, role, RLS, and pool-reuse evidence. This follows the
locked Blueprint and keeps ORM behavior, a developer-installed database, and
mocked SQL outside the correctness boundary.

The first migration is privileged only long enough to establish NOLOGIN
Migrator/Application group roles and transfer ownership. Application login roles
are provisioned externally as members of `agent_app`; they do not own
tables, cannot execute DDL, and have neither superuser nor `BYPASSRLS`. The
Application group receives exactly `SELECT, INSERT` on the two bootstrap tables.

PostgreSQL roles are cluster-global, so the fixed `agent_migrator` and
`agent_app` roles are bound by role comment to the first bootstrapped database
name. A different database in the same cluster is rejected before Agent schema
creation or privilege grants. This slice therefore supports one Agent database
name per PostgreSQL cluster; a separate Agent database requires a separate
cluster. Recreating the bound database with the same name is supported.

Bootstrap runs under the cluster administrator. Every later goose execution
uses an externally provisioned Migrator Login that is a member of
`agent_migrator`; each migration wraps DDL in explicit `SET ROLE
agent_migrator` / `RESET ROLE`. The integration probe proves goose version-table
access, group-role object ownership, and rollback through that path. Running
later DDL as the Login without `SET ROLE` is unsupported because it would assign
ownership to the Login.

## Upgrade And Rollback

Library/tool upgrades are separate reviewed changes: update the exact version and
digest, regenerate sqlc output, run the full implementation Gate, and retain the
previous release artifact/digest for tool rollback. PostgreSQL patch/minor image
updates must rerun bootstrap and repository isolation tests before adoption.
The detailed component-specific rollback analysis is machine-enforced in the
third-party inventory rather than inferred from this summary.

Database evolution is expand, backfill, verify, contract. Bootstrap Down is
forward-only because deleting cluster roles, ownership, or tenant tables cannot
be inferred safe. The test suite proves a rejected Down leaves version 1 and its
schema intact; recovery is a new reviewed forward migration.
