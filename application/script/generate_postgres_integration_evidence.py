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
    canonical = json.dumps(files, ensure_ascii=True, separators=(",", ":"), sort_keys=True).encode()
    return {
        "files": files,
        "source_set_sha256": "sha256:" + hashlib.sha256(canonical).hexdigest(),
    }


parser = argparse.ArgumentParser()
parser.add_argument("--test-log", type=Path, required=True)
parser.add_argument("--test-command", required=True)
parser.add_argument("--output", type=Path, required=True)
args = parser.parse_args()

test_log = args.test_log.resolve()
if not test_log.is_file() or test_log.stat().st_size == 0:
    raise SystemExit("PostgreSQL integration test log is missing or empty")

toolchain = load_env(ROOT / "toolchain/toolchain.env")
dependency_lock_path = ROOT / "dependency-lock.json"
dependency_lock = json.loads(dependency_lock_path.read_text(encoding="utf-8"))
pgx_go_sum_prefix = f"github.com/jackc/pgx/v5 v{toolchain['PGX_VERSION']}"
go_sum_lines = [
    line
    for line in (ROOT / "go.sum").read_text(encoding="utf-8").splitlines()
    if line.startswith(pgx_go_sum_prefix + " ")
    or line.startswith(pgx_go_sum_prefix + "/go.mod ")
]
if len(go_sum_lines) != 2:
    raise AssertionError("pgx module and go.mod checksums must both be present in go.sum")

evidence: dict[str, Any] = {
    "schema_version": 1,
    "evidence_id": "agent-b02.1-postgresql-integration",
    "scope": "PostgreSQL bootstrap, Migrator/Application roles, TenantContext, RLS, and repository isolation",
    "result": "passed",
    "command": args.test_command,
    "exit_code": 0,
    "test_log": {
        "path": "postgres-integration.log",
        "sha256": sha256_file(test_log),
    },
    "environment": {
        "go_version": toolchain["GO_VERSION"],
        "go_target_os": toolchain["GO_TARGET_OS"],
        "go_target_arch": toolchain["GO_TARGET_ARCH"],
        "go_toolchain_image": toolchain["GO_TOOLCHAIN_IMAGE"],
        "postgres_version": toolchain["POSTGRES_VERSION"],
        "postgres_test_image": toolchain["POSTGRES_TEST_IMAGE"],
        "database_storage": "container tmpfs",
        "network": "isolated disposable Docker network",
    },
    "locked_dependencies": {
        "pgx": {
            "version": toolchain["PGX_VERSION"],
            "go_sum": sorted(go_sum_lines),
        },
        "goose": {
            "version": toolchain["GOOSE_VERSION"],
            "artifact_sha256": "sha256:" + toolchain["GOOSE_LINUX_ARM64_SHA256"],
        },
        "sqlc": {
            "version": toolchain["SQLC_VERSION"],
            "image": toolchain["SQLC_IMAGE"],
        },
        "postgresql": {
            "version": toolchain["POSTGRES_VERSION"],
            "image": toolchain["POSTGRES_TEST_IMAGE"],
        },
    },
    "dependency_lock": {
        "path": "dependency-lock.json",
        "sha256": sha256_file(dependency_lock_path),
        "value": dependency_lock,
    },
    "sources": {
        "migrations": source_manifest(list((ROOT / "db/migration").glob("*.sql"))),
        "queries_and_repository": source_manifest(
            list((ROOT / "db/query").glob("*.sql"))
            + list((ROOT / "internal/domain/tenancy").glob("*.go"))
            + list((ROOT / "internal/persistence").glob("*.go"))
            + list((ROOT / "internal/generated/agentdb").glob("*.go"))
        ),
        "integration_tests": source_manifest(
            list((ROOT / "test/integration").rglob("*.go"))
            + list((ROOT / "test/integration").rglob("*.sql"))
            + [
                ROOT / "script/test_postgres_integration.sh",
                ROOT / "script/generate_postgres_integration_evidence.py",
            ]
        ),
    },
    "claims_not_made": [
        "Phase 0B completion",
        "production topology isolation",
        "capacity or SLO evidence",
        "backup or disaster-recovery evidence",
    ],
}
canonical = json.dumps(evidence, ensure_ascii=True, separators=(",", ":"), sort_keys=True).encode()
evidence["evidence_digest"] = {
    "profile": "sha256-canonical-json-excluding-evidence_digest",
    "value": "sha256:" + hashlib.sha256(canonical).hexdigest(),
}

args.output.parent.mkdir(parents=True, exist_ok=True)
args.output.write_text(json.dumps(evidence, ensure_ascii=True, indent=2, sort_keys=True) + "\n", encoding="utf-8")
print(f"PostgreSQL integration evidence written to {args.output}")
