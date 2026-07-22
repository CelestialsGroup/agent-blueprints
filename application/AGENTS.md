# Agent Application Platform Implementation Rules

## Authority

The independently versioned Blueprint owns architecture intent and development rules. The independently versioned Contract owns Schema, OpenAPI, state machines, event registries, semantic constraints, fixtures, and Conformance Suites. In the current sibling layout they default to `../blueprint` and `../contract`; `AGENT_PLATFORM_BLUEPRINT_ROOT` and `AGENT_PLATFORM_CONTRACT_ROOT` must support external read-only checkouts when repositories split. Do not create copied contract truth inside this directory.

Before implementation, read the locked Blueprint's
`docs/53_APPLICATION_DEVELOPMENT_STANDARDS.md`. Application-local README and
tool configuration may strengthen those rules but must not weaken them.

Every CI, build, and Conformance result must bind exact Blueprint and Contract versions, full source revisions, Contract Manifest Digest, and consumed Suite Digests. A branch name, relative path, or mutable tag is not a dependency lock.

`dependency-lock.json` is the Application-owned immutable input lock. Refresh it
only after reviewing an upstream change, then verify it before compilation and
include its digest and contents in generated evidence.

## Boundaries

- Go owns the platform kernel, SQL transactions, Temporal workflows, Outbox/Inbox, fencing, ledgers, gateways, and the Reference Runtime Probe.
- Python owns the Native Runtime and Python ecosystem adapters behind versioned platform Ports. It must not read the platform database or Temporal persistence.
- PostgreSQL owns current state, ledgers, Outbox, and Inbox; Temporal owns durable orchestration history; Redis is only cache, presence, and wakeup.
- Reliability is at-least-once plus idempotency, fencing, and reconciliation. Never claim global exactly-once.
- Third-party Agent frameworks are references only and must not become dependencies or fact sources.

## Validation

Run `make validate-implementation` for implementation changes and `make validate-contract` in the Contract checkout for machine-contract changes. Keep Contract Gate, component completion, end-to-end integration, reliability evidence, formal freeze, and production approval as separate maturity claims.
