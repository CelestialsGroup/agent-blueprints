#!/usr/bin/env sh
set -eu

ROOT="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
cd "$ROOT"

python3 scripts/validate_contracts.py

if [ ! -x node_modules/.bin/redocly ]; then
  echo "Missing pinned Redocly CLI. Run: npm ci" >&2
  exit 1
fi

node_modules/.bin/redocly lint contracts/openapi/agent-access-v1.yaml
node_modules/.bin/redocly lint contracts/openapi/plugin-invocation-v1.yaml

node_modules/.bin/redocly lint contracts/openapi/delivery-webhook-v1.yaml

node_modules/.bin/redocly lint contracts/openapi/sandbox-provider-v1.yaml
