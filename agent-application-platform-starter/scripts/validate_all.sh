#!/usr/bin/env sh
set -eu

ROOT="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
cd "$ROOT"

PYTHON="${PYTHON:-.venv/bin/python}"
REDOCLY="${REDOCLY:-node_modules/.bin/redocly}"

"$PYTHON" scripts/check_supply_chain.py
"$PYTHON" scripts/offline_static_audit.py
"$PYTHON" scripts/validate_contracts.py
node scripts/verify_contract_manifest.mjs
"$PYTHON" scripts/jcs/verify_python.py
node scripts/jcs/verify_node.mjs
(
  cd scripts/jcs/go
  go test ./...
)

"$REDOCLY" lint contracts/openapi/agent-access-v1.yaml
"$REDOCLY" lint contracts/openapi/plugin-invocation-v1.yaml
"$REDOCLY" lint contracts/openapi/delivery-webhook-v1.yaml
"$REDOCLY" lint contracts/openapi/sandbox-provider-v1.yaml

echo "All contract, JCS, supply-chain and OpenAPI gates passed."
