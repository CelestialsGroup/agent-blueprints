#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
from typing import Any


ROOT = Path(os.environ.get("AGENT_APPLICATION_ROOT", Path(__file__).resolve().parents[1])).resolve()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def load_env(path: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        key, separator, value = line.partition("=")
        if separator != "=" or not key or not value:
            raise AssertionError(f"Invalid toolchain entry: {raw_line}")
        result[key] = value
    return result


def source_manifest(paths: list[Path]) -> dict[str, Any]:
    files = [
        {"path": path.relative_to(ROOT).as_posix(), "sha256": sha256_file(path)}
        for path in sorted(set(paths))
    ]
    encoded = json.dumps(files, ensure_ascii=True, separators=(",", ":"), sort_keys=True).encode()
    return {"files": files, "source_set_sha256": "sha256:" + hashlib.sha256(encoded).hexdigest()}


parser = argparse.ArgumentParser()
parser.add_argument("--test-log", type=Path, required=True)
parser.add_argument("--replay-log", type=Path, required=True)
parser.add_argument("--history", type=Path, required=True)
parser.add_argument("--test-command", required=True)
parser.add_argument("--replay-command", required=True)
parser.add_argument("--workflow-definition-digest", required=True)
parser.add_argument("--worker-build-id", required=True)
parser.add_argument("--output", type=Path, required=True)
args = parser.parse_args()

test_log = args.test_log.resolve()
replay_log = args.replay_log.resolve()
history = args.history.resolve()
if not test_log.is_file() or not replay_log.is_file() or not history.is_file():
    raise AssertionError("Temporal integration, Replay logs, and History are required")
summary = [line for line in test_log.read_text(encoding="utf-8").splitlines() if line][-1]
if not summary.startswith("ok  \tgithub.com/shell-echo/agent/test/temporal"):
    raise AssertionError(f"Unexpected Temporal integration result: {summary}")
replay_summary = [line for line in replay_log.read_text(encoding="utf-8").splitlines() if line][-1]
if not replay_summary.startswith("ok  \tgithub.com/shell-echo/agent/test/replay"):
    raise AssertionError(f"Unexpected Replay result: {replay_summary}")
json.loads(history.read_text(encoding="utf-8"))

toolchain = load_env(ROOT / "toolchain/toolchain.env")
dependency_lock_path = ROOT / "dependency-lock.json"
go_sum_prefixes = (
    f"go.temporal.io/sdk v{toolchain['TEMPORAL_SDK_VERSION']}",
    "go.temporal.io/api v",
)
go_sum_lines = sorted(
    line
    for line in (ROOT / "go.sum").read_text(encoding="utf-8").splitlines()
    if line.startswith(go_sum_prefixes)
)
if len(go_sum_lines) != 4:
    raise AssertionError("Temporal SDK/API module and go.mod checksums are required")

evidence: dict[str, Any] = {
    "schema_version": 1,
    "evidence_id": "agent-b03.1-temporal-orchestration-replay-foundation-integration",
    "scope": "Temporal stable start, lost-response reconciliation, Activity retry, PostgreSQL WorkflowRun confirmation, Worker restart, Continue-as-New identity, and sanitized History",
    "result": "passed",
    "command": args.test_command,
    "exit_code": 0,
    "test_log": {
        "path": test_log.name,
        "sha256": sha256_file(test_log),
        "summary": summary,
        "race_enabled": True,
        "repeat_count": 3,
    },
    "replay": {
        "command": args.replay_command,
        "log": replay_log.name,
        "log_sha256": sha256_file(replay_log),
        "summary": replay_summary,
        "race_enabled": True,
        "repeat_count": 3,
        "fixture": "test/replay/testdata/work-order-completed-v1.json",
        "fixture_sha256": sha256_file(
            ROOT / "test/replay/testdata/work-order-completed-v1.json"
        ),
    },
    "history": {
        "path": history.name,
        "sha256": sha256_file(history),
        "sanitized_test_execution": True,
    },
    "workflow": {
        "type": "agent.work-order.v1",
        "definition_digest": args.workflow_definition_digest,
        "worker_deployment": "agent-worker-b031",
        "worker_build_id": args.worker_build_id,
        "versioning_behavior": "pinned",
    },
    "environment": {
        "go_version": toolchain["GO_VERSION"],
        "go_toolchain_image": toolchain["GO_TOOLCHAIN_IMAGE"],
        "postgres_version": toolchain["POSTGRES_VERSION"],
        "postgres_test_image": toolchain["POSTGRES_TEST_IMAGE"],
        "temporal_sdk_version": toolchain["TEMPORAL_SDK_VERSION"],
        "temporal_server_version": toolchain["TEMPORAL_SERVER_VERSION"],
        "temporal_server_test_image": toolchain["TEMPORAL_SERVER_TEST_IMAGE"],
        "database_storage": "container tmpfs",
        "network": "isolated disposable Docker network",
    },
    "go_sum": go_sum_lines,
    "dependency_lock": {
        "path": "dependency-lock.json",
        "sha256": sha256_file(dependency_lock_path),
        "value": json.loads(dependency_lock_path.read_text(encoding="utf-8")),
    },
    "sources": {
        "orchestration": source_manifest(
            list((ROOT / "internal/domain/orchestration").glob("*.go"))
            + list((ROOT / "internal/orchestration/temporaladapter").glob("*.go"))
            + [ROOT / "cmd/agent-worker/main.go"]
        ),
        "persistence": source_manifest(
            [ROOT / "db/migration/00004_temporal_orchestration_replay_foundation.sql"]
            + [ROOT / "db/query/workflow_runs.sql"]
            + [ROOT / "internal/persistence/workflow_runs.go"]
            + list((ROOT / "internal/generated/agentdb").glob("*.go"))
        ),
        "integration": source_manifest(
            list((ROOT / "test/temporal").glob("*.go"))
            + list((ROOT / "test/replay").rglob("*.go"))
            + list((ROOT / "test/replay/testdata").glob("*.json"))
            + [
                ROOT / "script/test_temporal_integration.sh",
                ROOT / "script/generate_temporal_integration_evidence.py",
            ]
        ),
        "supply_chain": source_manifest(
            [
                ROOT / "dependency-lock.json",
                ROOT / "go.mod",
                ROOT / "go.sum",
                ROOT / "toolchain/third-party.json",
                ROOT / "toolchain/toolchain.env",
                ROOT / "script/check_implementation_supply_chain.py",
            ]
        ),
    },
    "claims_not_made": [
        "production WorkOrder start-intent authority or Start Outbox atomicity",
        "externally visible WorkOrder state transitions or Canonical Platform Events",
        "RootBinding, Root Admission, RunManifest, Provider, Sandbox, or Native Runtime orchestration",
        "Temporal production topology, backup, capacity, SLO, security, or reliability approval",
        "Phase 0B completion, end-to-end execution, formal freeze, or production readiness",
    ],
}
canonical = json.dumps(evidence, ensure_ascii=True, separators=(",", ":"), sort_keys=True).encode()
evidence["evidence_digest"] = {
    "profile": "sha256-canonical-json-excluding-evidence_digest",
    "value": "sha256:" + hashlib.sha256(canonical).hexdigest(),
}

args.output.parent.mkdir(parents=True, exist_ok=True)
args.output.write_text(json.dumps(evidence, ensure_ascii=True, indent=2, sort_keys=True) + "\n", encoding="utf-8")
print(f"Temporal integration evidence written to {args.output}")
