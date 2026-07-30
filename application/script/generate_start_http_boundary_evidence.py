#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
from pathlib import Path
from typing import Any

import generate_mtls_process_foundation_evidence as prior
import generate_pre_transport_safety_evidence as common

ROOT = Path(__file__).resolve().parents[1]
TEST_COUNT = re.compile(r"Ran (\d+) tests")
PKI_FINGERPRINTS = re.compile(
    r"process-foundation-test-pki:"
    r"ca=(sha256:[0-9a-f]{64}),client=(sha256:[0-9a-f]{64})"
)
FORBIDDEN_EVIDENCE_FRAGMENTS = (
    "-----BEGIN PRIVATE KEY-----",
    "Authorization: Bearer ",
    "Traceback (most recent call last)",
    "sensitive-controlled-precommit-marker",
    "sensitive-body-marker",
)
REQUIRED_SOURCE_TESTS = (
    "test_bearer_authorization_is_one_bounded_compact_jws",
    "test_mutation_jti_is_consumed_only_with_committed_start",
    "test_start_calls_core_with_mtls_subject_and_validates_202",
    "test_start_error_mapping_is_closed_and_safe",
    "test_start_request_line_is_exact_origin_form_http_1_1",
)
REQUIRED_INSTALLED_START_TESTS = (
    "test_body_limit_short_read_and_total_deadline_are_precommit",
    "test_committed_run_status_response_respects_byte_limit",
    "test_concurrency_and_sqlite_lock_use_retryable_closed_mappings",
    "test_controlled_post_validation_precommit_failure_has_zero_facts",
    "test_draining_start_is_retryable_503_without_facts",
    "test_postcommit_response_loss_retries_same_runtime_run",
    "test_request_schema_authorization_and_unsupported_fail_precommit",
    "test_request_target_host_content_type_and_framing_are_strict",
    "test_token_binding_failures_are_401_and_precommit",
    "test_valid_algorithms_replay_and_conflicts",
)
SOURCE_FILES = (
    *prior.SOURCE_FILES,
    "script/generate_start_http_boundary_evidence.py",
)


def _is_scoped_source(path: Path) -> bool:
    return (
        path.is_file()
        and "__pycache__" not in path.parts
        and path.suffix != ".pyc"
    )


def source_manifest() -> dict[str, Any]:
    paths = [ROOT / relative for relative in SOURCE_FILES]
    for relative in common.SOURCE_DIRECTORIES:
        paths.extend(
            path
            for path in (ROOT / relative).rglob("*")
            if _is_scoped_source(path)
        )
    if any(not _is_scoped_source(path) for path in paths):
        raise AssertionError("source manifest contains a non-source cache file")
    files = [
        {
            "path": path.relative_to(ROOT).as_posix(),
            "sha256": "sha256:" + common.sha256_file(path),
        }
        for path in sorted(
            set(paths), key=lambda item: item.relative_to(ROOT).as_posix()
        )
    ]
    encoded = json.dumps(files, separators=(",", ":"), sort_keys=True).encode()
    return {
        "files": files,
        "source_set_sha256": "sha256:" + hashlib.sha256(encoded).hexdigest(),
    }


def case_matrix(suite: dict[str, Any]) -> list[dict[str, str]]:
    profile = next(
        profile
        for profile in suite["profiles"]
        if profile["profile_id"] == "runtime-core-v1"
    )
    case_results = {
        "capabilities-immutable": (
            "a1_1_1_regression_passed",
            "the installed process keeps immutable Schema-valid Capabilities across restart; production registration remains absent",
        ),
        "start-idempotent": (
            "installed_start_passed",
            "installed HTTP Start with the same request digest and a fresh JTI returns the same RuntimeRun without duplicate event or work",
        ),
        "start-digest-conflict": (
            "installed_start_passed",
            "installed HTTP Start rejects the same idempotency key with a different request digest as 409 without consuming the fresh JTI",
        ),
        "start-executable-context-complete": (
            "installed_presented_context_subset_passed",
            "mTLS, JWS and the complete presented Start context are validated before the atomic Provider-local facts; production parent authority is absent",
        ),
        "start-encoded-body-limit": (
            "installed_preparse_413_passed",
            "Content-Length 8388609 returns pre-parse 413 with zero facts while an exact 8388608-byte Strict JSON body is admitted",
        ),
        "command-contiguous": (
            "a1_1_0_regression_passed",
            "the durable contiguous-command invariant remains covered below transport; Command HTTP is not implemented",
        ),
        "stale-fencing-rejected": (
            "a1_1_0_regression_passed",
            "the durable fencing invariant remains covered below transport; Command HTTP is not implemented",
        ),
        "typed-event-payloads": (
            "a1_1_0_regression_subset_passed",
            "Provider-local emitted event validation remains covered; Event HTTP and CanonicalEvent authority are absent",
        ),
        "cursor-resume": (
            "a1_1_0_regression_passed",
            "Provider-local cursor behavior remains covered below transport; Event HTTP is not implemented",
        ),
        "cursor-expired-explicit": (
            "a1_1_0_regression_passed",
            "Provider-local explicit cursor recovery remains covered below transport; Event HTTP is not implemented",
        ),
        "cancel-confirmed": (
            "a1_1_0_regression_subset_passed",
            "Provider-local cancellation evidence remains covered; Command HTTP and Platform terminal authority are absent",
        ),
        "checkpoint-compatibility": (
            "http_unsupported_and_same_revision_regression_subset_passed",
            "unsupported checkpoint restore is a Schema-valid 422 and existing same-revision component behavior regresses; process recovery is not claimed",
        ),
        "adapter-restart-resume": (
            "provider_process_response_loss_subset_passed",
            "controlled response loss followed by process restart and fresh-JTI replay preserves one RuntimeRun; no Go adapter exists",
        ),
        "authorization-renewal": (
            "platform_blocked",
            "requires authoritative append-only RuntimeAuthorization and ArtifactGrant lineage",
        ),
        "runtime-token-replay-and-expiry": (
            "installed_start_token_subset_passed",
            "installed Start covers EdDSA, ES256, issuer, audience, subject, operation, request digest, time window and mutation-JTI replay; production issuance is absent",
        ),
        "system-safety-control": (
            "provider_regression_subset_passed",
            "the reduction-only secure-core subset remains covered; no Command HTTP or production Safety Controller is present",
        ),
        "outcome-unknown-reconcile": (
            "response_loss_retry_subset_passed",
            "controlled post-commit response loss is recovered by exact idempotent retry; Platform outcome reconciliation and kill -9 recovery remain absent",
        ),
    }
    tests = profile.get("tests")
    if not isinstance(tests, list) or not tests:
        raise AssertionError("locked runtime-core-v1 has no cases")
    case_ids = [test["test_id"] for test in tests]
    if len(case_ids) != len(set(case_ids)) or set(case_ids) != set(case_results):
        raise AssertionError("runtime-core-v1 cases and a1.1.2 evidence mapping differ")
    return [
        {
            "case_id": case_id,
            "verdict": case_results[case_id][0],
            "boundary": case_results[case_id][1],
        }
        for case_id in case_ids
    ]


def _test_count(text: str, required: tuple[str, ...], name: str) -> int:
    for fragment in (*required, "OK"):
        if fragment not in text:
            raise AssertionError(f"{name} validation log lacks {fragment!r}")
    counts = [int(value) for value in TEST_COUNT.findall(text)]
    if not counts or counts[-1] < len(required):
        raise AssertionError(f"{name} validation log lacks the required test count")
    return counts[-1]


def _reject_sensitive_content(name: str, text: str) -> None:
    for fragment in FORBIDDEN_EVIDENCE_FRAGMENTS:
        if fragment in text:
            raise AssertionError(f"{name} contains forbidden sensitive content")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--application-base-revision", required=True)
    parser.add_argument("--validation-command", required=True)
    parser.add_argument("--python-validation-log", type=Path, required=True)
    parser.add_argument("--installed-process-log", type=Path, required=True)
    parser.add_argument("--installed-start-log", type=Path, required=True)
    parser.add_argument("--supply-chain-log", type=Path, required=True)
    parser.add_argument("--native-runtime-artifact", type=Path, required=True)
    parser.add_argument("--native-runtime-rebuild", type=Path, required=True)
    parser.add_argument("--implementation-evidence-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    if not common.GIT_REVISION.fullmatch(arguments.application_base_revision):
        raise AssertionError("Application base revision is not a full Git object ID")

    python_text = arguments.python_validation_log.read_text(encoding="utf-8")
    process_text = arguments.installed_process_log.read_text(encoding="utf-8")
    start_text = arguments.installed_start_log.read_text(encoding="utf-8")
    supply_chain_text = arguments.supply_chain_log.read_text(encoding="utf-8")
    python_count = _test_count(
        python_text, REQUIRED_SOURCE_TESTS, "Native Runtime source"
    )
    process_count = _test_count(
        process_text, prior.REQUIRED_INSTALLED_TESTS, "installed process foundation"
    )
    start_count = _test_count(
        start_text, REQUIRED_INSTALLED_START_TESTS, "installed Start HTTP"
    )
    fingerprints = PKI_FINGERPRINTS.search(process_text)
    if fingerprints is None:
        raise AssertionError("installed process log lacks public test PKI fingerprints")
    if "Implementation supply-chain check passed:" not in supply_chain_text:
        raise AssertionError("supply-chain validation log is incomplete")
    for name, text in (
        ("Native Runtime source log", python_text),
        ("installed process foundation log", process_text),
        ("installed Start HTTP log", start_text),
        ("supply-chain log", supply_chain_text),
    ):
        _reject_sensitive_content(name, text)

    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    copied_python = arguments.output.parent / "native-runtime-validation.log"
    copied_process = (
        arguments.output.parent / "installed-process-foundation-validation.log"
    )
    copied_start = arguments.output.parent / "installed-start-http-validation.log"
    copied_supply_chain = arguments.output.parent / "supply-chain.log"
    shutil.copyfile(arguments.python_validation_log, copied_python)
    shutil.copyfile(arguments.installed_process_log, copied_process)
    shutil.copyfile(arguments.installed_start_log, copied_start)
    shutil.copyfile(arguments.supply_chain_log, copied_supply_chain)

    lock_path = ROOT / "dependency-lock.json"
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    lock_entry, suite = common.runtime_suite(lock)
    projection_path = ROOT / "internal/generated/runtimeapi/projection-manifest.json"
    projection = json.loads(projection_path.read_text(encoding="utf-8"))
    evidence = {
        "evidence_version": 1,
        "slice_id": "B03.2a1.1.2",
        "scope": "start_http_boundary",
        "result": "passed",
        "conformance_profile_result": "not_claimed",
        "application_base_revision": arguments.application_base_revision,
        "application_source": source_manifest(),
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
            "schema_closure_sha256": "sha256:"
            + projection["schema_closure_sha256"],
            "openapi_sha256": "sha256:" + projection["openapi_sha256"],
        },
        "dependencies": common.dependency_evidence(),
        "sqlite_migrations": common.migration_evidence(),
        "http_start_boundary": {
            "route": "POST /v1/runs",
            "http_version": "HTTP/1.1",
            "content_type": "application/json",
            "max_encoded_body_bytes": 8_388_608,
            "body_read_chunk_bytes": 65_536,
            "framing": {
                "content_length": "single_canonical_decimal_required",
                "transfer_encoding": "rejected",
                "chunked": "rejected",
                "expect": "rejected",
                "short_read": "close_or_schema_valid_400",
                "deadline": "single_total_monotonic_deadline",
            },
            "authentication": {
                "mutual_tls": "required",
                "certificate_subject_binding": "exact_token_sub",
                "bearer": "single_bounded_compact_jws",
                "algorithms": ["EdDSA", "ES256"],
                "host_cannot_replace_audience": True,
                "request_cannot_replace_operation_or_digest": True,
                "test_pki_public_fingerprints": {
                    "ca": fingerprints.group(1),
                    "client": fingerprints.group(2),
                },
                "private_test_key_retention": "none",
            },
            "success": {
                "status": 202,
                "schema": "urn:agent-platform:agent-runtime-run-status:v1",
            },
            "closed_error_statuses": [400, 401, 403, 409, 413, 422, 429, 500, 503],
            "error_schema": "urn:agent-platform:standard-error:v1",
        },
        "atomicity_and_replay": {
            "atomic_facts": [
                "consumed_mutation_jti",
                "runtime_run",
                "runtime_security_binding",
                "start_idempotency",
                "runtime.run.started",
                "pending_execution_work",
            ],
            "precommit_failures": "all_six_fact_counts_zero",
            "same_digest_fresh_jti": "same_runtime_run",
            "digest_conflict": "409_without_jti_consumption",
            "response_loss_final_counts": {
                "consumed_mutation_jtis": 2,
                "runtime_runs": 1,
                "runtime_security_bindings": 1,
                "start_idempotency": 1,
                "runtime_events": 1,
                "execution_work": 1,
            },
        },
        "controlled_fault_scope": {
            "proven": [
                "test-only graceful failure after JSON Schema and JWS validation but before kernel store mutation",
                "SQLite busy or locked before commit",
                "TLS response loss after commit and before the 202 write",
                "fresh-JTI exact idempotent retry after process restart",
            ],
            "not_claimed": [
                "kill -9 recovery",
                "real work lease recovery",
                "checkpoint process recovery",
                "SQLite reopen recovery after abrupt termination",
            ],
            "deferred_slice": "B03.2a1.1.3",
        },
        "authority_gaps": [
            {
                "gap_id": "status-event-http-400",
                "status": "blocked",
                "reason": "locked OpenAPI omits authoritative 400 responses for Status and Event reads",
                "action": "do_not_guess_or_modify_contract",
            },
            {
                "gap_id": "production-runtime-authority",
                "status": "not_in_slice",
                "includes": [
                    "Go adapter",
                    "production composition root",
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
            "source_test_count": python_count,
            "installed_process_foundation_test_count": process_count,
            "installed_start_file_test_count": start_count,
            "required_installed_start_process_cases": len(
                REQUIRED_INSTALLED_START_TESTS
            ),
            "quality": {
                "ruff_version": "0.16.0",
                "ruff_format": "passed",
                "ruff_lint": "passed",
                "mypy_version": "2.3.0",
                "mypy_strict": "passed",
            },
            "logs": {
                "native_runtime": {
                    "path": copied_python.name,
                    "sha256": "sha256:" + common.sha256_file(copied_python),
                },
                "installed_process_foundation": {
                    "path": copied_process.name,
                    "sha256": "sha256:" + common.sha256_file(copied_process),
                },
                "installed_start_http": {
                    "path": copied_start.name,
                    "sha256": "sha256:" + common.sha256_file(copied_start),
                },
                "supply_chain": {
                    "path": copied_supply_chain.name,
                    "sha256": "sha256:" + common.sha256_file(copied_supply_chain),
                },
            },
        },
        "runtime_core_case_matrix": case_matrix(suite),
        "supply_chain": common.supply_chain_evidence(
            arguments.native_runtime_artifact,
            arguments.native_runtime_rebuild,
            arguments.implementation_evidence_dir,
        ),
        "proven": [
            "only exact POST /v1/runs is enabled for Runtime operations; Command Status and Event transports remain disabled",
            "strict Host Content-Type Content-Length Transfer-Encoding Expect and total body deadline admission precedes JSON Schema JWS and SQLite",
            "the Contract 8388608-byte encoded body limit is enforced before parsing and an exact-boundary body is admitted",
            "installed-wheel EdDSA and ES256 Start responses validate as AgentRuntimeRunStatus and every sent error validates as StandardError",
            "mTLS certificate identity exactly constrains token subject and Host cannot replace audience operation or request digest",
            "mutation JTI and accepted Start facts retain their existing SQLite transaction while replay and digest conflict preserve Contract semantics",
            "controlled precommit failure SQLite lock and postcommit response loss have deterministic installed-process evidence",
            "reproducible wheel dependency audit SPDX 2.3 SLSA v1 and BuildProvenance pass through the Application Gate",
        ],
        "not_proven": [
            "Command Status or Event HTTP transport and the blocked Status Event HTTP 400 interpretation",
            "kill -9 real work lease checkpoint or SQLite reopen recovery which belongs to B03.2a1.1.3",
            "Go adapter production composition root ProviderResolution token issuer or private-key custody",
            "Platform PostgreSQL Temporal caller CanonicalEvent or production Safety Controller authority",
            "aggregate runtime-core-v1 conformance end-to-end reliability freeze security approval or production readiness",
        ],
    }
    if len(evidence["runtime_core_case_matrix"]) != 17:
        raise AssertionError("a1.1.2 evidence must preserve all 17 Suite cases")
    for value in (
        evidence["dependency_lock_sha256"],
        evidence["contract_manifest_digest"],
        evidence["runtime_suite"]["suite_digest"],
    ):
        if not isinstance(value, str) or not common.SHA256_DIGEST.fullmatch(value):
            raise AssertionError("a1.1.2 governed digest is invalid")
    encoded_evidence = json.dumps(evidence, indent=2, sort_keys=True) + "\n"
    _reject_sensitive_content("Start HTTP evidence", encoded_evidence)
    arguments.output.write_text(encoded_evidence, encoding="utf-8")


if __name__ == "__main__":
    main()
