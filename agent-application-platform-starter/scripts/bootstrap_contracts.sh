#!/usr/bin/env sh
set -eu

ROOT="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
cd "$ROOT"

PYTHON="${PYTHON:-python3}"
VENV="${VENV:-.venv}"
PIP_INDEX_URL="${PIP_INDEX_URL:-https://pypi.org/simple}"
NPM_CONFIG_REGISTRY="${NPM_CONFIG_REGISTRY:-https://registry.npmjs.org/}"

"$PYTHON" -m venv "$VENV"
"$VENV/bin/python" -m pip install --upgrade pip
"$VENV/bin/python" -m pip install \
  --index-url "$PIP_INDEX_URL" \
  -r requirements-contracts.txt

npm ci --registry "$NPM_CONFIG_REGISTRY"

echo "Contract toolchain installed from public registries."
