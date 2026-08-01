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

import generate_command_recovery_boundary_evidence as native
import generate_http_adapter_evidence as adapter
import generate_pre_transport_safety_evidence as common

ROOT = Path(__file__).resolve().parents[1]
CONTRACT_ROOT = Path(
    os.environ.get("AGENT_CONTRACT_ROOT", ROOT.parent / "contract")
).resolve()
REQUIRED_TESTS = (
    "TestInstalledCrossLanguageFiveOperations",
    "TestInstalledCrossLanguageClosedFailures",
)
EVIDENCE_MARKERS = (
    "installed-wheel-process-ed25519-mtls-http11-sqlite",
    "five-operation-happy-path",
    "closed-known-failures",
)
SOURCE_FILES = (
    "doc/plan/B03.2a2.2.0-installed-cross-language-five-operation-component.md",
    "runtime/native/test/installed_cross_language_fixture.py",
    "script/generate_installed_cross_language_evidence.py",
)


def source_paths() -> tuple[Path, ...]:
    paths = set(native.source_paths()) | set(adapter.source_paths())
    paths.update(ROOT / relative for relative in SOURCE_FILES)
    if any(
        not path.is_file() or "__pycache__" in path.parts or path.suffix == ".pyc"
        for path in paths
    ):
        raise AssertionError("installed cross-language source manifest is invalid")
    return tuple(sorted(paths, key=lambda path: path.relative_to(ROOT).as_posix()))


def source_manifest(paths: tuple[Path, ...]) -> dict[str, Any]:
    files = [
        {
            "path": path.relative_to(ROOT).as_posix(),
            "sha256": "sha256:" + common.sha256_file(path),
        }
        for path in paths
    ]
    canonical = json.dumps(files, separators=(",", ":"), sort_keys=True).encode()
    return {
        "files": files,
        "source_set_sha256": "sha256:" + hashlib.sha256(canonical).hexdigest(),
        "cache_policy": {
            "forbidden": ["__pycache__", "*.pyc"],
            "observed_forbidden_count": 0,
            "failure_mode": "reject_generation",
        },
    }


def parse_validation_log(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    native._scan_evidence_bytes(
        "installed cross-language validation log", text.encode()
    )
    for test in REQUIRED_TESTS:
        if len(re.findall(rf"^=== RUN\s+{re.escape(test)}$", text, re.MULTILINE)) != 2:
            raise AssertionError(f"installed cross-language test count differs: {test}")
        if len(re.findall(rf"^--- PASS: {re.escape(test)} ", text, re.MULTILINE)) != 2:
            raise AssertionError(f"installed cross-language pass count differs: {test}")
    markers: list[str] = []
    for marker in EVIDENCE_MARKERS:
        if text.count(f"installed-cross-language-evidence:{marker}:passed") != 2:
            raise AssertionError(
                f"installed cross-language evidence marker differs: {marker}"
            )
        markers.append(marker)
    for static_marker in (
        "installed-cross-language-module-files-base-revision-zero-diff:passed",
        "installed-cross-language-production-importers:none",
        "installed-cross-language-architecture:linux/arm64",
        "installed-cross-language-wheel-entrypoints:installed",
        "installed-cross-language-normal:passed",
        "installed-cross-language-race:passed",
    ):
        if text.count(static_marker) != 1:
            raise AssertionError(
                f"installed cross-language static marker differs: {static_marker}"
            )
    if len(re.findall(r"^PASS$", text, re.MULTILINE)) != 2:
        raise AssertionError("installed cross-language normal/Race summaries differ")
    return {
        "normal_test_count": len(REQUIRED_TESTS),
        "race_test_count": len(REQUIRED_TESTS),
        "required_tests": list(REQUIRED_TESTS),
        "dynamic_markers": markers,
        "architecture": "linux/arm64",
        "production_importers": [],
    }


def log_evidence(path: Path) -> dict[str, Any]:
    return {
        "path": path.name,
        "sha256": "sha256:" + common.sha256_file(path),
        "size_bytes": path.stat().st_size,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--application-base-revision", required=True)
    parser.add_argument("--validation-command", required=True)
    parser.add_argument("--installed-cross-language-log", type=Path, required=True)
    parser.add_argument("--supply-chain-log", type=Path, required=True)
    parser.add_argument("--native-runtime-artifact", type=Path, required=True)
    parser.add_argument("--native-runtime-rebuild", type=Path, required=True)
    parser.add_argument("--implementation-evidence-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    if not common.GIT_REVISION.fullmatch(arguments.application_base_revision):
        raise AssertionError("Application base revision is not a full Git object ID")

    validation = parse_validation_log(arguments.installed_cross_language_log)
    supply_chain_text = arguments.supply_chain_log.read_text(encoding="utf-8")
    if "Implementation supply-chain check passed:" not in supply_chain_text:
        raise AssertionError("supply-chain validation log is incomplete")
    native._scan_evidence_bytes("supply-chain log", supply_chain_text.encode())

    paths = source_paths()
    source_scan_count = native._scan_source_secrets(paths)
    wheel_member_count = native._scan_wheel(arguments.native_runtime_artifact)
    implementation_supply_files = 0
    for path in sorted(arguments.implementation_evidence_dir.rglob("*")):
        if path.is_file():
            native._scan_evidence_bytes(
                f"implementation evidence {path.name}", path.read_bytes()
            )
            implementation_supply_files += 1

    lock_path = ROOT / "dependency-lock.json"
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    suite_lock, suite = common.runtime_suite(lock)
    profile = next(
        item for item in suite["profiles"] if item["profile_id"] == "runtime-core-v1"
    )
    tests = profile.get("tests")
    if not isinstance(tests, list):
        raise TypeError("runtime-core-v1 cases are absent")
    case_ids = [item["test_id"] for item in tests]
    if len(case_ids) != 17 or len(case_ids) != len(set(case_ids)):
        raise AssertionError("runtime-core-v1 case count or uniqueness changed")

    projection_path = ROOT / "internal/generated/runtimeapi/projection-manifest.json"
    projection = json.loads(projection_path.read_text(encoding="utf-8"))
    predecessor_path = (
        ROOT / "build/evidence/b03.2a2.1/strict-unwired-http-adapter.json"
    )
    predecessor = json.loads(predecessor_path.read_text(encoding="utf-8"))
    if (
        predecessor.get("result") != "passed"
        or predecessor.get("maturity") != "strict_unwired_http_adapter_component"
        or predecessor.get("conformance_profile_result") != "not_claimed"
    ):
        raise AssertionError("a2.1 predecessor evidence boundary differs")

    registry_path = CONTRACT_ROOT / "event-types/agent-runtime-core-v1.json"
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    registry_digest = registry.get("registry_digest")
    if not isinstance(registry_digest, str) or not registry_digest.startswith(
        "sha256:"
    ):
        raise AssertionError("Runtime Event Registry digest is invalid")
    registry_resource_sha256 = "sha256:" + common.sha256_file(registry_path)
    if registry_resource_sha256 == registry_digest:
        raise AssertionError("Registry resource SHA and internal digest were conflated")

    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    copied_logs = {
        "installed_cross_language": arguments.output.parent
        / "installed-cross-language-validation.log",
        "supply_chain": arguments.output.parent / "supply-chain.log",
    }
    for source, target in (
        (
            arguments.installed_cross_language_log,
            copied_logs["installed_cross_language"],
        ),
        (arguments.supply_chain_log, copied_logs["supply_chain"]),
    ):
        shutil.copyfile(source, target)
        native._scan_evidence_bytes(f"copied log {target.name}", target.read_bytes())

    toolchain = adapter.load_toolchain()
    evidence: dict[str, Any] = {
        "evidence_version": 1,
        "slice_id": "B03.2a2.2.0",
        "scope": "installed_cross_language_five_operation_component",
        "result": "passed",
        "maturity": "installed_cross_language_five_operation_component",
        "conformance_profile_result": "not_claimed",
        "application_base_revision": arguments.application_base_revision,
        "application_source": source_manifest(paths),
        "blueprint": lock["blueprint"],
        "contract": lock["contract"],
        "dependency_lock_sha256": "sha256:" + common.sha256_file(lock_path),
        "contract_manifest_digest": lock["contract"]["manifest_digest"],
        "runtime_suite": suite_lock,
        "runtime_suite_canonical_sha256": "sha256:"
        + hashlib.sha256(
            json.dumps(suite, separators=(",", ":"), sort_keys=True).encode()
        ).hexdigest(),
        "runtime_suite_case_inventory": [
            {
                "case_id": case_id,
                "status": "not_evaluated_in_a2_2_0",
                "planned_closure": "B03.2a2.3",
            }
            for case_id in case_ids
        ],
        "runtime_projection": {
            "manifest_sha256": "sha256:" + common.sha256_file(projection_path),
            "schema_count": projection["schema_count"],
            "schema_closure_sha256": "sha256:" + projection["schema_closure_sha256"],
            "openapi_sha256": "sha256:" + projection["openapi_sha256"],
        },
        "predecessor_evidence": {
            "path": predecessor_path.relative_to(ROOT).as_posix(),
            "sha256": "sha256:" + common.sha256_file(predecessor_path),
            "result": predecessor["result"],
            "maturity": predecessor["maturity"],
            "conformance_profile_result": predecessor["conformance_profile_result"],
        },
        "installed_component": {
            "operations": [
                "capabilities",
                "start",
                "read_status",
                "submit_command",
                "read_events",
            ],
            "go_adapter": "harness_only_existing_httpadapter",
            "native_runtime": "installed_wheel_subprocess",
            "entrypoints": [
                "agent-native-runtime-migrate",
                "agent-native-runtime-serve",
            ],
            "migration": "explicit_ephemeral_store_only",
            "serve_open_mode": "open_current_only",
            "network": {
                "loopback_socket": True,
                "http_version": "HTTP/1.1",
                "mutual_tls": "mandatory",
                "certificate_algorithm": "Ed25519",
                "minimum_tls": "1.2",
                "client_auth_eku": True,
                "single_uri_san_subject_binding": True,
            },
            "sqlite": "real_ephemeral_provider_local_file",
            "start_and_command_dispatch": "once_no_internal_retry",
            "closed_failures": [
                "authentication_rejected",
                "not_found",
                "protocol_conflict",
            ],
            "production_composition_present": False,
            "source_import_as_runtime": False,
        },
        "event_registry": {
            "path": registry_path.relative_to(CONTRACT_ROOT).as_posix(),
            "resource_sha256": registry_resource_sha256,
            "registry_digest": registry_digest,
            "resource_sha_and_internal_digest_are_distinct": True,
        },
        "authority_gaps": [
            {
                "gap_id": "status-event-http-400",
                "status": "blocked",
                "machine_readable": True,
                "reason": "locked OpenAPI omits authoritative 400 responses for Status and Event reads",
                "action": "map_to_invalid_response_and_do_not_modify_contract",
            },
            {
                "gap_id": "read-http-429-authority",
                "status": "blocked",
                "machine_readable": True,
                "reason": "locked read operations omit 429",
                "action": "map_to_invalid_response_and_do_not_guess",
            },
            {
                "gap_id": "fresh-token-issuer-and-durable-reconciliation-caller",
                "status": "blocked",
            },
            {
                "gap_id": "response-loss-restart-reconciliation-mechanics",
                "status": "not_in_slice",
                "planned_slice": "B03.2a2.2.1",
            },
            {
                "gap_id": "provider-resolution-production-tls-and-identity",
                "status": "not_in_slice",
                "planned_slice": "B03.2b/B03.2c",
            },
            {
                "gap_id": "platform-parents-canonical-event-safety-controller",
                "status": "not_in_slice",
            },
            {
                "gap_id": "postgresql-temporal-production-composition",
                "status": "not_in_slice",
                "planned_slice": "B03.2b/B03.2c",
            },
            {
                "gap_id": "aggregate-runtime-core-v1",
                "status": "not_claimed",
                "planned_slice": "B03.2a2.3",
            },
        ],
        "validation": {
            "command": arguments.validation_command,
            **validation,
            "logs": {key: log_evidence(path) for key, path in copied_logs.items()},
        },
        "supply_chain": {
            **common.supply_chain_evidence(
                arguments.native_runtime_artifact,
                arguments.native_runtime_rebuild,
                arguments.implementation_evidence_dir,
            ),
            "go_version": toolchain["GO_VERSION"],
            "go_toolchain_image": toolchain["GO_TOOLCHAIN_IMAGE"],
            "python_version": toolchain["PYTHON_VERSION"],
            "python_toolchain_image": toolchain["PYTHON_TOOLCHAIN_IMAGE"],
            "uv_version": toolchain["UV_VERSION"],
            "uv_binary_image": toolchain["UV_BINARY_IMAGE"],
            "architecture": "linux/arm64",
            "new_dependencies": [],
            "production_importers": [],
        },
        "sensitive_scan": {
            "result": "passed",
            "source_files_scanned": source_scan_count,
            "wheel_members_scanned": wheel_member_count,
            "implementation_supply_chain_files_scanned": (implementation_supply_files),
            "copied_logs_scanned": len(copied_logs),
            "categories": [
                "complete_compact_jws",
                "authorization_bearer_value",
                "request_document_content",
                "private_key_pem_block",
                "sqlite_or_checkpoint_content",
                "captured_traceback",
            ],
        },
        "data_retention": {
            "durable_writes": "ephemeral_provider_local_sqlite_only",
            "migrations": "explicit_up_in_ephemeral_temp_root",
            "token_document_private_key_persistence": "temporary_test_root_only",
            "evidence_retains": "hashes_public_cert_fingerprint_counts_and_redacted_logs_only",
            "existing_sqlite_postgresql_temporal_facts": "unchanged_forward_only",
            "rollback": "remove_test_fixture_generator_gate_docs_and_ignored_evidence_only",
        },
        "proven": [
            "Go adapter calls the real installed Native Runtime wheel process for all five operations",
            "real Ed25519 CA server and client certificates enforce mutual TLS over loopback HTTP/1.1 sockets",
            "explicit installed migration and open_current serve operate on a real ephemeral Provider-local SQLite file",
            "happy path binds Provider Runtime invocation digest fencing Event Registry order and cursor responses",
            "real authentication not-found and protocol-conflict failures remain closed and Start Command are not retried",
            "normal and Race test binaries pass without a production importer or new dependency",
        ],
        "not_proven": [
            "response loss timeout reset process restart SQLite reopen or fresh-read reconciliation mechanics",
            "production fresh-token issuer private-key custody durable reconciliation caller or ProviderResolution",
            "Status Event HTTP 400 read HTTP 429 or any Contract change",
            "Platform parent facts CanonicalEvent Safety Controller PostgreSQL Temporal ownership or production composition",
            "any dynamic Runtime Suite case aggregate runtime-core-v1 reliability freeze security approval or production readiness",
        ],
    }
    if len(evidence["runtime_suite_case_inventory"]) != 17:
        raise AssertionError("a2.2.0 evidence must preserve 17 Suite case IDs")
    canonical = json.dumps(
        evidence, ensure_ascii=True, separators=(",", ":"), sort_keys=True
    ).encode()
    evidence["evidence_digest"] = {
        "profile": "sha256-canonical-json-excluding-evidence_digest",
        "value": "sha256:" + hashlib.sha256(canonical).hexdigest(),
    }
    encoded = (
        json.dumps(evidence, ensure_ascii=True, indent=2, sort_keys=True) + "\n"
    ).encode()
    native._scan_evidence_bytes("installed cross-language evidence", encoded)
    arguments.output.write_bytes(encoded)


if __name__ == "__main__":
    main()
