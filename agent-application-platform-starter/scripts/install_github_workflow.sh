#!/usr/bin/env sh
set -eu

PACKAGE_ROOT="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
GIT_ROOT="$(git -C "$PACKAGE_ROOT" rev-parse --show-toplevel)"
RELATIVE_ROOT="$(python3 - "$GIT_ROOT" "$PACKAGE_ROOT" <<'PY'
import os
import sys

print(os.path.relpath(sys.argv[2], sys.argv[1]))
PY
)"

mkdir -p "$GIT_ROOT/.github/workflows"
cp "$PACKAGE_ROOT/.github/workflows/contracts.yml" "$GIT_ROOT/.github/workflows/contracts.yml"

cat <<EOF
Installed the contracts workflow at the Git repository root.
Set the GitHub repository variable AGENT_PLATFORM_CONTRACT_ROOT to:
  $RELATIVE_ROOT
Use '.' when the contract package is the repository root.
Set protected AGENT_PLATFORM_FROZEN_CONTRACT_REF to the immutable frozen tag/commit.
Before the first frozen baseline only, explicitly set protected
AGENT_PLATFORM_ALLOW_NO_FROZEN_BASELINE=true.
Commit .github/workflows/contracts.yml at the Git root; copying it locally is not activation.
EOF
