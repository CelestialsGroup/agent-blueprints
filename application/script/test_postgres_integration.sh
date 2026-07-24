#!/usr/bin/env bash
set -euo pipefail

ROOT="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
source "$ROOT/toolchain/toolchain.env"

CACHE_DIR="${1:-$ROOT/.cache/implementation}"
EVIDENCE_DIR="${2:-$ROOT/build/evidence/b02.2}"
CONTAINER_NAME="agent-b022-postgres-$$"
NETWORK_NAME="agent-b022-$$"
POSTGRES_PASSWORD="b021-integration-admin"
TEST_COMMAND="go test -race -tags=integration -count=3 ./test/integration/..."

mkdir -p "$CACHE_DIR" "$EVIDENCE_DIR"
CACHE_DIR="$(CDPATH= cd -- "$CACHE_DIR" && pwd)"
EVIDENCE_DIR="$(CDPATH= cd -- "$EVIDENCE_DIR" && pwd)"
TEST_LOG="$EVIDENCE_DIR/postgres-integration.log"
EVIDENCE_MANIFEST="$EVIDENCE_DIR/postgres-integration-evidence.json"
rm -f "$TEST_LOG" "$EVIDENCE_MANIFEST"

cleanup() {
  docker rm --force "$CONTAINER_NAME" >/dev/null 2>&1 || true
  docker network rm "$NETWORK_NAME" >/dev/null 2>&1 || true
}
trap cleanup EXIT INT TERM

docker network create "$NETWORK_NAME" >/dev/null
docker run --detach --rm \
  --name "$CONTAINER_NAME" \
  --network "$NETWORK_NAME" \
  --network-alias postgres \
  --tmpfs /var/lib/postgresql:rw,noexec,nosuid,size=512m \
  -e POSTGRES_PASSWORD="$POSTGRES_PASSWORD" \
  -e POSTGRES_DB=postgres \
  "$POSTGRES_TEST_IMAGE" >/dev/null

attempt=1
until docker exec "$CONTAINER_NAME" pg_isready --username postgres --dbname postgres >/dev/null 2>&1; do
  if [ "$attempt" -ge 60 ]; then
    docker logs "$CONTAINER_NAME" >&2
    exit 1
  fi
  attempt=$((attempt + 1))
  sleep 0.5
done

set +e
docker run --rm \
  --network "$NETWORK_NAME" \
  -e AGENT_TEST_ADMIN_DSN="postgres://postgres:$POSTGRES_PASSWORD@postgres:5432/postgres?sslmode=disable" \
  -e AGENT_GOOSE=/cache/tools/goose \
  -e GOCACHE=/cache/go-build \
  -e GOMODCACHE=/cache/go-mod \
  -e HOME=/tmp \
  -v "$CACHE_DIR:/cache" \
  -v "$ROOT:/workspace:ro" \
  -w /workspace \
  "$GO_TOOLCHAIN_IMAGE" \
  sh -euc '
    test "$(go env GOVERSION)" = "go1.26.5"
    go test -race -tags=integration -count=3 ./test/integration/...
  ' 2>&1 | tee "$TEST_LOG"
test_status="${PIPESTATUS[0]}"
set -e
if [ "$test_status" -ne 0 ]; then
  exit "$test_status"
fi

docker run --rm \
  -e AGENT_APPLICATION_ROOT=/workspace \
  -v "$ROOT:/workspace:ro" \
  -v "$EVIDENCE_DIR:/evidence" \
  -w /workspace \
  "$PYTHON_TOOLCHAIN_IMAGE" \
  python script/generate_postgres_integration_evidence.py \
    --test-log /evidence/postgres-integration.log \
    --test-command "$TEST_COMMAND" \
    --output /evidence/postgres-integration-evidence.json

test -s "$EVIDENCE_MANIFEST"
