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
B03_EVIDENCE_DIR="$ROOT/build/evidence/b03.1"
P0_EVIDENCE_DIR="$ROOT/build/evidence/b03.2-p0"
A0_EVIDENCE_DIR="$ROOT/build/evidence/b03.2a0"
A1_0_EVIDENCE_DIR="$ROOT/build/evidence/b03.2a1.0"
A1_1_0_EVIDENCE_DIR="$ROOT/build/evidence/b03.2a1.1.0"
A1_1_1_EVIDENCE_DIR="$ROOT/build/evidence/b03.2a1.1.1"
A1_1_2_EVIDENCE_DIR="$ROOT/build/evidence/b03.2a1.1.2"
CACHE_DIR="$ROOT/.cache/implementation"
SQLC_CHECK_DIR="$CACHE_DIR/sqlc-check"
P0_RUN_DIR="$CACHE_DIR/b03.2-p0-validation"
NATIVE_WHEEL="agent_native_runtime-0.1.0-py3-none-any.whl"
APPLICATION_BASE_REVISION="$(git -C "$ROOT" rev-parse HEAD)"

rm -rf "$P0_RUN_DIR"
mkdir -p "$P0_RUN_DIR"

docker run --rm \
  -e AGENT_BLUEPRINT_ROOT=/blueprint \
  -e AGENT_CONTRACT_ROOT=/contract \
  -v "$BLUEPRINT_ROOT:/blueprint:ro" \
  -v "$CONTRACT_ROOT:/contract:ro" \
  -v "$ROOT:/workspace:ro" \
  -w /workspace \
  "$PYTHON_TOOLCHAIN_IMAGE" \
  python script/verify_dependency_lock.py

"$ROOT/script/generate_runtime_contract.sh" --check 2>&1 \
  | tee "$P0_RUN_DIR/regeneration.log"

mkdir -p \
  "$CACHE_DIR/go-build" \
  "$CACHE_DIR/go-mod" \
  "$CACHE_DIR/uv" \
  "$EVIDENCE_DIR/artifacts/native" \
  "$EVIDENCE_DIR/evidence" \
  "$EVIDENCE_DIR/rebuild/native" \
  "$B03_EVIDENCE_DIR"

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
  -e AGENT_CONTRACT_ROOT=/contract \
  -e GOCACHE=/cache/go-build \
  -e GOMODCACHE=/cache/go-mod \
  -e HOME=/tmp \
  -v "$CACHE_DIR:/cache" \
  -v "$CONTRACT_ROOT:/contract:ro" \
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
  ' 2>&1 | tee "$P0_RUN_DIR/go-validation.log"

"$ROOT/script/test_postgres_integration.sh" "$CACHE_DIR" "$B03_EVIDENCE_DIR"

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
    go build -trimpath -buildvcs=false -ldflags="-buildid=" -o /out/artifacts/agent-worker ./cmd/agent-worker
    go build -trimpath -buildvcs=false -ldflags="-buildid=" -o /out/rebuild/agent-worker ./cmd/agent-worker
    cmp /out/artifacts/agent-worker /out/rebuild/agent-worker
  '

"$ROOT/script/test_temporal_integration.sh" "$CACHE_DIR" "$B03_EVIDENCE_DIR"

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
  -e MYPY_CACHE_DIR=/tmp/mypy-cache \
  -e PYTHONDONTWRITEBYTECODE=1 \
  -e RUFF_CACHE_DIR=/tmp/ruff-cache \
  -e UV_CACHE_DIR=/cache/uv \
  -e UV_LINK_MODE=copy \
  -e UV_PROJECT_ENVIRONMENT=/tmp/native-runtime-venv \
  -v "$CACHE_DIR:/cache" \
  -v "$CONTRACT_ROOT:/contract:ro" \
  -v "$ROOT:/workspace:ro" \
  -w /workspace/runtime/native \
  "$UV_TOOLCHAIN_TAG" \
  run --frozen --project /workspace/runtime/native \
    sh -euc '
      test "$(ruff --version)" = "ruff 0.16.0"
      ruff --version
      ruff format --check src test
      echo "Ruff format check passed."
      ruff check src test
      echo "Ruff lint check passed."
      case "$(mypy --version)" in
        "mypy 2.3.0"*) ;;
        *) echo "unexpected mypy version: $(mypy --version)" >&2; exit 1 ;;
      esac
      mypy --version
      mypy --config-file pyproject.toml
      echo "mypy strict check passed."
      python -m unittest discover -s test -v
    ' \
    2>&1 | tee "$P0_RUN_DIR/python-validation.log"

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
    python -c '\''
import os
import zipfile

wheel = "/out/artifacts/native/" + os.environ["NATIVE_WHEEL"]
with zipfile.ZipFile(wheel) as archive:
    names = set(archive.namelist())
for required in (
    "agent_native_runtime/migrations/0001_runtime_durable_kernel.up.sql",
    "agent_native_runtime/migrations/0001_runtime_durable_kernel.down.sql",
    "agent_native_runtime/migrations/0002_secure_admission_core.up.sql",
    "agent_native_runtime/migrations/0002_secure_admission_core.down.sql",
):
    assert required in names, required
'\''
    python -m pip install --disable-pip-version-check --no-deps --root-user-action ignore \
      --target /tmp/native-runtime \
      "/out/artifacts/native/$NATIVE_WHEEL" >/dev/null
    PYTHONPATH=/tmp/native-runtime python -c '\''
from agent_native_runtime import BUILD_IDENTITY

assert BUILD_IDENTITY.target_profile == "runtime-core-v1"
'\''
  '

docker run --rm \
  --entrypoint sh \
  -e AGENT_CONTRACT_ROOT=/contract \
  -e AGENT_NATIVE_RUNTIME_INSTALLED_BIN=/tmp/installed/bin \
  -e AGENT_TEST_APPLICATION_ROOT=/workspace \
  -e NATIVE_WHEEL="$NATIVE_WHEEL" \
  -e PYTHONDONTWRITEBYTECODE=1 \
  -e UV_CACHE_DIR=/cache/uv \
  -e UV_LINK_MODE=copy \
  -e UV_PROJECT_ENVIRONMENT=/tmp/installed \
  -v "$CACHE_DIR:/cache" \
  -v "$CONTRACT_ROOT:/contract:ro" \
  -v "$ROOT:/workspace:ro" \
  -v "$EVIDENCE_DIR:/out:ro" \
  -w /workspace/runtime/native \
  "$UV_TOOLCHAIN_TAG" \
  -euc '
    uv sync --frozen --project /workspace/runtime/native --no-install-project
    uv pip install --python /tmp/installed/bin/python --no-deps \
      "/out/artifacts/native/$NATIVE_WHEEL"
    /tmp/installed/bin/python test/test_process_foundation.py -v
  ' 2>&1 | tee "$P0_RUN_DIR/process-foundation-validation.log"

docker run --rm \
  --entrypoint sh \
  -e AGENT_CONTRACT_ROOT=/contract \
  -e AGENT_NATIVE_RUNTIME_INSTALLED_BIN=/tmp/installed/bin \
  -e AGENT_TEST_APPLICATION_ROOT=/workspace \
  -e NATIVE_WHEEL="$NATIVE_WHEEL" \
  -e PYTHONDONTWRITEBYTECODE=1 \
  -e UV_CACHE_DIR=/cache/uv \
  -e UV_LINK_MODE=copy \
  -e UV_PROJECT_ENVIRONMENT=/tmp/installed \
  -v "$CACHE_DIR:/cache" \
  -v "$CONTRACT_ROOT:/contract:ro" \
  -v "$ROOT:/workspace:ro" \
  -v "$EVIDENCE_DIR:/out:ro" \
  -w /workspace/runtime/native \
  "$UV_TOOLCHAIN_TAG" \
  -euc '
    uv sync --frozen --project /workspace/runtime/native --no-install-project
    uv pip install --python /tmp/installed/bin/python --no-deps \
      "/out/artifacts/native/$NATIVE_WHEEL"
    /tmp/installed/bin/python test/test_start_http_boundary.py -v
  ' 2>&1 | tee "$P0_RUN_DIR/start-http-boundary-validation.log"

docker run --rm \
  -e AGENT_BLUEPRINT_ROOT=/blueprint \
  -e AGENT_CONTRACT_ROOT=/contract \
  -v "$BLUEPRINT_ROOT:/blueprint:ro" \
  -v "$CONTRACT_ROOT:/contract:ro" \
  -v "$ROOT:/workspace:ro" \
  -w /workspace \
  "$PYTHON_TOOLCHAIN_IMAGE" \
  python script/check_implementation_supply_chain.py \
  2>&1 | tee "$P0_RUN_DIR/supply-chain.log"

mkdir -p "$P0_EVIDENCE_DIR"
docker run --rm \
  -v "$ROOT:/workspace:ro" \
  -v "$P0_RUN_DIR:/validation:ro" \
  -v "$P0_EVIDENCE_DIR:/out" \
  -w /workspace \
  "$PYTHON_TOOLCHAIN_IMAGE" \
  python script/generate_runtime_contract_evidence.py \
    --application-base-revision "$APPLICATION_BASE_REVISION" \
    --validation-command "make validate-implementation" \
    --regeneration-log /validation/regeneration.log \
    --go-validation-log /validation/go-validation.log \
    --python-validation-log /validation/python-validation.log \
    --supply-chain-log /validation/supply-chain.log \
    --output /out/runtime-contract-projection.json

mkdir -p "$A0_EVIDENCE_DIR"
docker run --rm \
  -e AGENT_CONTRACT_ROOT=/contract \
  -v "$CONTRACT_ROOT:/contract:ro" \
  -v "$ROOT:/workspace:ro" \
  -v "$P0_RUN_DIR:/validation:ro" \
  -v "$A0_EVIDENCE_DIR:/out" \
  -w /workspace \
  "$PYTHON_TOOLCHAIN_IMAGE" \
  python script/generate_native_runtime_kernel_evidence.py \
    --application-base-revision "$APPLICATION_BASE_REVISION" \
    --validation-command "make validate-implementation" \
    --python-validation-log /validation/python-validation.log \
    --output /out/native-runtime-durable-kernel.json

mkdir -p "$A1_0_EVIDENCE_DIR"
docker run --rm \
  -e AGENT_CONTRACT_ROOT=/contract \
  -v "$CONTRACT_ROOT:/contract:ro" \
  -v "$ROOT:/workspace:ro" \
  -v "$P0_RUN_DIR:/validation:ro" \
  -v "$A1_0_EVIDENCE_DIR:/out" \
  -w /workspace \
  "$PYTHON_TOOLCHAIN_IMAGE" \
  python script/generate_secure_admission_evidence.py \
    --application-base-revision "$APPLICATION_BASE_REVISION" \
    --validation-command "make validate-implementation" \
    --python-validation-log /validation/python-validation.log \
    --supply-chain-log /validation/supply-chain.log \
    --output /out/secure-admission-core.json

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
    --agent-worker-artifact /out/artifacts/agent-worker \
    --dependency-lock /workspace/dependency-lock.json \
    --native-runtime-artifact "/out/artifacts/native/$NATIVE_WHEEL" \
    --traceability-map /workspace/test/traceability/phase0-implementation-evidence.json \
    --traceability-report /out/evidence/phase0-implementation-traceability.json \
    --output-dir /out/evidence

mkdir -p "$A1_1_0_EVIDENCE_DIR"
docker run --rm \
  -e AGENT_CONTRACT_ROOT=/contract \
  -v "$CONTRACT_ROOT:/contract:ro" \
  -v "$ROOT:/workspace:ro" \
  -v "$P0_RUN_DIR:/validation:ro" \
  -v "$A1_1_0_EVIDENCE_DIR:/out" \
  -w /workspace \
  "$PYTHON_TOOLCHAIN_IMAGE" \
  python script/generate_pre_transport_safety_evidence.py \
    --application-base-revision "$APPLICATION_BASE_REVISION" \
    --validation-command "make validate-implementation" \
    --python-validation-log /validation/python-validation.log \
    --supply-chain-log /validation/supply-chain.log \
    --native-runtime-artifact "/workspace/build/evidence/b01/artifacts/native/$NATIVE_WHEEL" \
    --native-runtime-rebuild "/workspace/build/evidence/b01/rebuild/native/$NATIVE_WHEEL" \
    --implementation-evidence-dir /workspace/build/evidence/b01/evidence \
    --output /out/pre-transport-safety-preconditions.json

mkdir -p "$A1_1_1_EVIDENCE_DIR"
docker run --rm \
  -e AGENT_CONTRACT_ROOT=/contract \
  -v "$CONTRACT_ROOT:/contract:ro" \
  -v "$ROOT:/workspace:ro" \
  -v "$P0_RUN_DIR:/validation:ro" \
  -v "$A1_1_1_EVIDENCE_DIR:/out" \
  -w /workspace \
  "$PYTHON_TOOLCHAIN_IMAGE" \
  python script/generate_mtls_process_foundation_evidence.py \
    --application-base-revision "$APPLICATION_BASE_REVISION" \
    --validation-command "make validate-implementation" \
    --python-validation-log /validation/python-validation.log \
    --installed-process-log /validation/process-foundation-validation.log \
    --supply-chain-log /validation/supply-chain.log \
    --native-runtime-artifact "/workspace/build/evidence/b01/artifacts/native/$NATIVE_WHEEL" \
    --native-runtime-rebuild "/workspace/build/evidence/b01/rebuild/native/$NATIVE_WHEEL" \
    --implementation-evidence-dir /workspace/build/evidence/b01/evidence \
    --output /out/mtls-process-foundation.json

mkdir -p "$A1_1_2_EVIDENCE_DIR"
docker run --rm \
  -e AGENT_CONTRACT_ROOT=/contract \
  -v "$CONTRACT_ROOT:/contract:ro" \
  -v "$ROOT:/workspace:ro" \
  -v "$P0_RUN_DIR:/validation:ro" \
  -v "$A1_1_2_EVIDENCE_DIR:/out" \
  -w /workspace \
  "$PYTHON_TOOLCHAIN_IMAGE" \
  python script/generate_start_http_boundary_evidence.py \
    --application-base-revision "$APPLICATION_BASE_REVISION" \
    --validation-command "make validate-implementation" \
    --python-validation-log /validation/python-validation.log \
    --installed-process-log /validation/process-foundation-validation.log \
    --installed-start-log /validation/start-http-boundary-validation.log \
    --supply-chain-log /validation/supply-chain.log \
    --native-runtime-artifact "/workspace/build/evidence/b01/artifacts/native/$NATIVE_WHEEL" \
    --native-runtime-rebuild "/workspace/build/evidence/b01/rebuild/native/$NATIVE_WHEEL" \
    --implementation-evidence-dir /workspace/build/evidence/b01/evidence \
    --output /out/start-http-boundary.json

echo "B03.2a1.1.2 Start HTTP boundary, B03.2a1.1.1 mTLS process foundation, B03.2a1.1.0 pre-transport safety, B03.2a1.0 secure admission, B03.2a0 durable kernel, B03.2-P0 projection, and bounded B03.1 validation passed; reproducible evidence preserved."
