#!/usr/bin/env bash
set -euo pipefail

ROOT="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
source "$ROOT/toolchain/toolchain.env"

CACHE_DIR="${1:-$ROOT/.cache/implementation}"
EVIDENCE_DIR="${2:-$ROOT/build/evidence/b03.1}"
POSTGRES_CONTAINER="agent-b031-postgres-$$"
TEMPORAL_CONTAINER="agent-b031-temporal-$$"
NETWORK_NAME="agent-b031-$$"
POSTGRES_PASSWORD="b031-integration-admin"
APPLICATION_LOGIN="agent_app_b031"
APPLICATION_PASSWORD="b031-integration-application"
APPLICATION_DATABASE="agent_temporal_integration"
TEMPORAL_NAMESPACE="default"
TEMPORAL_TASK_QUEUE="agent-b031-work-orders"
WORKER_DEPLOYMENT="agent-worker-b031"
WORKFLOW_DEFINITION_DIGEST="sha256:$(sha256sum "$ROOT/internal/orchestration/temporaladapter/workflow.go" | awk '{print $1}')"
WORKER_BUILD_ID="b03.1-$(printf '%s' "$WORKFLOW_DEFINITION_DIGEST" | cut -c8-23)"
TEST_COMMAND="go test -race -tags=temporalintegration -count=3 ./test/temporal/..."
REPLAY_COMMAND="go test -race -count=3 ./test/replay/..."

mkdir -p "$CACHE_DIR" "$EVIDENCE_DIR"
CACHE_DIR="$(CDPATH= cd -- "$CACHE_DIR" && pwd)"
EVIDENCE_DIR="$(CDPATH= cd -- "$EVIDENCE_DIR" && pwd)"
TEST_LOG="$EVIDENCE_DIR/temporal-integration.log"
REPLAY_LOG="$EVIDENCE_DIR/replay.log"
HISTORY_OUTPUT="$EVIDENCE_DIR/work-order-completed-history.json"
rm -f "$TEST_LOG" "$REPLAY_LOG" "$HISTORY_OUTPUT"

docker run --rm \
	-e HOME=/tmp \
	-v "$CACHE_DIR:/cache" \
	-v "$ROOT:/workspace:ro" \
	-w /workspace \
	"$GO_TOOLCHAIN_IMAGE" \
	./script/prepare_go_tools.sh /cache/tools

cleanup() {
	docker rm --force "$TEMPORAL_CONTAINER" >/dev/null 2>&1 || true
	docker rm --force "$POSTGRES_CONTAINER" >/dev/null 2>&1 || true
	docker network rm "$NETWORK_NAME" >/dev/null 2>&1 || true
}
trap cleanup EXIT INT TERM

docker network create "$NETWORK_NAME" >/dev/null
docker run --detach --rm \
	--name "$POSTGRES_CONTAINER" \
	--network "$NETWORK_NAME" \
	--network-alias postgres \
	--tmpfs /var/lib/postgresql:rw,noexec,nosuid,size=1g \
	-e POSTGRES_PASSWORD="$POSTGRES_PASSWORD" \
	-e POSTGRES_DB=postgres \
	"$POSTGRES_TEST_IMAGE" >/dev/null

attempt=1
until docker exec "$POSTGRES_CONTAINER" pg_isready --username postgres --dbname postgres >/dev/null 2>&1; do
	if [ "$attempt" -ge 60 ]; then
		docker logs "$POSTGRES_CONTAINER" >&2
		exit 1
	fi
	attempt=$((attempt + 1))
	sleep 0.5
done

docker run --detach --rm \
	--name "$TEMPORAL_CONTAINER" \
	--network "$NETWORK_NAME" \
	--network-alias temporal \
	-e DB=postgres12_pgx \
	-e DB_PORT=5432 \
	-e POSTGRES_SEEDS=postgres \
	-e POSTGRES_USER=postgres \
	-e POSTGRES_PWD="$POSTGRES_PASSWORD" \
	-e DBNAME=temporal \
	-e VISIBILITY_DBNAME=temporal_visibility \
	"$TEMPORAL_SERVER_TEST_IMAGE" >/dev/null

attempt=1
until docker exec "$TEMPORAL_CONTAINER" temporal operator cluster health --address temporal:7233 >/dev/null 2>&1; do
	if [ "$attempt" -ge 120 ]; then
		docker logs "$TEMPORAL_CONTAINER" >&2
		exit 1
	fi
	attempt=$((attempt + 1))
	sleep 0.5
done

docker exec "$POSTGRES_CONTAINER" createdb \
	--username postgres \
	--owner postgres \
	"$APPLICATION_DATABASE"

docker run --rm \
	--network "$NETWORK_NAME" \
	-e GOOSE_DRIVER=postgres \
	-e GOOSE_DBSTRING="postgres://postgres:$POSTGRES_PASSWORD@postgres:5432/$APPLICATION_DATABASE?sslmode=disable" \
	-e GOOSE_MIGRATION_DIR=/workspace/db/migration \
	-v "$CACHE_DIR:/cache" \
	-v "$ROOT:/workspace:ro" \
	-w /workspace \
	"$GO_TOOLCHAIN_IMAGE" \
	/cache/tools/goose up

docker exec "$POSTGRES_CONTAINER" psql \
	--username postgres \
	--dbname "$APPLICATION_DATABASE" \
	--set ON_ERROR_STOP=1 \
	--command "CREATE ROLE $APPLICATION_LOGIN LOGIN NOSUPERUSER INHERIT NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS PASSWORD '$APPLICATION_PASSWORD'; GRANT agent_app TO $APPLICATION_LOGIN;"

set +e
docker run --rm \
	--network "$NETWORK_NAME" \
	-e AGENT_TEST_APPLICATION_DSN="postgres://$APPLICATION_LOGIN:$APPLICATION_PASSWORD@postgres:5432/$APPLICATION_DATABASE?sslmode=disable" \
	-e AGENT_TEST_TEMPORAL_ADDRESS=temporal:7233 \
	-e AGENT_TEST_TEMPORAL_NAMESPACE="$TEMPORAL_NAMESPACE" \
	-e AGENT_TEST_TEMPORAL_TASK_QUEUE="$TEMPORAL_TASK_QUEUE" \
	-e AGENT_TEST_TEMPORAL_ENGINE_VERSION="$TEMPORAL_SERVER_VERSION" \
	-e AGENT_TEST_WORKER_DEPLOYMENT="$WORKER_DEPLOYMENT" \
	-e AGENT_TEST_WORKER_BUILD_ID="$WORKER_BUILD_ID" \
	-e AGENT_TEST_WORKFLOW_DEFINITION_DIGEST="$WORKFLOW_DEFINITION_DIGEST" \
	-e AGENT_TEST_HISTORY_OUTPUT=/evidence/work-order-completed-history.json \
	-e GOCACHE=/cache/go-build \
	-e GOMODCACHE=/cache/go-mod \
	-e HOME=/tmp \
	-v "$CACHE_DIR:/cache" \
	-v "$ROOT:/workspace:ro" \
	-v "$EVIDENCE_DIR:/evidence" \
	-w /workspace \
	"$GO_TOOLCHAIN_IMAGE" \
	sh -euc "$TEST_COMMAND" 2>&1 | tee "$TEST_LOG"
test_status="${PIPESTATUS[0]}"
set -e
if [ "$test_status" -ne 0 ]; then
	exit "$test_status"
fi

test -s "$HISTORY_OUTPUT"

set +e
docker run --rm \
	-e GOCACHE=/cache/go-build \
	-e GOMODCACHE=/cache/go-mod \
	-e HOME=/tmp \
	-v "$CACHE_DIR:/cache" \
	-v "$ROOT:/workspace:ro" \
	-w /workspace \
	"$GO_TOOLCHAIN_IMAGE" \
	sh -euc "$REPLAY_COMMAND" 2>&1 | tee "$REPLAY_LOG"
replay_status="${PIPESTATUS[0]}"
set -e
if [ "$replay_status" -ne 0 ]; then
	exit "$replay_status"
fi

docker run --rm \
	-e AGENT_APPLICATION_ROOT=/workspace \
	-v "$ROOT:/workspace:ro" \
	-v "$EVIDENCE_DIR:/evidence" \
	-w /workspace \
	"$PYTHON_TOOLCHAIN_IMAGE" \
	python script/generate_temporal_integration_evidence.py \
		--test-log /evidence/temporal-integration.log \
		--replay-log /evidence/replay.log \
		--history /evidence/work-order-completed-history.json \
		--test-command "$TEST_COMMAND" \
		--replay-command "$REPLAY_COMMAND" \
		--workflow-definition-digest "$WORKFLOW_DEFINITION_DIGEST" \
		--worker-build-id "$WORKER_BUILD_ID" \
		--output /evidence/temporal-integration-evidence.json

test -s "$EVIDENCE_DIR/temporal-integration-evidence.json"
