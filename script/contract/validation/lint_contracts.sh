#!/usr/bin/env sh
set -eu

SCRIPT_ROOT="$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)"
cd "$SCRIPT_ROOT"
export AGENT_CONTRACT_ROOT="${AGENT_CONTRACT_ROOT:-$SCRIPT_ROOT/../contract}"
export AGENT_BLUEPRINT_ROOT="${AGENT_BLUEPRINT_ROOT:-$SCRIPT_ROOT/../blueprint}"
PYTHON="${PYTHON:-.venv/bin/python}"

"$PYTHON" contract/validation/validate_contracts.py
"$PYTHON" contract/validation/validate_semantics.py
"$PYTHON" contract/validation/prepare_openapi.py
node contract/validation/lint_openapi_zero.mjs
