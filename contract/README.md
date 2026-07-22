# Agent Application Platform Contract

This directory is the independently versioned executable specification for the Agent Application Platform. It owns machine-readable behavior, compatibility metadata, validation tooling, and Contract Gate evidence. It does not own architecture prose or product implementation.

## Contents

- `contracts/schemas/`: Draft 2020-12 JSON Schema wire contracts.
- `contracts/openapi/`: OpenAPI 3.1 provider and gateway contracts.
- `contracts/state-machines/`: executable lifecycle definitions.
- `contracts/event-types/`: governed event registries.
- `contracts/semantic-constraints-v1.json`: semantic enforcement traceability.
- `contracts/conformance/`: content-addressed provider conformance suites.
- `contracts/testdata/` and `examples/`: positive and negative fixtures.
- `scripts/`: validation, compatibility, JCS, manifest, and supply-chain gates.

Architecture intent and Phase responsibilities live in a separately versioned Blueprint. Set `AGENT_PLATFORM_BLUEPRINT_ROOT` to its read-only checkout. The current sibling default is `../blueprint`; this default is local convenience, not a repository contract.

## Validation

Bootstrap the pinned toolchain once, then run the canonical Contract Gate:

```bash
./scripts/bootstrap_contracts.sh
make validate-contract
```

`make validate-architecture` remains a temporary compatibility alias. `make validate-all` additionally enforces supply-chain admission and is required for formal freeze preparation. CI configuration is owned by the deployment repository rather than this Contract package.

Successful validation regenerates `VALIDATION.json` and `CONTRACT_VALIDATION_REPORT.md`. A green Contract Gate proves internal contract consistency only. It does not prove 0B implementation, 0C-0G integration, 0H reliability, formal freeze, or production approval.
