# Contract Validation Report — v0.9.0

Status: **local product-boundary contract closure complete; repository/CI integration excluded from this architecture review; candidate is not frozen and not production ready**

Validation date: 2026-07-17

| Check | Local result |
|---|---|
| Source-only static audit | pass: 271 JSON, 22 YAML, 5 OpenAPI, 109 Markdown files |
| JSON Schema and fixtures | pass: 143 schemas, 79 valid fixtures, 16 schema-invalid fixtures |
| Semantic invariants | pass: 6 deterministic/schema-aligned state machines and 60 negative fixtures |
| Product boundary closure | pass: Conversation/Branch/Turn, Agent Runtime, Recording, Experience admission and explicit CommercialAuthorization binding |
| Contract Manifest | pass: 157 governed resources; Python 3.11/3.13 and Node 22.16 agree |
| Compatibility comparator | self-tests pass; local baseline N/A because no frozen Git ref was supplied |
| Python JCS/Strict I-JSON | Python 3.11 and 3.13 pass |
| Node JCS/Strict I-JSON | Node 22.16 pass |
| Go JCS/Strict I-JSON | Go 1.23.2 linux/arm64 pass; gofmt pass |
| OpenAPI | pass: 5 documents, each 0 errors and 0 warnings |
| OpenAPI bundle | pass: 5 bundles, second generation byte-identical |

Repository-root Workflow, hidden-file policy and protected CI variables were intentionally excluded from this review. This does not weaken the runtime acceptance boundary: Phase 0 still needs real migrations, DeerFlow/Sandbox adapters, failure injection, Temporal replay, isolation, capacity and recovery evidence before any production claim.
