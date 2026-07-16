# Contract Validation Report

Baseline: **v0.8.1 Contract Hardening Candidate**  
Generated at: 2026-07-16T03:59:29.136581Z

## Offline validation: passed

- Package files: 283
- Portable JSON Schema resources: 104
- JSON files parsed: 148
- YAML files parsed: 26
- Markdown files scanned: 84
- OpenAPI documents structurally audited: 4
- Positive fixtures: 27
- Schema-negative fixtures: 11
- Semantic-negative fixtures: 3
- Strict I-JSON raw-negative fixtures: 4
- Node RFC 8785 valid vectors: 5
- Go RFC 8785 valid vectors: 5
- Contract Manifest resources: 111
- Contract Manifest digest:
  `sha256:68577ac45d555ff509a7c0e73b71dfd751eabbf409908f2e9ec1f2ac3acf529f`

## Commands actually run

```bash
python3 scripts/check_supply_chain.py
python3 scripts/offline_static_audit.py
node scripts/jcs/verify_node.mjs
cd scripts/jcs/go && go test ./...
python3 scripts/validate_contracts.py
node scripts/verify_contract_manifest.mjs
python3 -m compileall -q scripts
```

The local container already included:

```text
jsonschema 4.26.0
referencing 0.37.0
PyYAML 6.0.3
```

The official Python `rfc8785==0.1.4` wheel was not installed because the current
container cannot access public package registries. The Python structural/digest validation
was exercised with an equivalent local bridge to the repository's Node RFC 8785 implementation.
This does **not** replace the required public CI run of the official Python package.

## Pending public CI

The following are intentionally not claimed as passed:

- `./scripts/bootstrap_contracts.sh`
- official Python rfc8785 vectors
- public npm `npm ci`
- Redocly lint 0 error / 0 warning for all 4 OpenAPI documents
- deterministic Redocly bundles
- GitHub Actions Python 3.11/3.13 Matrix

## Freeze condition

```bash
./scripts/bootstrap_contracts.sh
make validate-all
```

must pass in public CI before the baseline is frozen for Codex Phase 0.
