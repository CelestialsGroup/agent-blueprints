#!/usr/bin/env sh
set -eu

ROOT="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
cd "$ROOT"

PYTHON="${PYTHON:-python3}"
VENV="${VENV:-.venv}"
PIP_INDEX_URL="${PIP_INDEX_URL:-https://pypi.org/simple}"
NPM_CONFIG_REGISTRY="${NPM_CONFIG_REGISTRY:-https://registry.npmjs.org/}"
# Ignore ambient npm cache settings that may point at an unavailable home.
# Use CONTRACT_NPM_CACHE for an explicit shared cache override.
NPM_CONFIG_CACHE="${CONTRACT_NPM_CACHE:-$VENV/npm-cache}"
export NPM_CONFIG_CACHE

command -v "$PYTHON" >/dev/null 2>&1 || {
  echo "Python executable not found: $PYTHON" >&2
  exit 2
}

"$PYTHON" - <<'PY'
import sys
if not ((3, 11) <= sys.version_info[:2] <= (3, 13)):
    raise SystemExit(
        f"Python 3.11-3.13 is required; found {sys.version.split()[0]}. "
        "Set PYTHON to a supported interpreter."
    )
PY

if [ ! -x "$VENV/bin/python" ]; then
  "$PYTHON" -m venv "$VENV"
fi
"$VENV/bin/python" -m pip install \
  --index-url "$PIP_INDEX_URL" \
  --require-hashes \
  -r requirements-contracts-v0.8.3.txt

npm ci --registry "$NPM_CONFIG_REGISTRY"

echo "Contract toolchain installed from public registries with locked integrity metadata."
