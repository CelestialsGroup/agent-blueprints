#!/usr/bin/env sh
set -eu

ROOT="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
cd "$ROOT"

PYTHON="${PYTHON:-.venv/bin/python}"

"$PYTHON" scripts/check_supply_chain.py
"$PYTHON" scripts/offline_static_audit.py
"$PYTHON" scripts/validate_contracts.py
"$PYTHON" scripts/validate_semantics.py
"$PYTHON" scripts/check_contract_compatibility.py
node scripts/verify_contract_manifest.mjs
"$PYTHON" scripts/jcs/verify_python.py
node scripts/jcs/verify_node.mjs
test -z "$(gofmt -l scripts/jcs/go/*.go)"
(
  cd scripts/jcs/go
  go test ./...
)

"$PYTHON" scripts/prepare_openapi.py
node scripts/lint_openapi_zero.mjs

echo "All Contract, semantic, compatibility, JCS, supply-chain and zero-warning OpenAPI gates passed."
