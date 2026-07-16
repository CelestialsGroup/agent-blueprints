# Contract Validation Report — v0.8.3

Status: **local re-hardening evidence complete except Go/public matrix; repository-root integration and public re-admission remain pending; candidate is not frozen**

Validation date: 2026-07-16

## Executed in this workspace

| Check | Result |
|---|---|
| Official Bootstrap from a clean ZIP with CPython 3.12 and npm | pass with the exact command; Python hashes and npm integrity enforced |
| Supply-chain Gate after virtual-environment creation | pass; generated `.pyc` ignored, tracked bytecode/`.DS_Store` remain forbidden |
| Source-only static audit | pass: 175 JSON, 21 YAML, 4 OpenAPI, 91 Markdown at execution time |
| JSON Schema | pass: 112 schemas |
| Fixtures | pass: 35 valid, 11 schema-invalid |
| Semantic invariants | pass: 4 state-machine checks and 12 negative fixtures |
| Contract Manifest | pass in Python and Node: 122 governed resources |
| Compatibility self-tests | pass for reported Schema/OpenAPI/state-machine cases |
| Compatibility baseline | N/A locally: no publicly admitted frozen baseline; CI fail-closed behavior separately tested |
| CI missing-baseline negative test | pass: `CI=true` without protected exception exits non-zero |
| Python JCS/Strict I-JSON | pass: 5 valid + 7 invalid |
| Node JCS/Strict I-JSON | pass: 5 valid + 7 invalid |
| OpenAPI | pass: 4 documents, each 0 errors / 0 warnings |
| OpenAPI Bundle | pass: 4 bundles; second generation byte-identical |
| Go JCS/Strict I-JSON | not executed locally: Go toolchain unavailable |

Local runtime differed from the public matrix (CPython 3.12.13, Node 24.14.0). A clean ZIP extraction executed `./scripts/bootstrap_contracts.sh` successfully and `make validate-all` passed every step through Node JCS before stopping only because this runner has no `gofmt`/`go`; the OpenAPI and deterministic Bundle gates were then executed separately and passed. This local evidence does not substitute for the pinned GitHub Actions Python 3.11/3.13, Node 22.16 and Go 1.23.2 run.

## Required public admission

```bash
./scripts/bootstrap_contracts.sh
make validate-all
```

For a monorepo, first run `scripts/install_github_workflow.sh`, commit the Git-root Workflow, configure `AGENT_PLATFORM_CONTRACT_ROOT`, and configure the protected compatibility variables. Only a public CI run that includes Go tests/gofmt, both Python versions and deterministic bundles can support a freeze proposal. No production reliability claim is made by this report.
