#!/usr/bin/env bash
set -euo pipefail

ROOT="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
CONTRACT_ROOT="${AGENT_CONTRACT_ROOT:-$ROOT/../contract}"
source "$ROOT/toolchain/toolchain.env"

if [ "${1:-}" = "--check" ]; then
  CHECK_ONLY=1
elif [ "$#" -eq 0 ]; then
  CHECK_ONLY=0
else
  echo "usage: $0 [--check]" >&2
  exit 2
fi

CACHE_DIR="$ROOT/.cache/implementation"
mkdir -p "$CACHE_DIR"
WORK_DIR="$(mktemp -d "$CACHE_DIR/runtime-contract-projection.XXXXXX")"
trap 'rm -rf "$WORK_DIR"' EXIT

docker run --rm --entrypoint python \
  -v "$CONTRACT_ROOT:/contract:ro" \
  -v "$ROOT:/workspace:ro" \
  -v "$WORK_DIR:/out" \
  "$RUNTIME_PYTHON_CODEGEN_IMAGE" \
  /workspace/script/runtime_contract_projection.py prepare \
    --contract-root /contract \
    --output-root /out/contract

docker run --rm --entrypoint python \
  -v "$ROOT:/workspace:ro" \
  -v "$WORK_DIR:/out" \
  "$RUNTIME_PYTHON_CODEGEN_IMAGE" \
  /workspace/script/runtime_contract_projection.py python-codegen-inventory \
    --image-reference "$RUNTIME_PYTHON_CODEGEN_IMAGE" \
    --output /out/runtime-python-codegen-packages.json

docker run --rm \
  -v "$WORK_DIR/contract:/contract:ro" \
  -v "$WORK_DIR:/out" \
  "$RUNTIME_PYTHON_CODEGEN_IMAGE" \
  --input /contract/openapi/agent-runtime-provider-v1.yaml \
  --input-file-type openapi \
  --openapi-scopes paths \
  --allow-remote-refs \
  --output /out/runtime_api \
  --output-model-type typing.TypedDict \
  --target-python-version 3.14 \
  --strict-nullable \
  --use-standard-collections \
  --use-union-operator \
  --use-annotated \
  --field-constraints \
  --extra-fields forbid \
  --formatters builtin \
  --disable-timestamp

set -- "$WORK_DIR/contract/schemas/"*.schema.json

docker run --rm \
  -e GOCACHE=/cache/go-build \
  -e GOMODCACHE=/cache/go-mod \
  -e HOME=/tmp \
  -v "$CACHE_DIR:/cache" \
  -v "$ROOT:/workspace:ro" \
  -v "$WORK_DIR/contract:$WORK_DIR/contract:ro" \
  -v "$WORK_DIR:/out" \
  -w /workspace/toolchain/runtime-codegen \
  "$GO_TOOLCHAIN_IMAGE" \
  go run github.com/atombender/go-jsonschema \
    --package runtimeapi \
    --struct-name-from-title \
    --capitalization ID \
    --capitalization JWS \
    --tags json \
    --output /out/runtime.schemas.gen.go \
    "$@"

docker run --rm --entrypoint python \
  -v "$ROOT:/workspace:ro" \
  -v "$WORK_DIR:/out" \
  "$RUNTIME_PYTHON_CODEGEN_IMAGE" \
  /workspace/script/runtime_contract_projection.py finalize \
    --language go \
    --generated /out/runtime.schemas.gen.go \
    --manifest /out/contract/projection-manifest.json \
    --dependency-lock /workspace/dependency-lock.json \
    --output /out/runtime.schemas.final.go

docker run --rm --entrypoint python \
  -v "$ROOT:/workspace:ro" \
  -v "$WORK_DIR:/out" \
  "$RUNTIME_PYTHON_CODEGEN_IMAGE" \
  /workspace/script/runtime_contract_projection.py finalize \
    --language python \
    --generated /out/runtime_api \
    --manifest /out/contract/projection-manifest.json \
    --dependency-lock /workspace/dependency-lock.json \
    --output /out/runtime_api.final

GO_OUTPUT="$ROOT/internal/generated/runtimeapi/runtime.schemas.gen.go"
PYTHON_OUTPUT="$ROOT/runtime/native/src/agent_native_runtime/generated/runtimeapi"
MANIFEST_OUTPUT="$ROOT/internal/generated/runtimeapi/projection-manifest.json"
CODEGEN_INVENTORY_OUTPUT="$ROOT/toolchain/runtime-python-codegen-packages.json"

if [ "$CHECK_ONLY" -eq 1 ]; then
  diff -u "$GO_OUTPUT" "$WORK_DIR/runtime.schemas.final.go"
  diff -ru "$PYTHON_OUTPUT" "$WORK_DIR/runtime_api.final"
  diff -u "$MANIFEST_OUTPUT" "$WORK_DIR/contract/projection-manifest.json"
  diff -u "$CODEGEN_INVENTORY_OUTPUT" "$WORK_DIR/runtime-python-codegen-packages.json"
  echo "Runtime Contract projection regeneration check passed."
else
  mkdir -p "$(dirname "$GO_OUTPUT")" "$(dirname "$PYTHON_OUTPUT")"
  cp "$WORK_DIR/runtime.schemas.final.go" "$GO_OUTPUT"
  rm -rf "$PYTHON_OUTPUT"
  cp -R "$WORK_DIR/runtime_api.final" "$PYTHON_OUTPUT"
  cp "$WORK_DIR/contract/projection-manifest.json" "$MANIFEST_OUTPUT"
  cp "$WORK_DIR/runtime-python-codegen-packages.json" "$CODEGEN_INVENTORY_OUTPUT"
fi
