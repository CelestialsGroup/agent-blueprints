#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path
from typing import Any

import generate_command_recovery_boundary_evidence as prior
import generate_pre_transport_safety_evidence as common

ROOT = Path(__file__).resolve().parents[1]
SOURCE_FILES = (
    *prior.SOURCE_FILES,
    "doc/plan/B03.2a1.1.4-read-boundary-evidence-closure.md",
    "runtime/native/README.md",
    "runtime/native/test/README.md",
    "script/README.md",
    "script/generate_read_boundary_evidence.py",
)
REQUIRED_SOURCE_TESTS = (
    "test_cursor_resume_and_expiry_are_explicit",
    "test_event_page_document_preserves_order_and_next_cursor",
    "test_exact_status_and_event_targets_apply_openapi_defaults",
    "test_malformed_read_targets_remain_outside_the_admitted_handler",
    "test_read_error_mapping_uses_only_declared_statuses_and_safe_details",
    "test_read_path_and_cursor_replacement_are_rejected",
    "test_secure_lifecycle_uses_both_algorithms_and_authorized_reads",
)
REQUIRED_READ_TESTS = (
    "test_crypto_oracle_binding_and_admitted_not_found",
    "test_cursor_resume_empty_page_and_expiry_are_explicit",
    "test_valid_status_and_default_events_are_read_only",
    "test_event_page_document_preserves_order_and_next_cursor",
    "test_exact_status_and_event_targets_apply_openapi_defaults",
    "test_malformed_read_targets_remain_outside_the_admitted_handler",
    "test_read_error_mapping_uses_only_declared_statuses_and_safe_details",
)
READ_CASES = (
    "crypto_oracle_binding_not_found",
    "cursor_resume_empty_expiry",
    "status_default_events_read_only",
)


def source_paths() -> tuple[Path, ...]:
    prior._reject_source_caches()
    paths = [ROOT / relative for relative in SOURCE_FILES]
    for relative in common.SOURCE_DIRECTORIES:
        paths.extend(path for path in (ROOT / relative).rglob("*") if path.is_file())
    if any(
        not path.is_file() or "__pycache__" in path.parts or path.suffix == ".pyc"
        for path in paths
    ):
        raise AssertionError("read evidence source manifest contains cache content")
    return tuple(sorted(set(paths), key=lambda path: path.relative_to(ROOT).as_posix()))


def case_matrix(suite: dict[str, Any]) -> list[dict[str, str]]:
    profile = next(
        profile
        for profile in suite["profiles"]
        if profile["profile_id"] == "runtime-core-v1"
    )
    results = {
        "capabilities-immutable": (
            "a1_1_1_regression_passed",
            "installed immutable Capabilities regression remains green; production registration is absent",
        ),
        "start-idempotent": (
            "a1_1_2_regression_passed",
            "installed Start idempotency regression remains green",
        ),
        "start-digest-conflict": (
            "a1_1_2_regression_passed",
            "installed Start digest-conflict regression remains green",
        ),
        "start-executable-context-complete": (
            "presented_context_subset_passed",
            "presented Start and read context is cryptographically checked; production parent authority is absent",
        ),
        "start-encoded-body-limit": (
            "a1_1_2_regression_passed",
            "installed Start encoded-body regression remains green",
        ),
        "command-contiguous": (
            "a1_1_3_regression_passed",
            "installed Command sequence and idempotency regression remains green",
        ),
        "stale-fencing-rejected": (
            "installed_command_read_and_lease_subset_passed",
            "signed stale request fencing and expired worker identities cannot mutate Provider-local facts",
        ),
        "typed-event-payloads": (
            "installed_provider_event_read_passed",
            "installed Event HTTP returns ordered Schema-valid Provider-local typed events; CanonicalEvent is absent",
        ),
        "cursor-resume": (
            "installed_provider_event_read_passed",
            "installed Event HTTP proves exact strict cursor resume and empty-page next cursor",
        ),
        "cursor-expired-explicit": (
            "installed_provider_event_read_passed",
            "installed Event HTTP returns Schema-valid 410 with bounded recovery details after real retention",
        ),
        "cancel-confirmed": (
            "a1_1_3_installed_worker_subset_passed",
            "cancel becomes terminal only after installed test-executor evidence; production executor is absent",
        ),
        "checkpoint-compatibility": (
            "a1_1_3_same_revision_subset_passed",
            "installed checkpoint recovery proves exact same-revision compatibility only",
        ),
        "adapter-restart-resume": (
            "installed_process_reopen_subset_passed",
            "installed processes reopen Provider-local SQLite facts; no Go adapter exists",
        ),
        "authorization-renewal": (
            "platform_blocked",
            "requires authoritative append-only RuntimeAuthorization and ArtifactGrant lineage",
        ),
        "runtime-token-replay-and-expiry": (
            "installed_read_and_mutation_token_subset_passed",
            "read JTI is reusable and mutation replay remains atomic; production issuance and custody are absent",
        ),
        "system-safety-control": (
            "provider_safety_subset_passed",
            "presented safety-control requests remain reduction-only; production Safety Controller is absent",
        ),
        "outcome-unknown-reconcile": (
            "a1_1_3_response_loss_and_sigkill_subset_passed",
            "Provider-local reopen preserves one outcome; Platform reconciliation is absent",
        ),
    }
    tests = profile.get("tests")
    if not isinstance(tests, list) or not tests:
        raise AssertionError("locked runtime-core-v1 has no cases")
    case_ids = [test["test_id"] for test in tests]
    if len(case_ids) != 17 or len(case_ids) != len(set(case_ids)):
        raise AssertionError("runtime-core-v1 case count or uniqueness changed")
    if set(case_ids) != set(results):
        raise AssertionError("runtime-core-v1 cases and a1.1.4 mapping differ")
    return [
        {
            "case_id": case_id,
            "verdict": results[case_id][0],
            "boundary": results[case_id][1],
        }
        for case_id in case_ids
    ]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--application-base-revision", required=True)
    parser.add_argument("--validation-command", required=True)
    parser.add_argument("--python-validation-log", type=Path, required=True)
    parser.add_argument("--installed-read-log", type=Path, required=True)
    parser.add_argument("--supply-chain-log", type=Path, required=True)
    parser.add_argument("--native-runtime-artifact", type=Path, required=True)
    parser.add_argument("--native-runtime-rebuild", type=Path, required=True)
    parser.add_argument("--implementation-evidence-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    if not common.GIT_REVISION.fullmatch(arguments.application_base_revision):
        raise AssertionError("Application base revision is not a full Git object ID")

    source_text, source_count = prior._validation_log(
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
    read_text, read_file_count = prior._validation_log(
        arguments.installed_read_log,
        "installed read HTTP log",
        REQUIRED_READ_TESTS,
    )
    if read_file_count != len(REQUIRED_READ_TESTS):
        raise AssertionError("installed read log test count differs")
    read_cases = prior._dynamic_cases(
        read_text,
        "read-boundary-case",
        READ_CASES,
    )
    supply_chain_text = arguments.supply_chain_log.read_text(encoding="utf-8")
    if "Implementation supply-chain check passed:" not in supply_chain_text:
        raise AssertionError("supply-chain validation log is incomplete")
    prior._scan_evidence_bytes("supply-chain log", supply_chain_text.encode())

    paths = source_paths()
    source_scan_count = prior._scan_source_secrets(paths)
    wheel_member_count = prior._scan_wheel(arguments.native_runtime_artifact)
    scanned_supply_files = 0
    for path in sorted(arguments.implementation_evidence_dir.rglob("*")):
        if path.is_file():
            prior._scan_evidence_bytes(
                f"implementation evidence {path.name}", path.read_bytes()
            )
            scanned_supply_files += 1

    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    copied = {
        "native_runtime": arguments.output.parent / "native-runtime-validation.log",
        "installed_read_http": arguments.output.parent
        / "installed-read-http-validation.log",
        "supply_chain": arguments.output.parent / "supply-chain.log",
    }
    sources = {
        "native_runtime": arguments.python_validation_log,
        "installed_read_http": arguments.installed_read_log,
        "supply_chain": arguments.supply_chain_log,
    }
    for key, target in copied.items():
        shutil.copyfile(sources[key], target)
        prior._scan_evidence_bytes(f"copied log {target.name}", target.read_bytes())

    lock_path = ROOT / "dependency-lock.json"
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    lock_entry, suite = common.runtime_suite(lock)
    projection_path = ROOT / "internal/generated/runtimeapi/projection-manifest.json"
    projection = json.loads(projection_path.read_text(encoding="utf-8"))
    predecessor_path = (
        ROOT / "build/evidence/b03.2a1.1.3/command-recovery-boundary.json"
    )
    evidence = {
        "evidence_version": 1,
        "slice_id": "B03.2a1.1.4",
        "scope": "read_boundary_and_evidence_closure",
        "result": "passed",
        "maturity": "provider_local_component",
        "conformance_profile_result": "not_claimed",
        "application_base_revision": arguments.application_base_revision,
        "application_source": prior.source_manifest(paths),
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
        "read_http_boundary": {
            "routes": [
                "GET /v1/runs/{runtime_run_id}",
                "GET /v1/runs/{runtime_run_id}/events",
            ],
            "http_version": "HTTP/1.1",
            "request_target": "exact_dynamic_origin_form",
            "runtime_run_id_max_ascii_bytes": 200,
            "event_query": {
                "after_event_sequence": {
                    "default": 0,
                    "minimum": 0,
                    "maximum": 9_007_199_254_740_991,
                },
                "limit": {"default": 1000, "minimum": 1, "maximum": 1000},
                "canonical_decimal_only": True,
                "default_normalized_before_descriptor_digest": True,
            },
            "authentication": {
                "mutual_tls": "required",
                "bearer": "single_bounded_compact_jws",
                "certificate_subject_binding": "exact_token_sub",
                "operations": ["read_status", "read_events"],
                "request_claim_and_descriptor_digest": "independently_bound",
                "invalid_signature_run_existence_oracle": "absent",
            },
            "success": [
                {
                    "operation": "read_status",
                    "status": 200,
                    "schema": "urn:agent-platform:agent-runtime-run-status:v1",
                },
                {
                    "operation": "read_events",
                    "status": 200,
                    "schema": "urn:agent-platform:agent-runtime-event-page:v1",
                },
            ],
            "closed_error_statuses": [401, 403, 404, 410, 500, 503],
            "error_schema": "urn:agent-platform:standard-error:v1",
            "read_jti_persistence": "none_repeated_same_token_passed",
            "durable_write_delta": "none",
            "cursor_recovery": "bounded_no_checkpoint_content",
            "malformed_http_verdict": "blocked_not_counted_as_passed",
        },
        "dynamic_read_cases": read_cases,
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
            "read_test_file_count": read_file_count,
            "installed_read_test_count": len(READ_CASES),
            "dynamic_read_case_count": len(read_cases),
            "quality": {
                "ruff_version": "0.16.0",
                "ruff_format": "passed",
                "ruff_lint": "passed",
                "mypy_version": "2.3.0",
                "mypy_strict": "passed",
            },
            "logs": {key: prior._log_evidence(path) for key, path in copied.items()},
        },
        "sensitive_scan": {
            "result": "passed",
            "source_files_scanned": source_scan_count,
            "wheel_members_scanned": wheel_member_count,
            "implementation_supply_chain_files_scanned": scanned_supply_files,
            "copied_logs_scanned": len(copied),
            "categories": [
                "complete_compact_jws_or_bearer_token",
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
            "exact legal installed Status and Event HTTP admission with closed Schema-validated responses",
            "cryptographic request binding precedes durable run lookup and invalid signatures expose no run oracle",
            "default descriptor normalization exact cursor resume empty page and explicit 410 retention recovery",
            "repeated read token has zero mutation JTI or Provider-local durable write delta",
            "reproducible wheel dependency audit SPDX 2.3 SLSA v1 and BuildProvenance",
        ],
        "not_proven": [
            "malformed Status or Event HTTP behavior because authoritative OpenAPI 400 responses are absent",
            "Go adapter ProviderResolution production worker composition or Platform caller",
            "token issuer private-key custody or authoritative Platform parent facts",
            "CanonicalEvent production Safety Controller or cross-revision checkpoint compatibility",
            "aggregate runtime-core-v1 end-to-end reliability freeze security approval or production readiness",
        ],
    }
    matrix = evidence["runtime_core_case_matrix"]
    if len(matrix) != 17 or len({item["case_id"] for item in matrix}) != 17:
        raise AssertionError("a1.1.4 evidence must preserve 17 unique Suite cases")
    for value in (
        evidence["dependency_lock_sha256"],
        evidence["contract_manifest_digest"],
        evidence["runtime_suite"]["suite_digest"],
    ):
        if not isinstance(value, str) or not common.SHA256_DIGEST.fullmatch(value):
            raise AssertionError("a1.1.4 governed digest is invalid")
    encoded = (json.dumps(evidence, indent=2, sort_keys=True) + "\n").encode()
    prior._scan_evidence_bytes("read boundary evidence", encoded)
    arguments.output.write_bytes(encoded)


if __name__ == "__main__":
    main()
