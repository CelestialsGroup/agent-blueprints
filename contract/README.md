# Agent Contract

This directory contains the independently versioned, declarative agreements for the Agent. It defines machine-readable behavior and compatibility metadata; it contains no executable tooling or product implementation.

## Contents

- `schemas/`: Draft 2020-12 JSON Schema wire agreements.
- `openapi/`: OpenAPI 3.1 provider and gateway agreements.
- `state-machines/`: lifecycle and transition agreements.
- `event-types/`: governed event registries.
- `semantic-constraints-v1.json`: semantic responsibility traceability.
- `conformance/`: content-addressed provider conformance suites.
- `testdata/`: positive and negative contract fixtures.
- `compatibility/`: candidate compatibility policy and resource manifest.
- `examples/`: valid example documents referenced by the agreements.

Architecture intent and Phase responsibilities live in the separately versioned Blueprint. Validation code, dependency locks, build output, and Contract Gate reports live outside this package under `script/contract/` or an equivalent release-governance system.

Consumers must lock an immutable Contract source revision and verify the declared Manifest and Suite digests. A passing external Contract Gate proves internal contract consistency only; it does not prove 0B implementation, 0C-0G integration, 0H reliability, formal freeze, or production approval.
