#!/usr/bin/env sh
set -eu

SCRIPT_ROOT="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
cd "$SCRIPT_ROOT"

export AGENT_CONTRACT_ROOT="${AGENT_CONTRACT_ROOT:-$SCRIPT_ROOT/../contract}"
export AGENT_BLUEPRINT_ROOT="${AGENT_BLUEPRINT_ROOT:-$SCRIPT_ROOT/../blueprint}"

PYTHON="${PYTHON:-.venv/bin/python}"

"$PYTHON" contract/validation/check_supply_chain.py
"$PYTHON" contract/validation/offline_static_audit.py
"$PYTHON" contract/validation/validate_contracts.py
"$PYTHON" contract/validation/validate_semantics.py
"$PYTHON" contract/compatibility/check_contract_compatibility.py
node contract/manifest/verify_contract_manifest.mjs
"$PYTHON" contract/jcs/verify_python.py
node contract/jcs/verify_node.mjs
test -z "$(gofmt -l contract/jcs/go/*.go)"
(
  cd contract/jcs/go
  go test ./...
)

"$PYTHON" contract/validation/prepare_openapi.py
node contract/validation/lint_openapi_zero.mjs

echo "All Contract, semantic, compatibility, JCS, supply-chain and zero-warning OpenAPI gates passed."
