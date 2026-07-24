#!/usr/bin/env bash
set -euo pipefail

ROOT="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
BLUEPRINT_ROOT="${AGENT_BLUEPRINT_ROOT:-$ROOT/../blueprint}"
CONTRACT_ROOT="${AGENT_CONTRACT_ROOT:-$ROOT/../contract}"
source "$ROOT/toolchain/toolchain.env"

test -f "$BLUEPRINT_ROOT/START_HERE.md"
test -f "$CONTRACT_ROOT/conformance/runtime/v1/suite.json"
test -f "$CONTRACT_ROOT/schemas/build-provenance.schema.json"

UV_TOOLCHAIN_TAG="agent-uv-toolchain:${UV_VERSION}-python${PYTHON_VERSION}"
EVIDENCE_DIR="$ROOT/build/evidence/b01"
B02_EVIDENCE_DIR="$ROOT/build/evidence/b02.2"
CACHE_DIR="$ROOT/.cache/implementation"
SQLC_CHECK_DIR="$CACHE_DIR/sqlc-check"
NATIVE_WHEEL="agent_native_runtime-0.1.0-py3-none-any.whl"

docker run --rm \
  -e AGENT_BLUEPRINT_ROOT=/blueprint \
  -e AGENT_CONTRACT_ROOT=/contract \
  -v "$BLUEPRINT_ROOT:/blueprint:ro" \
  -v "$CONTRACT_ROOT:/contract:ro" \
  -v "$ROOT:/workspace:ro" \
  -w /workspace \
  "$PYTHON_TOOLCHAIN_IMAGE" \
  python script/verify_dependency_lock.py

mkdir -p \
  "$CACHE_DIR/go-build" \
  "$CACHE_DIR/go-mod" \
  "$CACHE_DIR/uv" \
  "$EVIDENCE_DIR/artifacts/native" \
  "$EVIDENCE_DIR/evidence" \
  "$EVIDENCE_DIR/rebuild/native" \
  "$B02_EVIDENCE_DIR"

docker run --rm \
  -e HOME=/tmp \
  -v "$CACHE_DIR:/cache" \
  -v "$ROOT:/workspace:ro" \
  -w /workspace \
  "$GO_TOOLCHAIN_IMAGE" \
  ./script/prepare_go_tools.sh /cache/tools

docker run --rm \
  -v "$ROOT:/src:ro" \
  -w /src \
  "$SQLC_IMAGE" \
  vet

rm -rf "$SQLC_CHECK_DIR"
mkdir -p "$SQLC_CHECK_DIR/internal/generated"
cp "$ROOT/sqlc.yaml" "$SQLC_CHECK_DIR/sqlc.yaml"
cp -R "$ROOT/db" "$SQLC_CHECK_DIR/db"
docker run --rm \
  -v "$SQLC_CHECK_DIR:/src" \
  -w /src \
  "$SQLC_IMAGE" \
  generate
diff -ru \
  "$ROOT/internal/generated/agentdb" \
  "$SQLC_CHECK_DIR/internal/generated/agentdb"

docker build --quiet \
  --file "$ROOT/toolchain/uv-toolchain.Dockerfile" \
  --tag "$UV_TOOLCHAIN_TAG" \
  "$ROOT" >/dev/null

docker run --rm \
  -e GOCACHE=/cache/go-build \
  -e GOMODCACHE=/cache/go-mod \
  -e HOME=/tmp \
  -v "$CACHE_DIR:/cache" \
  -v "$ROOT:/workspace:ro" \
  -w /workspace \
  "$GO_TOOLCHAIN_IMAGE" \
  sh -euc '
    test "$(go env GOVERSION)" = "go1.26.5"
    attempt=1
    until go mod download; do
      if [ "$attempt" -ge 3 ]; then
        exit 1
      fi
      attempt=$((attempt + 1))
    done
    unformatted="$(find . \( -path ./build -o -path ./.cache \) -prune -o -name "*.go" -type f -print0 | xargs -0 gofmt -l)"
    if [ -n "$unformatted" ]; then
      echo "gofmt required for:" >&2
      echo "$unformatted" >&2
      exit 1
    fi
    go vet ./...
    /cache/tools/staticcheck ./...
    go test ./...
    go test -race ./...
  '

"$ROOT/script/test_postgres_integration.sh" "$CACHE_DIR" "$B02_EVIDENCE_DIR"

docker run --rm \
  -e GOCACHE=/cache/go-build \
  -e GOMODCACHE=/cache/go-mod \
  -e GO_TARGET_ARCH="$GO_TARGET_ARCH" \
  -e GO_TARGET_OS="$GO_TARGET_OS" \
  -e HOME=/tmp \
  -v "$CACHE_DIR:/cache" \
  -v "$ROOT:/workspace:ro" \
  -v "$EVIDENCE_DIR:/out" \
  -w /workspace \
  "$GO_TOOLCHAIN_IMAGE" \
  sh -euc '
    test "$(go env GOOS)" = "$GO_TARGET_OS"
    test "$(go env GOARCH)" = "$GO_TARGET_ARCH"
    export CGO_ENABLED=0 GOOS="$GO_TARGET_OS" GOARCH="$GO_TARGET_ARCH"
    go build -trimpath -buildvcs=false -ldflags="-buildid=" -o /out/artifacts/agent-access ./cmd/agent-access
    go build -trimpath -buildvcs=false -ldflags="-buildid=" -o /out/rebuild/agent-access ./cmd/agent-access
    cmp /out/artifacts/agent-access /out/rebuild/agent-access
  '

docker run --rm \
  -v "$EVIDENCE_DIR:/out:ro" \
  "$PYTHON_TOOLCHAIN_IMAGE" \
  sh -euc '
    AGENT_ACCESS_ADDRESS=127.0.0.1:18080 /out/artifacts/agent-access &
    server_pid=$!
    trap '\''kill -TERM "$server_pid" 2>/dev/null || true'\'' EXIT
    python -c '\''
import json
import time
import urllib.request

for attempt in range(50):
    try:
        with urllib.request.urlopen("http://127.0.0.1:18080/health/ready", timeout=1) as response:
            assert response.status == 200
            assert json.load(response) == {"status": "ok"}
            break
    except OSError:
        if attempt == 49:
            raise
        time.sleep(0.1)
'\''
    kill -TERM "$server_pid"
    wait "$server_pid"
    trap - EXIT
  '

docker run --rm \
  -e AGENT_CONTRACT_ROOT=/contract \
  -e PYTHONDONTWRITEBYTECODE=1 \
  -e PYTHONPATH=/workspace/runtime/native/src \
  -v "$CONTRACT_ROOT:/contract:ro" \
  -v "$ROOT:/workspace:ro" \
  -w /workspace \
  "$PYTHON_TOOLCHAIN_IMAGE" \
  sh -c 'test "$(python -c '\''import platform; print(platform.python_version())'\'')" = "3.14.6" && python -m unittest discover -s runtime/native/test'

docker run --rm \
  -v "$ROOT:/workspace:ro" \
  -w /workspace \
  "$UV_TOOLCHAIN_TAG" \
  lock --check --project /workspace/runtime/native

docker run --rm \
  -e UV_CACHE_DIR=/cache/uv \
  -e SOURCE_DATE_EPOCH=946684800 \
  -v "$CACHE_DIR:/cache" \
  -v "$ROOT:/workspace:ro" \
  -v "$EVIDENCE_DIR:/out" \
  -w /workspace \
  "$UV_TOOLCHAIN_TAG" \
  build --wheel --clear --no-create-gitignore --no-progress \
    --build-constraints /workspace/runtime/native/build-constraints.txt \
    --require-hashes \
    --out-dir /out/artifacts/native \
    /workspace/runtime/native

docker run --rm \
  -e UV_CACHE_DIR=/cache/uv \
  -e SOURCE_DATE_EPOCH=946684800 \
  -v "$CACHE_DIR:/cache" \
  -v "$ROOT:/workspace:ro" \
  -v "$EVIDENCE_DIR:/out" \
  -w /workspace \
  "$UV_TOOLCHAIN_TAG" \
  build --wheel --clear --no-create-gitignore --no-progress \
    --build-constraints /workspace/runtime/native/build-constraints.txt \
    --require-hashes \
    --out-dir /out/rebuild/native \
    /workspace/runtime/native

cmp \
  "$EVIDENCE_DIR/artifacts/native/$NATIVE_WHEEL" \
  "$EVIDENCE_DIR/rebuild/native/$NATIVE_WHEEL"

docker run --rm \
  -e NATIVE_WHEEL="$NATIVE_WHEEL" \
  -v "$EVIDENCE_DIR:/out:ro" \
  "$PYTHON_TOOLCHAIN_IMAGE" \
  sh -euc '
    python -m pip install --disable-pip-version-check --no-deps --root-user-action ignore \
      --target /tmp/native-runtime \
      "/out/artifacts/native/$NATIVE_WHEEL" >/dev/null
    PYTHONPATH=/tmp/native-runtime python -c '\''
from agent_native_runtime import BUILD_IDENTITY

assert BUILD_IDENTITY.target_profile == "runtime-core-v1"
'\''
  '

docker run --rm \
  -e AGENT_BLUEPRINT_ROOT=/blueprint \
  -e AGENT_CONTRACT_ROOT=/contract \
  -v "$BLUEPRINT_ROOT:/blueprint:ro" \
  -v "$CONTRACT_ROOT:/contract:ro" \
  -v "$ROOT:/workspace:ro" \
  -w /workspace \
  "$PYTHON_TOOLCHAIN_IMAGE" \
  python script/check_implementation_supply_chain.py

docker run --rm \
  -e AGENT_CONTRACT_ROOT=/contract \
  -v "$CONTRACT_ROOT:/contract:ro" \
  -v "$ROOT:/workspace:ro" \
  -v "$EVIDENCE_DIR:/out" \
  -w /workspace \
  "$PYTHON_TOOLCHAIN_IMAGE" \
  python script/verify_phase0_traceability.py \
    --evidence-map /workspace/test/traceability/phase0-implementation-evidence.json \
    --output /out/evidence/phase0-implementation-traceability.json

docker run --rm \
  -v "$ROOT:/workspace:ro" \
  -v "$EVIDENCE_DIR:/out" \
  -w /workspace \
  "$PYTHON_TOOLCHAIN_IMAGE" \
  python script/generate_implementation_evidence.py \
    --agent-access-artifact /out/artifacts/agent-access \
    --dependency-lock /workspace/dependency-lock.json \
    --native-runtime-artifact "/out/artifacts/native/$NATIVE_WHEEL" \
    --traceability-map /workspace/test/traceability/phase0-implementation-evidence.json \
    --traceability-report /out/evidence/phase0-implementation-traceability.json \
    --output-dir /out/evidence

echo "B02.2 implementation validation passed; B01 reproducible artifact evidence preserved."
