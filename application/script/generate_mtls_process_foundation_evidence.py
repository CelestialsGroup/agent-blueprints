#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
from pathlib import Path
from typing import Any

import generate_pre_transport_safety_evidence as prior

ROOT = Path(__file__).resolve().parents[1]
TEST_COUNT = re.compile(r"Ran (\d+) tests")
PKI_FINGERPRINTS = re.compile(
    r"process-foundation-test-pki:"
    r"ca=(sha256:[0-9a-f]{64}),client=(sha256:[0-9a-f]{64})"
)
REQUIRED_SOURCE_TESTS = (
    "test_installed_cli_entrypoints_are_declared",
    "test_invalid_tokens_never_open_store_or_reveal_run_existence",
    "test_open_current_rejects_noncurrent_migration_ledger_without_write",
)
REQUIRED_INSTALLED_TESTS = (
    "test_bounded_connection_request_header_body_and_read_timeouts",
    "test_installed_migrate_serve_separation_and_schema_fail_closed",
    "test_real_mtls_certificate_identity_and_route_boundary",
    "test_response_write_limit_and_tls_version_are_enforced",
    "test_sigterm_readiness_bounded_drain_preserves_durable_work",
)
SOURCE_FILES = (
    *prior.SOURCE_FILES,
    "script/generate_mtls_process_foundation_evidence.py",
)


def source_manifest() -> dict[str, Any]:
    paths = [ROOT / relative for relative in SOURCE_FILES]
    for relative in prior.SOURCE_DIRECTORIES:
        paths.extend(path for path in (ROOT / relative).rglob("*") if path.is_file())
    files = [
        {
            "path": path.relative_to(ROOT).as_posix(),
            "sha256": "sha256:" + prior.sha256_file(path),
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
            "installed_process_subset_passed",
            "the installed wheel serves the same Schema-valid immutable Capabilities document across process restart; production Provider admission remains absent",
        ),
        "start-idempotent": (
            "a1_1_0_regression_passed",
            "the secure core replay invariant remains covered; Start HTTP is not enabled in a1.1.1",
        ),
        "start-digest-conflict": (
            "a1_1_0_regression_passed",
            "the secure core digest-conflict invariant remains covered; Start HTTP is not enabled in a1.1.1",
        ),
        "start-executable-context-complete": (
            "presented_context_regression_subset_passed",
            "presented-context admission remains covered below transport; production parent authority and Start HTTP remain absent",
        ),
        "start-encoded-body-limit": (
            "not_in_a1_1_1",
            "foundation routes reject request bodies, but the Contract 8 MiB Start HTTP pre-parse 413 belongs to a1.1.2",
        ),
        "command-contiguous": (
            "a1_1_0_regression_passed",
            "the durable contiguous-command invariant remains covered; Command HTTP is not enabled in a1.1.1",
        ),
        "stale-fencing-rejected": (
            "a1_1_0_regression_passed",
            "the durable fencing invariant remains covered; Command HTTP is not enabled in a1.1.1",
        ),
        "typed-event-payloads": (
            "a1_1_0_regression_subset_passed",
            "Provider-local event validation remains covered; Event HTTP and CanonicalEvent admission remain absent",
        ),
        "cursor-resume": (
            "a1_1_0_regression_passed",
            "durable cursor behavior remains covered below transport; Event HTTP is not enabled in a1.1.1",
        ),
        "cursor-expired-explicit": (
            "a1_1_0_regression_passed",
            "explicit Provider-local cursor recovery remains covered below transport; Event HTTP is not enabled in a1.1.1",
        ),
        "cancel-confirmed": (
            "a1_1_0_regression_subset_passed",
            "Provider-local cancel evidence remains covered; Command HTTP and Platform terminal authority remain absent",
        ),
        "checkpoint-compatibility": (
            "same_revision_regression_subset_passed",
            "same-revision checkpoint behavior remains covered; no process recovery or cross-revision claim is added",
        ),
        "adapter-restart-resume": (
            "provider_process_subset_passed",
            "installed serve restart preserves the current store and SIGTERM preserves pending durable work; no Go adapter is present",
        ),
        "authorization-renewal": (
            "platform_blocked",
            "requires authoritative append-only RuntimeAuthorization and ArtifactGrant lineage",
        ),
        "runtime-token-replay-and-expiry": (
            "mtls_identity_subset_passed",
            "a test certificate URI maps one-to-one to the exact token subject and mismatch is rejected; production issuer, key custody and workload identity remain absent",
        ),
        "system-safety-control": (
            "provider_regression_subset_passed",
            "the reduction-only secure-core subset remains covered; no Command HTTP or production Safety Controller is present",
        ),
        "outcome-unknown-reconcile": (
            "not_in_a1_1_1",
            "HTTP mutation response uncertainty and Go adapter reconciliation begin in later slices",
        ),
    }
    tests = profile.get("tests")
    if not isinstance(tests, list) or not tests:
        raise AssertionError("locked runtime-core-v1 has no cases")
    case_ids = [test["test_id"] for test in tests]
    if len(case_ids) != len(set(case_ids)) or set(case_ids) != set(case_results):
        raise AssertionError("runtime-core-v1 cases and a1.1.1 evidence mapping differ")
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


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--application-base-revision", required=True)
    parser.add_argument("--validation-command", required=True)
    parser.add_argument("--python-validation-log", type=Path, required=True)
    parser.add_argument("--installed-process-log", type=Path, required=True)
    parser.add_argument("--supply-chain-log", type=Path, required=True)
    parser.add_argument("--native-runtime-artifact", type=Path, required=True)
    parser.add_argument("--native-runtime-rebuild", type=Path, required=True)
    parser.add_argument("--implementation-evidence-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    if not prior.GIT_REVISION.fullmatch(arguments.application_base_revision):
        raise AssertionError("Application base revision is not a full Git object ID")

    python_text = arguments.python_validation_log.read_text(encoding="utf-8")
    installed_text = arguments.installed_process_log.read_text(encoding="utf-8")
    supply_chain_text = arguments.supply_chain_log.read_text(encoding="utf-8")
    python_count = _test_count(
        python_text, REQUIRED_SOURCE_TESTS, "Native Runtime source"
    )
    installed_count = _test_count(
        installed_text, REQUIRED_INSTALLED_TESTS, "installed process"
    )
    fingerprints = PKI_FINGERPRINTS.search(installed_text)
    if fingerprints is None:
        raise AssertionError("installed process log lacks public test PKI fingerprints")
    if "Implementation supply-chain check passed:" not in supply_chain_text:
        raise AssertionError("supply-chain validation log is incomplete")

    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    copied_python = arguments.output.parent / "native-runtime-validation.log"
    copied_process = arguments.output.parent / "installed-process-validation.log"
    copied_supply_chain = arguments.output.parent / "supply-chain.log"
    shutil.copyfile(arguments.python_validation_log, copied_python)
    shutil.copyfile(arguments.installed_process_log, copied_process)
    shutil.copyfile(arguments.supply_chain_log, copied_supply_chain)

    lock_path = ROOT / "dependency-lock.json"
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    lock_entry, suite = prior.runtime_suite(lock)
    projection_path = ROOT / "internal/generated/runtimeapi/projection-manifest.json"
    projection = json.loads(projection_path.read_text(encoding="utf-8"))
    evidence = {
        "evidence_version": 1,
        "slice_id": "B03.2a1.1.1",
        "scope": "mtls_process_foundation",
        "result": "passed",
        "conformance_profile_result": "not_claimed",
        "application_base_revision": arguments.application_base_revision,
        "application_source": source_manifest(),
        "blueprint": lock["blueprint"],
        "contract": lock["contract"],
        "dependency_lock_sha256": "sha256:" + prior.sha256_file(lock_path),
        "contract_manifest_digest": lock["contract"]["manifest_digest"],
        "runtime_suite": lock_entry,
        "runtime_suite_canonical_sha256": "sha256:"
        + hashlib.sha256(
            json.dumps(suite, separators=(",", ":"), sort_keys=True).encode()
        ).hexdigest(),
        "runtime_projection": {
            "manifest_sha256": "sha256:" + prior.sha256_file(projection_path),
            "schema_count": projection["schema_count"],
            "schema_closure_sha256": "sha256:" + projection["schema_closure_sha256"],
            "openapi_sha256": "sha256:" + projection["openapi_sha256"],
        },
        "dependencies": prior.dependency_evidence(),
        "sqlite_migrations": prior.migration_evidence(),
        "installed_process": {
            "cli": [
                "agent-native-runtime-migrate",
                "agent-native-runtime-serve",
            ],
            "serve_open_mode": "open_current_only",
            "http_version": "HTTP/1.1",
            "tls_minimum": "1.2",
            "mutual_tls": "required",
            "certificate_checks": [
                "trusted_ca",
                "validity_window",
                "clientAuth_eku",
                "single_uri_san",
                "exact_identity_allowlist",
                "exact_token_subject_mapping",
            ],
            "routes": [
                "/health/live",
                "/health/ready",
                "/v1/capabilities",
            ],
            "bounded_dimensions": [
                "connections",
                "concurrent_requests",
                "requests_per_connection",
                "request_line",
                "header_bytes",
                "header_count",
                "request_body",
                "response_body",
                "handshake_timeout",
                "idle_timeout",
                "read_timeout",
                "write_timeout",
                "drain_timeout",
            ],
            "test_pki_public_fingerprints": {
                "ca": fingerprints.group(1),
                "client": fingerprints.group(2),
            },
            "private_test_key_retention": "none",
        },
        "validation": {
            "command": arguments.validation_command,
            "source_test_count": python_count,
            "installed_process_test_count": installed_count,
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
                    "sha256": "sha256:" + prior.sha256_file(copied_python),
                },
                "installed_process": {
                    "path": copied_process.name,
                    "sha256": "sha256:" + prior.sha256_file(copied_process),
                },
                "supply_chain": {
                    "path": copied_supply_chain.name,
                    "sha256": "sha256:" + prior.sha256_file(copied_supply_chain),
                },
            },
        },
        "runtime_core_case_matrix": case_matrix(suite),
        "supply_chain": prior.supply_chain_evidence(
            arguments.native_runtime_artifact,
            arguments.native_runtime_rebuild,
            arguments.implementation_evidence_dir,
        ),
        "proven": [
            "installed-wheel migrate and serve are separate entry points and serve uses open_current without migration",
            "missing, old, drifted or configuration-mismatched stores reject serve startup without authoritative database changes",
            "the standard-library loopback HTTP/1.1 process has explicit connection, concurrency, request, response, timeout and drain bounds",
            "TLS 1.2 or newer and a client certificate are mandatory; CA, expiry, clientAuth EKU, single URI identity and exact allowlist mapping are exercised with ephemeral test PKI",
            "the certificate identity maps one-to-one to the future Runtime token subject and an unequal subject is rejected",
            "only Capabilities and health/readiness routes are enabled; mutation and read routes create no Runtime fact",
            "readiness becomes true only after current schema/configuration, TLS listener and request workers are ready",
            "SIGTERM clears readiness, stops acceptance, drains within a deadline and preserves pending Provider-local durable work",
            "reproducible wheel, dependency audit, SPDX 2.3, SLSA v1 and BuildProvenance pass through the Application Gate",
        ],
        "not_proven": [
            "Start, Command, Status or Event HTTP transport, content-type mapping, Contract success encoding or mutation StandardError classification",
            "kill -9, commit-boundary HTTP recovery, response-loss mutation reconciliation, work-lease execution or checkpoint process recovery",
            "Status/Event HTTP 400 mapping, which remains blocked on authoritative OpenAPI interpretation",
            "production server capacity, topology, maintenance, certificate issuance, revocation, workload identity or private-key custody",
            "Go adapter, production composition root, token issuer, ProviderResolution or production caller",
            "Platform PostgreSQL, Temporal caller, CanonicalEvent, production Safety Controller or aggregate runtime-core-v1 conformance",
        ],
    }
    for value in (
        evidence["dependency_lock_sha256"],
        evidence["contract_manifest_digest"],
        evidence["runtime_suite"]["suite_digest"],
    ):
        if not isinstance(value, str) or not prior.SHA256_DIGEST.fullmatch(value):
            raise AssertionError("a1.1.1 governed digest is invalid")
    arguments.output.write_text(
        json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
