#!/usr/bin/env sh
set -eu

ROOT="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
cd "$ROOT"

PYTHON="${PYTHON:-python3}"
VENV="${VENV:-.venv}"
PIP_INDEX_URL="${PIP_INDEX_URL:-https://pypi.org/simple}"
COREPACK_HOME="${CONTRACT_COREPACK_HOME:-$VENV/corepack-cache}"
PNPM_STORE_DIR="${CONTRACT_PNPM_STORE:-$VENV/pnpm-store}"
export COREPACK_HOME

command -v "$PYTHON" >/dev/null 2>&1 || {
  echo "Python executable not found: $PYTHON" >&2
  exit 2
}
command -v corepack >/dev/null 2>&1 || {
  echo "Corepack is required to run the pinned pnpm package manager." >&2
  exit 2
}

"$PYTHON" - <<'PY'
import sys
if not ((3, 13) <= sys.version_info[:2] <= (3, 14)):
    raise SystemExit(
        f"Python 3.13-3.14 is required; found {sys.version.split()[0]}. "
        "Set PYTHON to a supported interpreter."
    )
PY

PYTHON_ABI="$("$PYTHON" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
if [ -x "$VENV/bin/python" ]; then
  VENV_ABI="$("$VENV/bin/python" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")' 2>/dev/null || true)"
  if [ "$VENV_ABI" != "$PYTHON_ABI" ]; then
    echo "Existing $VENV uses Python $VENV_ABI but requested interpreter uses $PYTHON_ABI; select a fresh VENV or remove the stale generated environment." >&2
    exit 2
  fi
fi

if [ ! -x "$VENV/bin/python" ]; then
  "$PYTHON" -m venv --copies "$VENV"
fi
"$VENV/bin/python" -m pip install \
  --index-url "$PIP_INDEX_URL" \
  --require-hashes \
  -r requirements-contracts.txt

corepack pnpm install --frozen-lockfile --store-dir "$PNPM_STORE_DIR"

echo "Contract toolchain installed from public registries with locked integrity metadata (primary baseline: Python 3.14.6, Node 24.18.0 LTS, pnpm 11.15.1, Go 1.26.5)."
