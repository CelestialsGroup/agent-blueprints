#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
GIT_REVISION = re.compile(r"^[0-9a-f]{40,64}$")
TEST_COUNT = re.compile(r"Ran (\d+) tests")
EXPECTED_CASE_IDS = (
    "capabilities-immutable",
    "start-idempotent",
    "start-digest-conflict",
    "start-executable-context-complete",
    "start-encoded-body-limit",
    "command-contiguous",
    "stale-fencing-rejected",
    "typed-event-payloads",
    "cursor-resume",
    "cursor-expired-explicit",
    "cancel-confirmed",
    "checkpoint-compatibility",
    "adapter-restart-resume",
    "authorization-renewal",
    "runtime-token-replay-and-expiry",
    "system-safety-control",
    "outcome-unknown-reconcile",
)
REQUIRED_TESTS = (
    "test_cancel_is_terminal_only_after_executor_evidence",
    "test_checkpoint_is_content_addressed_and_restores_same_revision",
    "test_checkpoint_object_may_be_orphaned_but_manifest_never_is",
    "test_command_sequence_fencing_replay_and_authority",
    "test_concurrent_migrate_serializes_schema_and_configuration",
    "test_concurrent_start_serializes_to_one_run_and_one_event",
    "test_cursor_resume_and_expiry_are_explicit",
    "test_emitted_events_validate_against_locked_contract",
    "test_expired_work_lease_recovers_without_duplicate_run_or_event",
    "test_expired_worker_cannot_complete_after_lease_loss",
    "test_retention_rejects_a_checkpoint_with_missing_content",
    "test_sqlite_durability_pragmas_and_strict_schema_are_active",
    "test_start_idempotency_conflict_and_jti_consumption_are_atomic",
    "test_start_rejects_non_empty_sandbox_bindings_without_side_effects",
)
SOURCE_FILES = (
    "dependency-lock.json",
    "doc/plan/B03.2-native-runtime-core-conformance-safety-integration.md",
    "runtime/native/build-constraints.txt",
    "runtime/native/pyproject.toml",
    "runtime/native/test/test_durable_kernel.py",
    "runtime/native/uv.lock",
    "script/check_implementation_supply_chain.py",
    "script/generate_native_runtime_kernel_evidence.py",
    "script/validate_implementation.sh",
    "toolchain/third-party.json",
)
SOURCE_DIRECTORIES = (
    "runtime/native/src/agent_native_runtime",
    "runtime/native/test",
)


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def source_manifest() -> dict[str, Any]:
    paths = [ROOT / relative for relative in SOURCE_FILES]
    for relative in SOURCE_DIRECTORIES:
        paths.extend(path for path in (ROOT / relative).rglob("*") if path.is_file())
    files = [
        {
            "path": path.relative_to(ROOT).as_posix(),
            "sha256": "sha256:" + sha256_file(path),
        }
        for path in sorted(
            set(paths), key=lambda item: item.relative_to(ROOT).as_posix()
        )
    ]
    encoded = json.dumps(files, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return {
        "files": files,
        "source_set_sha256": "sha256:" + hashlib.sha256(encoded).hexdigest(),
    }


def runtime_suite(lock: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    lock_entry = next(
        suite
        for suite in lock["contract"]["suites"]
        if suite["suite_id"] == "agent-runtime-provider"
    )
    contract_root = Path(
        os.environ.get("AGENT_CONTRACT_ROOT", ROOT.parent / "contract")
    ).resolve()
    suite = json.loads(
        (contract_root / "conformance/runtime/v1/suite.json").read_text(
            encoding="utf-8"
        )
    )
    if suite["suite_digest"] != lock_entry["suite_digest"]:
        raise AssertionError("Runtime Suite digest differs from the Application lock")
    profile = next(
        profile
        for profile in suite["profiles"]
        if profile["profile_id"] == "runtime-core-v1"
    )
    case_ids = tuple(test["test_id"] for test in profile["tests"])
    if case_ids != EXPECTED_CASE_IDS:
        raise AssertionError("runtime-core-v1 case order or membership changed")
    return lock_entry, suite


def case_matrix() -> list[dict[str, str]]:
    results = {
        "capabilities-immutable": (
            "not_in_a0",
            "immutable configuration is bound, but the Capabilities document and HTTP operation are a1",
        ),
        "start-idempotent": (
            "kernel_passed",
            "fresh-JTI replay returns one RuntimeRun and one start event under SQLite serialization",
        ),
        "start-digest-conflict": (
            "kernel_passed",
            "digest conflict creates no Runtime fact and consumes no JTI",
        ),
        "start-executable-context-complete": (
            "not_in_a0",
            "full generated Schema and semantic admission belongs to a1 and Platform authority remains absent",
        ),
        "start-encoded-body-limit": (
            "not_in_a0",
            "pre-parse HTTP body limiting belongs to a1",
        ),
        "command-contiguous": (
            "kernel_passed",
            "new commands require the next sequence; exact replay uses a fresh JTI",
        ),
        "stale-fencing-rejected": (
            "kernel_passed",
            "new commands and expired work owners cannot mutate under stale fencing",
        ),
        "typed-event-payloads": (
            "kernel_subset_passed",
            "every event emitted by a0 validates against the locked Registry Schema; a0 does not emit every core type",
        ),
        "cursor-resume": (
            "kernel_passed",
            "reads use event_sequence greater than the exact durable cursor without duplicates",
        ),
        "cursor-expired-explicit": (
            "kernel_passed",
            "retained ranges reject old cursors with explicit earliest and latest recovery facts",
        ),
        "cancel-confirmed": (
            "kernel_subset_passed",
            "cancel_requested becomes cancelled only after private execution-loop evidence; Platform projection is absent",
        ),
        "checkpoint-compatibility": (
            "same_revision_subset_passed",
            "exact ProviderRevision, Runtime revision, profile, digest, size and content restore; cross-revision is rejected",
        ),
        "adapter-restart-resume": (
            "store_restart_subset_passed",
            "SQLite and expired work leases recover the same RuntimeRun; no Go adapter exists in a0",
        ),
        "authorization-renewal": (
            "platform_blocked",
            "requires authoritative RunManifest, RuntimeAuthorization and ArtifactGrant lineage",
        ),
        "runtime-token-replay-and-expiry": (
            "jti_subset_passed",
            "atomic mutation JTI replay and local deadline checks pass; JWS, mTLS and claim time bounds are a1",
        ),
        "system-safety-control": (
            "kernel_authority_subset_passed",
            "reduction-only Pause or Cancel shape is enforced; no production Safety Controller or dispatch exists",
        ),
        "outcome-unknown-reconcile": (
            "not_in_a0",
            "HTTP uncertainty classification and component reconciliation belong to a2",
        ),
    }
    return [
        {
            "case_id": case_id,
            "verdict": results[case_id][0],
            "boundary": results[case_id][1],
        }
        for case_id in EXPECTED_CASE_IDS
    ]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--application-base-revision", required=True)
    parser.add_argument("--validation-command", required=True)
    parser.add_argument("--python-validation-log", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    if not GIT_REVISION.fullmatch(arguments.application_base_revision):
        raise AssertionError("Application base revision is not a full Git object ID")

    validation_text = arguments.python_validation_log.read_text(encoding="utf-8")
    for fragment in REQUIRED_TESTS + (
        "ruff 0.16.0",
        "Ruff format check passed.",
        "Ruff lint check passed.",
        "mypy 2.3.0",
        "Success: no issues found in",
        "mypy strict check passed.",
        "OK",
    ):
        if fragment not in validation_text:
            raise AssertionError(f"Native Runtime validation log lacks {fragment!r}")
    counts = [int(value) for value in TEST_COUNT.findall(validation_text)]
    if not counts or counts[-1] < 36:
        raise AssertionError("Native Runtime validation log lacks the current test set")

    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    copied_log = arguments.output.parent / "native-runtime-validation.log"
    shutil.copyfile(arguments.python_validation_log, copied_log)

    lock_path = ROOT / "dependency-lock.json"
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    lock_entry, suite = runtime_suite(lock)
    evidence = {
        "evidence_version": 1,
        "slice_id": "B03.2a0",
        "scope": "native_runtime_durable_kernel",
        "result": "passed",
        "conformance_profile_result": "not_claimed",
        "application_base_revision": arguments.application_base_revision,
        "application_source": source_manifest(),
        "blueprint": lock["blueprint"],
        "contract": lock["contract"],
        "dependency_lock_sha256": "sha256:" + sha256_file(lock_path),
        "contract_manifest_digest": lock["contract"]["manifest_digest"],
        "runtime_suite": lock_entry,
        "runtime_suite_canonical_sha256": "sha256:"
        + hashlib.sha256(
            json.dumps(suite, separators=(",", ":"), sort_keys=True).encode("utf-8")
        ).hexdigest(),
        "sqlite_migrations": {
            "up_sha256": "sha256:"
            + sha256_file(
                ROOT
                / "runtime/native/src/agent_native_runtime/migrations/0001_runtime_durable_kernel.up.sql"
            ),
            "down_sha256": "sha256:"
            + sha256_file(
                ROOT
                / "runtime/native/src/agent_native_runtime/migrations/0001_runtime_durable_kernel.down.sql"
            ),
            "durability": [
                "foreign_keys=ON",
                "journal_mode=WAL",
                "synchronous=FULL",
                "bounded busy_timeout",
                "BEGIN IMMEDIATE writes",
                "STRICT tables",
            ],
        },
        "validation": {
            "command": arguments.validation_command,
            "log": {
                "path": copied_log.name,
                "sha256": "sha256:" + sha256_file(copied_log),
            },
            "quality": {
                "ruff_version": "0.16.0",
                "ruff_format": "passed",
                "ruff_lint": "passed",
                "mypy_version": "2.3.0",
                "mypy_strict": "passed",
            },
            "test_count": counts[-1],
        },
        "runtime_core_case_matrix": case_matrix(),
        "proven": [
            "immutable ProviderRevision and Runtime revision configuration binding per state root",
            "Provider-local SQLite mutation atomicity, idempotency, JTI replay protection, sequence and fencing",
            "typed a0 event persistence, exact cursor resume and explicit expired cursor recovery",
            "closed Runtime event data variants with fail-closed SQLite document mapping",
            "cancel intent separated from terminal execution-loop evidence",
            "same-revision content-addressed checkpoint write, restart and crash-window recovery",
            "sandboxes=[] and reduction-only local safety authority shape",
            "locked Ruff format and lint plus mypy strict checks over Native Runtime source and tests",
        ],
        "not_proven": [
            "this a0 evidence does not prove HTTP/process entrypoints, Strict I-JSON, body limits, StandardError, JWS or mTLS",
            "Go AgentRuntimeProvider Port, HTTP adapter, outcome_unknown classification or reconciliation",
            "complete Start executable-context or RuntimeAuthorization authority admission",
            "production ProviderRevision, AgentRun, RuntimeRun, RunManifest, InvocationAttempt or CanonicalEvent authority",
            "production Safety Controller, Temporal dispatch, Outbox wiring or composition root",
            "complete runtime-core-v1 profile, cross-revision checkpoint compatibility, reliability or production readiness",
        ],
    }
    arguments.output.write_text(
        json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
