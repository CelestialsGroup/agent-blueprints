#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import zipfile
from pathlib import Path
from typing import Any

import generate_pre_transport_safety_evidence as common
import generate_start_http_boundary_evidence as prior

ROOT = Path(__file__).resolve().parents[1]
TEST_COUNT = re.compile(r"Ran (\d+) tests")
COMPACT_JWS = re.compile(
    rb"(?<![A-Za-z0-9_-])eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{20,}\."
    rb"[A-Za-z0-9_-]{20,}(?![A-Za-z0-9_-])"
)
PRIVATE_KEY_BLOCK = re.compile(
    rb"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----[\s\S]+?"
    rb"-----END [A-Z0-9 ]*PRIVATE KEY-----"
)
TRACEBACK_BLOCK = re.compile(rb"Traceback \(most recent call last\):\r?\n\s+File \"")
FORBIDDEN_EVIDENCE_FRAGMENTS = (
    b"Authorization: Bearer ",
    b"checkpoint-payload:",
    b"encoded_body_base64",
    b"sensitive-body-marker",
    b"sensitive-controlled-precommit-marker",
    b"-----BEGIN PRIVATE KEY-----",
    b"-----BEGIN RSA PRIVATE KEY-----",
    b"-----BEGIN EC PRIVATE KEY-----",
    b"Traceback (most recent call last)",
)
SOURCE_FILES = (
    *prior.SOURCE_FILES,
    "doc/plan/README.md",
    "doc/plan/B03.2a1.1.3-command-recovery-boundary.md",
    "script/generate_command_recovery_boundary_evidence.py",
)
SOURCE_CACHE_ROOTS = (
    "runtime/native/src",
    "runtime/native/test",
    "script",
)
REQUIRED_SOURCE_TESTS = (
    "test_checkpoint_driver_is_not_a_production_entrypoint",
    "test_checkpoint_object_may_be_orphaned_but_manifest_never_is",
    "test_command_error_mapping_is_closed_and_safe",
    "test_command_request_line_is_exact_dynamic_origin_form",
    "test_expired_work_lease_recovers_without_duplicate_run_or_event",
    "test_recovery_driver_is_test_only",
    "test_unsupported_commands_require_full_token_context_before_rejection",
    "test_worker_driver_is_not_a_production_entrypoint",
)
REQUIRED_COMMAND_TESTS = (
    "test_body_limit_short_read_slow_body_and_exact_limit",
    "test_concurrency_sqlite_busy_and_response_limit_are_closed",
    "test_crypto_oracle_durable_binding_and_unsupported_variants",
    "test_target_host_content_type_and_framing_are_strict",
    "test_valid_cancel_replay_conflicts_and_cancel_requested_boundary",
)
REQUIRED_TRANSACTION_TESTS = (
    "test_http_response_loss_reopens_and_replays_without_duplicates",
    "test_sigkill_transaction_windows_reopen_and_replay",
)
REQUIRED_LEASE_TESTS = ("test_sigkill_expiry_reclaim_and_stale_fencing",)
REQUIRED_CHECKPOINT_TESTS = ("test_sigkill_checkpoint_filesystem_and_manifest_windows",)
TRANSACTION_CASES = (
    "http_response_loss",
    "before_transaction",
    "before_commit",
    "after_commit",
)
LEASE_CASES = ("cancel", "checkpoint")
CHECKPOINT_CASES = (
    "partial_write",
    "full_write",
    "file_fsync",
    "renamed",
    "directory_fsync",
    "manifest_before_commit",
    "manifest_after_commit",
)


def _reject_source_caches() -> None:
    for relative in SOURCE_CACHE_ROOTS:
        for path in (ROOT / relative).rglob("*"):
            if "__pycache__" in path.parts or path.suffix == ".pyc":
                raise AssertionError(
                    f"source tree contains forbidden Python cache content: {path}"
                )


def source_paths() -> tuple[Path, ...]:
    _reject_source_caches()
    paths = [ROOT / relative for relative in SOURCE_FILES]
    for relative in common.SOURCE_DIRECTORIES:
        paths.extend(path for path in (ROOT / relative).rglob("*") if path.is_file())
    if any(
        not path.is_file() or "__pycache__" in path.parts or path.suffix == ".pyc"
        for path in paths
    ):
        raise AssertionError("source manifest contains non-source or cache content")
    return tuple(sorted(set(paths), key=lambda path: path.relative_to(ROOT).as_posix()))


def source_manifest(paths: tuple[Path, ...]) -> dict[str, Any]:
    files = [
        {
            "path": path.relative_to(ROOT).as_posix(),
            "sha256": "sha256:" + common.sha256_file(path),
        }
        for path in paths
    ]
    encoded = json.dumps(files, separators=(",", ":"), sort_keys=True).encode()
    return {
        "files": files,
        "source_set_sha256": "sha256:" + hashlib.sha256(encoded).hexdigest(),
        "cache_policy": {
            "forbidden": ["__pycache__", "*.pyc"],
            "observed_forbidden_count": 0,
            "failure_mode": "reject_generation",
        },
    }


def _scan_source_secrets(paths: tuple[Path, ...]) -> int:
    scanned = 0
    for path in paths:
        data = path.read_bytes()
        if PRIVATE_KEY_BLOCK.search(data):
            raise AssertionError(f"source contains a complete private-key PEM: {path}")
        if COMPACT_JWS.search(data):
            raise AssertionError(f"source contains a complete compact JWS: {path}")
        if TRACEBACK_BLOCK.search(data):
            raise AssertionError(f"source contains a captured traceback: {path}")
        scanned += 1
    return scanned


def _scan_evidence_bytes(name: str, data: bytes) -> None:
    for fragment in FORBIDDEN_EVIDENCE_FRAGMENTS:
        if fragment in data:
            raise AssertionError(f"{name} contains forbidden sensitive content")
    if PRIVATE_KEY_BLOCK.search(data):
        raise AssertionError(f"{name} contains a private-key PEM block")
    if COMPACT_JWS.search(data):
        raise AssertionError(f"{name} contains a complete compact JWS")
    if TRACEBACK_BLOCK.search(data):
        raise AssertionError(f"{name} contains a captured traceback")


def _scan_wheel(path: Path) -> int:
    count = 0
    with zipfile.ZipFile(path) as archive:
        for name in archive.namelist():
            if name.endswith("/"):
                continue
            _scan_evidence_bytes(f"wheel member {name}", archive.read(name))
            count += 1
    return count


def _validation_log(
    path: Path, name: str, required: tuple[str, ...]
) -> tuple[str, int]:
    text = path.read_text(encoding="utf-8")
    for fragment in (*required, "OK"):
        if fragment not in text:
            raise AssertionError(f"{name} lacks {fragment!r}")
    counts = [int(value) for value in TEST_COUNT.findall(text)]
    if not counts or counts[-1] < len(required):
        raise AssertionError(f"{name} lacks its required test count")
    _scan_evidence_bytes(name, text.encode())
    return text, counts[-1]


def _dynamic_cases(text: str, prefix: str, expected: tuple[str, ...]) -> list[str]:
    observed = re.findall(rf"{re.escape(prefix)}:([a-z_]+):passed", text)
    if observed != list(expected) or len(observed) != len(set(observed)):
        raise AssertionError(
            f"{prefix} dynamic cases differ: expected {expected!r}, observed {observed!r}"
        )
    return observed


def case_matrix(suite: dict[str, Any]) -> list[dict[str, str]]:
    profile = next(
        profile
        for profile in suite["profiles"]
        if profile["profile_id"] == "runtime-core-v1"
    )
    results = {
        "capabilities-immutable": (
            "a1_1_1_regression_passed",
            "immutable installed Capabilities regression remains green; production registration is absent",
        ),
        "start-idempotent": (
            "a1_1_2_regression_passed",
            "installed Start idempotency remains green",
        ),
        "start-digest-conflict": (
            "a1_1_2_regression_passed",
            "installed Start digest conflict remains green",
        ),
        "start-executable-context-complete": (
            "presented_context_subset_passed",
            "presented Start and Command context is cryptographically checked; production parent authority is absent",
        ),
        "start-encoded-body-limit": (
            "a1_1_2_regression_passed",
            "the installed Start 8 MiB pre-parse boundary remains green",
        ),
        "command-contiguous": (
            "installed_command_passed",
            "installed Command preserves contiguous sequence, idempotency and digest conflict behavior",
        ),
        "stale-fencing-rejected": (
            "installed_command_and_lease_subset_passed",
            "signed stale command fencing and expired worker lease identities cannot mutate durable facts",
        ),
        "typed-event-payloads": (
            "provider_event_regression_subset_passed",
            "Provider-local emitted events remain Schema-valid; Event HTTP and CanonicalEvent are absent",
        ),
        "cursor-resume": (
            "provider_store_regression_passed",
            "Provider-local cursor resume remains green below transport; Event HTTP is absent",
        ),
        "cursor-expired-explicit": (
            "provider_store_regression_passed",
            "Provider-local explicit cursor expiry remains green below transport; Event HTTP is absent",
        ),
        "cancel-confirmed": (
            "installed_worker_subset_passed",
            "cancel_requested becomes cancelled only after installed test-executor evidence; production executor is absent",
        ),
        "checkpoint-compatibility": (
            "installed_same_revision_subset_passed",
            "installed crash recovery verifies exact Provider/runtime/profile same_revision only",
        ),
        "adapter-restart-resume": (
            "installed_process_reopen_subset_passed",
            "installed processes reopen one Provider-local SQLite run after crash; no Go adapter exists",
        ),
        "authorization-renewal": (
            "platform_blocked",
            "requires authoritative append-only RuntimeAuthorization and ArtifactGrant lineage",
        ),
        "runtime-token-replay-and-expiry": (
            "installed_command_token_subset_passed",
            "installed Command covers bounded JWS identity claims time and mutation replay; production issuance is absent",
        ),
        "system-safety-control": (
            "provider_safety_subset_passed",
            "presented safety-control Cancel and Pause remain reduction-only; production Safety Controller authority is absent",
        ),
        "outcome-unknown-reconcile": (
            "installed_response_loss_and_sigkill_subset_passed",
            "post-commit response loss and SIGKILL reopen preserve one Command; Platform reconciliation is absent",
        ),
    }
    tests = profile.get("tests")
    if not isinstance(tests, list) or not tests:
        raise AssertionError("locked runtime-core-v1 has no cases")
    case_ids = [test["test_id"] for test in tests]
    if len(case_ids) != 17 or len(case_ids) != len(set(case_ids)):
        raise AssertionError("runtime-core-v1 case count or uniqueness changed")
    if set(case_ids) != set(results):
        raise AssertionError("runtime-core-v1 cases and a1.1.3 mapping differ")
    return [
        {
            "case_id": case_id,
            "verdict": results[case_id][0],
            "boundary": results[case_id][1],
        }
        for case_id in case_ids
    ]


def _log_evidence(path: Path) -> dict[str, str]:
    return {"path": path.name, "sha256": "sha256:" + common.sha256_file(path)}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--application-base-revision", required=True)
    parser.add_argument("--validation-command", required=True)
    parser.add_argument("--python-validation-log", type=Path, required=True)
    parser.add_argument("--installed-command-log", type=Path, required=True)
    parser.add_argument("--transaction-log", type=Path, required=True)
    parser.add_argument("--lease-log", type=Path, required=True)
    parser.add_argument("--checkpoint-log", type=Path, required=True)
    parser.add_argument("--supply-chain-log", type=Path, required=True)
    parser.add_argument("--native-runtime-artifact", type=Path, required=True)
    parser.add_argument("--native-runtime-rebuild", type=Path, required=True)
    parser.add_argument("--implementation-evidence-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    if not common.GIT_REVISION.fullmatch(arguments.application_base_revision):
        raise AssertionError("Application base revision is not a full Git object ID")

    source_text, source_count = _validation_log(
        arguments.python_validation_log,
        "Native Runtime source log",
        REQUIRED_SOURCE_TESTS,
    )
    for fragment in (
        "ruff 0.16.0",
        "Ruff format check passed.",
        "Ruff lint check passed.",
        "mypy 2.3.0",
        "mypy strict check passed.",
    ):
        if fragment not in source_text:
            raise AssertionError(f"Native Runtime source log lacks {fragment!r}")
    _, command_count = _validation_log(
        arguments.installed_command_log,
        "installed Command HTTP log",
        REQUIRED_COMMAND_TESTS,
    )
    transaction_text, transaction_count = _validation_log(
        arguments.transaction_log,
        "installed Command transaction log",
        REQUIRED_TRANSACTION_TESTS,
    )
    lease_text, lease_count = _validation_log(
        arguments.lease_log,
        "installed work lease log",
        REQUIRED_LEASE_TESTS,
    )
    checkpoint_text, checkpoint_count = _validation_log(
        arguments.checkpoint_log,
        "installed checkpoint crash log",
        REQUIRED_CHECKPOINT_TESTS,
    )
    transaction_cases = _dynamic_cases(
        transaction_text,
        "command-transaction-recovery-case",
        TRANSACTION_CASES,
    )
    lease_cases = _dynamic_cases(
        lease_text,
        "work-lease-recovery-case",
        LEASE_CASES,
    )
    checkpoint_cases = _dynamic_cases(
        checkpoint_text,
        "checkpoint-crash-consistency-case",
        CHECKPOINT_CASES,
    )
    supply_chain_text = arguments.supply_chain_log.read_text(encoding="utf-8")
    if "Implementation supply-chain check passed:" not in supply_chain_text:
        raise AssertionError("supply-chain validation log is incomplete")
    _scan_evidence_bytes("supply-chain log", supply_chain_text.encode())

    paths = source_paths()
    source_scan_count = _scan_source_secrets(paths)
    wheel_member_count = _scan_wheel(arguments.native_runtime_artifact)
    scanned_supply_files = 0
    for path in sorted(arguments.implementation_evidence_dir.rglob("*")):
        if path.is_file():
            _scan_evidence_bytes(
                f"implementation evidence {path.name}", path.read_bytes()
            )
            scanned_supply_files += 1

    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    copied = {
        "native_runtime": arguments.output.parent / "native-runtime-validation.log",
        "installed_command_http": arguments.output.parent
        / "installed-command-http-validation.log",
        "installed_command_transaction": arguments.output.parent
        / "installed-command-transaction-recovery.log",
        "installed_work_lease": arguments.output.parent
        / "installed-work-lease-recovery.log",
        "installed_checkpoint": arguments.output.parent
        / "installed-checkpoint-recovery.log",
        "supply_chain": arguments.output.parent / "supply-chain.log",
    }
    sources = {
        "native_runtime": arguments.python_validation_log,
        "installed_command_http": arguments.installed_command_log,
        "installed_command_transaction": arguments.transaction_log,
        "installed_work_lease": arguments.lease_log,
        "installed_checkpoint": arguments.checkpoint_log,
        "supply_chain": arguments.supply_chain_log,
    }
    for key, target in copied.items():
        shutil.copyfile(sources[key], target)
        _scan_evidence_bytes(f"copied log {target.name}", target.read_bytes())

    lock_path = ROOT / "dependency-lock.json"
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    lock_entry, suite = common.runtime_suite(lock)
    projection_path = ROOT / "internal/generated/runtimeapi/projection-manifest.json"
    projection = json.loads(projection_path.read_text(encoding="utf-8"))
    predecessor_path = ROOT / "build/evidence/b03.2a1.1.2/start-http-boundary.json"
    evidence = {
        "evidence_version": 1,
        "slice_id": "B03.2a1.1.3",
        "scope": "command_and_recovery_boundary",
        "result": "passed",
        "conformance_profile_result": "not_claimed",
        "application_base_revision": arguments.application_base_revision,
        "application_source": source_manifest(paths),
        "blueprint": lock["blueprint"],
        "contract": lock["contract"],
        "dependency_lock_sha256": "sha256:" + common.sha256_file(lock_path),
        "contract_manifest_digest": lock["contract"]["manifest_digest"],
        "runtime_suite": lock_entry,
        "runtime_suite_canonical_sha256": "sha256:"
        + hashlib.sha256(
            json.dumps(suite, separators=(",", ":"), sort_keys=True).encode()
        ).hexdigest(),
        "runtime_projection": {
            "manifest_sha256": "sha256:" + common.sha256_file(projection_path),
            "schema_count": projection["schema_count"],
            "schema_closure_sha256": "sha256:" + projection["schema_closure_sha256"],
            "openapi_sha256": "sha256:" + projection["openapi_sha256"],
        },
        "predecessor_evidence": {
            "path": predecessor_path.relative_to(ROOT).as_posix(),
            "sha256": "sha256:" + common.sha256_file(predecessor_path),
        },
        "dependencies": common.dependency_evidence(),
        "sqlite_migrations": common.migration_evidence(),
        "command_http_boundary": {
            "route": "POST /v1/runs/{runtime_run_id}/commands",
            "http_version": "HTTP/1.1",
            "request_target": "exact_dynamic_origin_form",
            "content_type": "application/json",
            "max_encoded_body_bytes": 262_144,
            "framing": {
                "host": "single_canonical_configured_value",
                "content_length": "single_canonical_decimal_required",
                "transfer_encoding": "rejected",
                "chunked": "rejected",
                "expect": "rejected",
                "query_fragment_and_percent_substitution": "rejected",
                "short_read_half_close_and_timeout": "bounded_close_or_closed_error",
            },
            "authentication": {
                "mutual_tls": "required",
                "certificate_subject_binding": "exact_token_sub",
                "bearer": "single_bounded_compact_jws",
                "operation": "submit_command",
                "path_body_claim_and_digest": "independently_bound",
                "invalid_context_store_access": 0,
                "unauthorized_run_existence_oracle": "absent",
            },
            "success": {
                "status": 202,
                "schema": "urn:agent-platform:agent-runtime-run-status:v1",
                "meaning": "accepted_not_execution_complete",
            },
            "closed_error_statuses": [
                400,
                401,
                403,
                404,
                409,
                413,
                422,
                429,
                500,
                503,
            ],
            "error_schema": "urn:agent-platform:standard-error:v1",
        },
        "command_variants": [
            {"variant": "pause", "provider_local_result": "accepted"},
            {"variant": "resume", "provider_local_result": "accepted"},
            {
                "variant": "cancel",
                "provider_local_result": "accepted_as_cancel_requested",
            },
            {
                "variant": "checkpoint",
                "provider_local_result": "accepted_as_pending_work",
            },
            {
                "variant": "append_input",
                "provider_local_result": "422_after_crypto_before_store",
            },
            {
                "variant": "interrupt",
                "provider_local_result": "422_after_crypto_before_store",
            },
            {
                "variant": "approval_decision",
                "provider_local_result": "422_after_crypto_before_store",
            },
            {
                "variant": "subagent_spawn_decision",
                "provider_local_result": "422_after_crypto_before_store",
            },
        ],
        "recovery": {
            "command_transaction_cases": transaction_cases,
            "work_lease_cases": lease_cases,
            "checkpoint_crash_cases": checkpoint_cases,
            "process_signal": "SIGKILL_external_parent_verified_negative_returncode",
            "runtime": "installed_wheel_subprocess",
            "durability": "SQLite_open_current_reopen_and_real_filesystem",
            "checkpoint_invariant": "orphan_allowed_manifest_missing_content_forbidden",
            "checkpoint_compatibility": "same_revision_only",
            "physical_power_loss_or_filesystem_freeze": "not_claimed",
        },
        "authority_gaps": [
            {
                "gap_id": "status-event-http-400",
                "status": "blocked",
                "machine_readable": True,
                "reason": "locked OpenAPI omits authoritative 400 responses for Status and Event reads",
                "action": "do_not_guess_or_modify_contract",
            },
            {
                "gap_id": "production-runtime-authority",
                "status": "not_in_slice",
                "includes": [
                    "Go adapter",
                    "production worker or composition root",
                    "ProviderResolution",
                    "token issuer and private-key custody",
                    "Platform PostgreSQL or Temporal caller",
                    "CanonicalEvent",
                    "production Safety Controller",
                ],
            },
        ],
        "validation": {
            "command": arguments.validation_command,
            "source_test_count": source_count,
            "installed_command_test_count": command_count,
            "installed_transaction_test_count": transaction_count,
            "installed_lease_test_count": lease_count,
            "installed_checkpoint_test_count": checkpoint_count,
            "dynamic_recovery_case_count": len(
                transaction_cases + lease_cases + checkpoint_cases
            ),
            "quality": {
                "ruff_version": "0.16.0",
                "ruff_format": "passed",
                "ruff_lint": "passed",
                "mypy_version": "2.3.0",
                "mypy_strict": "passed",
            },
            "logs": {key: _log_evidence(path) for key, path in copied.items()},
        },
        "sensitive_scan": {
            "result": "passed",
            "source_files_scanned": source_scan_count,
            "wheel_members_scanned": wheel_member_count,
            "implementation_supply_chain_files_scanned": scanned_supply_files,
            "copied_logs_scanned": len(copied),
            "categories": [
                "complete_compact_jws",
                "authorization_bearer_value",
                "request_body_canary",
                "checkpoint_content_canary",
                "private_key_pem_block",
                "captured_traceback",
            ],
        },
        "runtime_core_case_matrix": case_matrix(suite),
        "supply_chain": common.supply_chain_evidence(
            arguments.native_runtime_artifact,
            arguments.native_runtime_rebuild,
            arguments.implementation_evidence_dir,
        ),
        "proven": [
            "strict installed Command HTTP admission and closed Schema-validated responses",
            "cryptographic admission precedes every invalid-context store access and durable binding lookup",
            "mutation JTI Command state work and event facts retain one SQLite transaction",
            "real installed-process SIGKILL transaction response-loss lease and checkpoint recovery",
            "checkpoint publish uses file and directory fsync before one atomic manifest event and work transaction",
            "reproducible wheel dependency audit SPDX 2.3 SLSA v1 and BuildProvenance",
        ],
        "not_proven": [
            "Status or Event HTTP transport and the blocked Status Event HTTP 400 interpretation",
            "production worker executor composition Provider caller or external side-effect exactly-once",
            "Go adapter ProviderResolution token issuer private-key custody or Platform PostgreSQL Temporal caller",
            "CanonicalEvent production Safety Controller or authoritative Platform parent facts",
            "cross-revision checkpoint compatibility portability or physical power-loss certification",
            "aggregate runtime-core-v1 end-to-end reliability freeze security approval or production readiness",
        ],
    }
    matrix = evidence["runtime_core_case_matrix"]
    if len(matrix) != 17 or len({item["case_id"] for item in matrix}) != 17:
        raise AssertionError("a1.1.3 evidence must preserve 17 unique Suite cases")
    for value in (
        evidence["dependency_lock_sha256"],
        evidence["contract_manifest_digest"],
        evidence["runtime_suite"]["suite_digest"],
    ):
        if not isinstance(value, str) or not common.SHA256_DIGEST.fullmatch(value):
            raise AssertionError("a1.1.3 governed digest is invalid")
    encoded = (json.dumps(evidence, indent=2, sort_keys=True) + "\n").encode()
    _scan_evidence_bytes("Command recovery evidence", encoded)
    arguments.output.write_bytes(encoded)


if __name__ == "__main__":
    main()
