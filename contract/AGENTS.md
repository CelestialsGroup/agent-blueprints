# Agent Application Platform Contract Rules

## Authority

This directory owns Schema, OpenAPI, state machines, event registries, semantic constraints, fixtures, Conformance Suites, compatibility manifests, and their validation tools. Architecture intent and development rules remain in the separately versioned Blueprint; product code, migrations, deployment configuration, and runtime evidence remain in Application.

Use `AGENT_PLATFORM_BLUEPRINT_ROOT` for an external read-only Blueprint checkout. The `../blueprint` fallback is only a local default. Contract resources must not depend on a common Git history or hard-coded sibling path. Cross-repository Blueprint references use version-independent `urn:agent-platform:blueprint:<path>` identifiers and resolve through the configured root; immutable consumption is proven separately by the Blueprint Source Revision.

## Change Discipline

- Update every affected Schema, OpenAPI document, state machine, event registry, semantic rule, fixture, Conformance Suite, compatibility manifest, and report together.
- Preserve Draft 2020-12 absolute IDs, Strict I-JSON, RFC 8785 JCS, deterministic bundles, and fail-closed compatibility behavior.
- Every `contract_gate` check ID must be registered and executed in the current Gate. Every `phase0_implementation_required` mapping must resolve to a Contract Suite test or a Blueprint responsibility ID.
- Do not add product source, database migrations, Kubernetes deployment resources, or implementation evidence here.
- Do not claim global exactly-once or promote third-party runtime, sandbox, thread, checkpoint, endpoint, local database, hook, or trace state into the stable contract.

## Validation

Run `make validate-contract` for Contract changes. Run `make validate-all` when preparing repository admission or formal freeze. Keep Contract Gate, 0B implementation, 0C-0G integration, 0H reliability, formal freeze, and production approval as separate conclusions.
