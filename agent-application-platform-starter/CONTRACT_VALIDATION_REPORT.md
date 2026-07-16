# Contract Validation Report — v0.8.2

Status: **local admission evidence complete except Go/public matrix; candidate is not frozen**

Validation date: 2026-07-16

## Executed in this workspace

| Check | Result |
|---|---|
| Public Bootstrap with CPython 3.12 and npm | pass; Python hashes and npm integrity enforced |
| Supply-chain Gate | pass |
| Source-only static audit | pass: 164 JSON, 21 YAML, 4 OpenAPI, 88 Markdown at execution time |
| JSON Schema | pass: 111 portable schemas |
| Fixtures | pass: 32 valid, 11 schema-invalid |
| Semantic invariants | pass: 5 negative fixtures |
| Contract Manifest | pass in Python and Node: 119 governed resources |
| Compatibility | N/A: no publicly admitted frozen baseline; comparator self-tests pass |
| Python JCS/Strict I-JSON | pass: 5 valid + 5 invalid |
| Node JCS/Strict I-JSON | pass: 5 valid + 5 invalid |
| OpenAPI | pass: 4 documents, each 0 errors / 0 warnings |
| OpenAPI Bundle | pass: 4 bundles; second generation byte-identical |
| Go JCS/Strict I-JSON | not executed locally: Go toolchain unavailable |

Local runtime differed from the public matrix (CPython 3.12, Node 24.14). This is useful local evidence but does not substitute for the pinned GitHub Actions Python 3.11/3.13, Node 22.16 and Go 1.23.2 run.

## Required public admission

```bash
./scripts/bootstrap_contracts.sh
make validate-all
```

Only a public CI run that includes Go tests/gofmt, both Python versions and deterministic bundles can support a freeze proposal. No production reliability claim is made by this report.
