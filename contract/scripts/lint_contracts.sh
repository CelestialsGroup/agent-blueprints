#!/usr/bin/env sh
set -eu

ROOT="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
cd "$ROOT"
PYTHON="${PYTHON:-.venv/bin/python}"

"$PYTHON" scripts/validate_contracts.py
"$PYTHON" scripts/validate_semantics.py
"$PYTHON" scripts/prepare_openapi.py
node scripts/lint_openapi_zero.mjs
