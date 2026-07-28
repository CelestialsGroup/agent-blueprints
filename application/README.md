# Agent

This directory contains the independently versioned Agent implementation. Architecture and development rules remain in the Blueprint; schemas, OpenAPI definitions, state machines, event registries, semantic constraints, fixtures, and Conformance Suites remain in the Contract. Current sibling checkouts default to `../blueprint` and `../contract`; external checkouts are selected with `AGENT_BLUEPRINT_ROOT` and `AGENT_CONTRACT_ROOT`.

The implementation consumes both upstreams read-only. It must not copy or redefine Contract resources as a second source of truth, and build/Conformance evidence must record exact Blueprint/Contract revisions and manifest/suite digests.

The Go module identity is `github.com/shell-echo/agent`.
The Business Reference subsystem remains in this repository for Phase 0C, but
its API, Web, database, signing keys, and dependency graph are independent from
the Agent Platform kernel.

Coding, database, language, test, review, and Definition of Done rules are
defined by the locked Blueprint's
`docs/53_APPLICATION_DEVELOPMENT_STANDARDS.md`.

The current implementation provides:

- the Go Agent Access process and lifecycle health endpoints;
- the Python Native Runtime package bound to `runtime-core-v1`;
- reproducible build, dependency, SBOM, and provenance evidence;
- the B02.1 PostgreSQL bootstrap with separate Migrator/Application roles,
  Tenant/ClientApplication RLS, pgx transactions, and a sqlc-backed repository;
- a disposable PostgreSQL 18.4 harness proving migration and tenant isolation
  against a real database;
- the B02.2 PostgreSQL transactional Outbox/Inbox, leased and fenced dispatcher
  store, globally unique Transport Message IDs, and atomic consumer dedupe;
- repeated real-PostgreSQL race evidence for concurrent claims, lease recovery,
  Inbox idempotency, and cross-tenant denial;
- the bounded B02.3 PostgreSQL Runtime Command, System Safety Control, and
  AgentRun Control Fanout ledgers, with Tenant-qualified authority parents,
  full command/control Outbox delivery bindings, monotonic version snapshots,
  leased claims, fencing, recovery, and reconciliation evidence. System safety
  writes remain fail-closed until a production authority verifier and
  authoritative controller/evidence admission slice exist;
- the bounded B03.1 Temporal foundation: framework-neutral orchestration values,
  an immutable PostgreSQL WorkflowRun start-confirmation ledger, stable
  WorkOrder-derived Workflow IDs, lost-response reconciliation, deterministic
  Workflow/Activity boundaries, a versioned Worker, sanitized History Replay,
  and repeated real Temporal/PostgreSQL recovery evidence. No production caller
  is wired to Workflow Start.

## Repository map

| Path | Responsibility | First phase |
|---|---|---|
| `app/` | Agent Workbench and the independent Business Reference system | 0C / 0E |
| `cmd/` | Deployable Go process composition roots | 0B |
| `db/` | SQL-first goose migrations and sqlc query sources | 0B |
| `doc/` | Implementation decisions and operational runbooks | 0B+ |
| `internal/` | Go domain kernel and infrastructure adapters | 0B |
| `runtime/` | Primary Python Native Runtime | 0B |
| `provider/` | Platform Capability and Sandbox Provider implementations | 0D |
| `package/` | Generated or genuinely shared TypeScript workspace packages | 0C+ |
| `test/` | Conformance, integration, Replay, fault, and end-to-end tests | 0B+ |
| `deploy/` | Local and Kubernetes environment assembly | 0B+ |
| `toolchain/` | Toolchain, dependency, SBOM, and provenance inputs | B01 |
| `script/` | Deterministic build and validation automation | B01 |

`dependency-lock.json` binds every build and evidence result to exact Blueprint
and Contract source snapshots, the Contract Manifest, and consumed Conformance
Suites. The lock is verified before compilation.

Each architecture directory has a README defining what belongs there and what
must not become a fact source. Language-standard directories such as Python
`src/` and package-local test folders follow their ecosystem conventions and do
not create additional architecture layers.

The scaffold is a responsibility map, not implementation evidence. Current
work proceeds through 0B persistence and Native Runtime Core before later
Business, Sandbox, Workbench, Gateway, or Reference Probe components are built.

Run the implementation Gate from this directory:

```bash
make validate-implementation
```

Local sibling paths are only defaults:

```bash
AGENT_BLUEPRINT_ROOT=/path/to/blueprint \
AGENT_CONTRACT_ROOT=/path/to/contract \
make validate-implementation
```

Only the Tenant/ClientApplication bootstrap, B02.2 durable messaging, bounded
B02.3 runtime-control ledgers, and bounded B03.1 orchestration foundation are
implemented. B02.3's narrow parent facts close only the foreign-key and
transaction invariants consumed by those slices; they are not complete
lifecycle models. Authenticated production Start-intent ownership, WorkOrder
Start Outbox/Event atomicity, RootBinding, RunManifest, Safety authority
admission, CanonicalEvent admission/Projection, Runtime HTTP operations, and
product execution remain future slices. Canonical source Inbox is specifically
blocked until the locked Contract defines a PostgreSQL-representable identifier
profile or stable encoding.
