#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
from pathlib import Path
from typing import Any

import generate_pre_transport_safety_evidence as common

ROOT = Path(__file__).resolve().parents[1]
COMPACT_JWS = re.compile(
    rb"(?<![A-Za-z0-9_-])eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{20,}\."
    rb"[A-Za-z0-9_-]{20,}(?![A-Za-z0-9_-])"
)
PRIVATE_KEY_BLOCK = re.compile(
    rb"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----[\s\S]+?"
    rb"-----END [A-Z0-9 ]*PRIVATE KEY-----"
)
TRACEBACK_BLOCK = re.compile(rb"Traceback \(most recent call last\):\r?\n\s+File \"")
FORBIDDEN_ARTIFACT_FRAGMENTS = (
    b"Authorization: Bearer ",
    b"header.payload.signature-token-canary",
    b"request-body-canary",
    b"checkpoint-content-canary",
    b"-----BEGIN PRIVATE KEY-----",
    b"-----BEGIN RSA PRIVATE KEY-----",
    b"-----BEGIN EC PRIVATE KEY-----",
    b"Traceback (most recent call last)",
)
SOURCE_FILES = (
    "AGENTS.md",
    "dependency-lock.json",
    "doc/decision/0005-runtime-contract-projection-security-dependencies.md",
    "doc/plan/B03.2-native-runtime-core-conformance-safety-integration.md",
    "doc/plan/B03.2a1-secure-provider-process.md",
    "doc/plan/B03.2a1.1.4-read-boundary-evidence-closure.md",
    "doc/plan/B03.2a2.0-framework-neutral-go-port-outcome-model.md",
    "doc/plan/README.md",
    "go.mod",
    "go.sum",
    "internal/generated/runtimeapi/projection-manifest.json",
    "internal/runtimeport/README.md",
    "script/README.md",
    "script/check_implementation_supply_chain.py",
    "script/generate_go_port_outcome_evidence.py",
    "script/validate_implementation.sh",
    "toolchain/third-party.json",
    "toolchain/toolchain.env",
)
SOURCE_CACHE_ROOTS = ("internal/runtimeport", "script")
REQUIRED_TESTS = (
    "TestGoPortEvidenceMarkers",
    "TestReadResultHasExactlyOneClosedState",
    "TestMutationOutcomesCoverClosedDispositions",
    "TestMutationOutcomeRejectsIllegalCombinations",
    "TestReconciliationRequiresFreshBoundedReadOperations",
    "TestFailureAndOutcomeRenderingRedactsDetails",
    "TestConcurrentOutcomeReadsRemainImmutable",
    "TestOperationSetIsClosed",
    "TestOpaqueValuesCopyAndRedact",
    "TestInvocationAndRequestOperationBindings",
    "TestStableResponseValuesCopyDocuments",
    "TestConstructorsRejectUnboundedOrInvalidValues",
)
FUZZ_TEST = "FuzzMutationDispositionIsClosed"
FUZZ_SEED_COUNT = 6
EVIDENCE_MARKERS = (
    "stable-values-copy-redaction",
    "closed-read-result",
    "four-mutation-dispositions",
    "fresh-read-reconciliation-no-retry",
    "illegal-outcome-states-rejected",
    "five-operation-port-no-retry-surface",
)
EXPECTED_PRODUCTION_IMPORTS = "context;errors;fmt;strings;unicode/utf8;"


def reject_source_caches() -> None:
    for relative in SOURCE_CACHE_ROOTS:
        for path in (ROOT / relative).rglob("*"):
            if "__pycache__" in path.parts or path.suffix == ".pyc":
                raise AssertionError(
                    f"source tree contains forbidden Python cache content: {path}"
                )


def source_paths() -> tuple[Path, ...]:
    reject_source_caches()
    paths = [ROOT / relative for relative in SOURCE_FILES]
    paths.extend(sorted((ROOT / "internal/runtimeport").glob("*.go")))
    if any(
        not path.is_file() or "__pycache__" in path.parts or path.suffix == ".pyc"
        for path in paths
    ):
        raise AssertionError(
            "Go Port evidence source manifest contains invalid content"
        )
    return tuple(sorted(set(paths), key=lambda path: path.relative_to(ROOT).as_posix()))


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


def scan_source(paths: tuple[Path, ...]) -> int:
    for path in paths:
        data = path.read_bytes()
        if PRIVATE_KEY_BLOCK.search(data):
            raise AssertionError(f"source contains a complete private-key PEM: {path}")
        if COMPACT_JWS.search(data):
            raise AssertionError(f"source contains a complete compact JWS: {path}")
        if TRACEBACK_BLOCK.search(data):
            raise AssertionError(f"source contains a captured traceback: {path}")
    return len(paths)


def scan_artifact(name: str, data: bytes) -> None:
    for fragment in FORBIDDEN_ARTIFACT_FRAGMENTS:
        if fragment in data:
            raise AssertionError(f"{name} contains forbidden sensitive content")
    if PRIVATE_KEY_BLOCK.search(data):
        raise AssertionError(f"{name} contains a private-key PEM block")
    if COMPACT_JWS.search(data):
        raise AssertionError(f"{name} contains a complete compact JWS")
    if TRACEBACK_BLOCK.search(data):
        raise AssertionError(f"{name} contains a captured traceback")


def parse_go_port_log(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    scan_artifact("Go Port validation log", text.encode())
    for test in REQUIRED_TESTS:
        observed = len(
            re.findall(rf"^=== RUN\s+{re.escape(test)}$", text, re.MULTILINE)
        )
        if observed != 2:
            raise AssertionError(f"Go Port test {test} count differs: {observed}")
    fuzz_runs = len(re.findall(rf"^=== RUN\s+{FUZZ_TEST}$", text, re.MULTILINE))
    if fuzz_runs != 2:
        raise AssertionError(f"Go Port fuzz entry count differs: {fuzz_runs}")
    fuzz_seeds = len(
        re.findall(rf"^=== RUN\s+{FUZZ_TEST}/seed#\d+$", text, re.MULTILINE)
    )
    if fuzz_seeds != FUZZ_SEED_COUNT * 2:
        raise AssertionError(f"Go Port fuzz seed count differs: {fuzz_seeds}")
    markers: list[str] = []
    for marker in EVIDENCE_MARKERS:
        fragment = f"go-port-evidence:{marker}:passed"
        if text.count(fragment) != 2:
            raise AssertionError(f"Go Port evidence marker {marker} count differs")
        markers.append(marker)
    summaries = re.findall(
        r"^ok\s+github\.com/shell-echo/agent/internal/runtimeport\s+[^\s]+$",
        text,
        re.MULTILINE,
    )
    if len(summaries) != 2:
        raise AssertionError("Go Port normal/Race summaries differ")
    import_marker = f"go-port-imports:{EXPECTED_PRODUCTION_IMPORTS}"
    if text.count(import_marker) != 1:
        raise AssertionError("Go Port production import set differs")
    if text.count("go-port-module-files-base-revision-zero-diff:passed") != 1:
        raise AssertionError("Go module base-revision zero-diff marker is absent")
    return {
        "normal_test_count": len(REQUIRED_TESTS),
        "race_test_count": len(REQUIRED_TESTS),
        "fuzz_entrypoint": FUZZ_TEST,
        "fuzz_seed_count_per_run": FUZZ_SEED_COUNT,
        "dynamic_markers": markers,
        "production_imports": [
            value for value in EXPECTED_PRODUCTION_IMPORTS.split(";") if value
        ],
        "summaries": summaries,
    }


def load_toolchain() -> dict[str, str]:
    values: dict[str, str] = {}
    for raw_line in (
        (ROOT / "toolchain/toolchain.env").read_text(encoding="utf-8").splitlines()
    ):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        key, separator, value = line.partition("=")
        if separator != "=" or not key or not value:
            raise AssertionError("toolchain entry is invalid")
        values[key] = value
    return values


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
    parser.add_argument("--go-port-log", type=Path, required=True)
    parser.add_argument("--supply-chain-log", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    if not common.GIT_REVISION.fullmatch(arguments.application_base_revision):
        raise AssertionError("Application base revision is not a full Git object ID")

    go_port = parse_go_port_log(arguments.go_port_log)
    supply_chain_text = arguments.supply_chain_log.read_text(encoding="utf-8")
    if "Implementation supply-chain check passed:" not in supply_chain_text:
        raise AssertionError("supply-chain validation log is incomplete")
    scan_artifact("supply-chain log", supply_chain_text.encode())

    paths = source_paths()
    source_count = scan_source(paths)
    lock_path = ROOT / "dependency-lock.json"
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    suite_lock, suite = common.runtime_suite(lock)
    profile = next(
        profile
        for profile in suite["profiles"]
        if profile["profile_id"] == "runtime-core-v1"
    )
    tests = profile.get("tests")
    if not isinstance(tests, list):
        raise AssertionError("runtime-core-v1 cases are absent")
    case_ids = [test["test_id"] for test in tests]
    if len(case_ids) != 17 or len(case_ids) != len(set(case_ids)):
        raise AssertionError("runtime-core-v1 case count or uniqueness changed")

    projection_path = ROOT / "internal/generated/runtimeapi/projection-manifest.json"
    projection = json.loads(projection_path.read_text(encoding="utf-8"))
    predecessor_path = (
        ROOT / "build/evidence/b03.2a1.1.4/read-boundary-evidence-closure.json"
    )
    predecessor = json.loads(predecessor_path.read_text(encoding="utf-8"))
    if (
        predecessor.get("result") != "passed"
        or predecessor.get("maturity") != "provider_local_component"
        or predecessor.get("conformance_profile_result") != "not_claimed"
    ):
        raise AssertionError("a1.1.4 predecessor evidence boundary differs")

    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    copied_logs = {
        "go_port": arguments.output.parent / "go-port-validation.log",
        "supply_chain": arguments.output.parent / "supply-chain.log",
    }
    for source, target in (
        (arguments.go_port_log, copied_logs["go_port"]),
        (arguments.supply_chain_log, copied_logs["supply_chain"]),
    ):
        shutil.copyfile(source, target)
        scan_artifact(f"copied log {target.name}", target.read_bytes())

    toolchain = load_toolchain()
    evidence: dict[str, Any] = {
        "evidence_version": 1,
        "slice_id": "B03.2a2.0",
        "scope": "framework_neutral_go_port_and_outcome_model",
        "result": "passed",
        "maturity": "framework_neutral_go_port_component",
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
                "status": "not_evaluated_in_a2_0",
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
        "go_port": {
            "operations": [
                "capabilities",
                "start",
                "read_status",
                "submit_command",
                "read_events",
            ],
            "framework_neutral": True,
            "adapter_present": False,
            "production_composition_present": False,
            "mutation_internal_retry_surface": False,
            "mutation_dispositions": [
                "accepted",
                "rejected",
                "not_dispatched",
                "outcome_unknown",
            ],
            "outcome_unknown": {
                "fresh_read_authority_required": True,
                "original_mutation_must_not_be_retried": True,
                "read_operations": ["read_status", "read_events"],
                "executor_present": False,
                "persistence_present": False,
            },
            "opaque_values": {
                "explicit_nonzero_byte_bound": True,
                "constructor_copy": True,
                "defensive_getter_copy": True,
                "string_and_go_string_redacted": True,
                "schema_or_jws_validation_claimed": False,
            },
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
                "gap_id": "reconciliation-read-authority",
                "status": "blocked",
                "machine_readable": True,
                "reason": "fresh Status/Event token authority and durable reconciliation caller are absent",
            },
            {
                "gap_id": "strict-unwired-http-adapter",
                "status": "not_in_slice",
                "planned_slice": "B03.2a2.1",
            },
            {
                "gap_id": "installed-cross-language-component-evidence",
                "status": "not_in_slice",
                "planned_slice": "B03.2a2.2",
            },
            {
                "gap_id": "aggregate-runtime-core-v1",
                "status": "not_claimed",
                "planned_slice": "B03.2a2.3",
            },
            {
                "gap_id": "production-runtime-authority-and-composition",
                "status": "not_in_slice",
                "planned_slice": "B03.2b/B03.2c",
            },
        ],
        "validation": {
            "command": arguments.validation_command,
            **go_port,
            "logs": {key: log_evidence(path) for key, path in copied_logs.items()},
        },
        "supply_chain": {
            "result": "passed",
            "go_version": toolchain["GO_VERSION"],
            "go_toolchain_image": toolchain["GO_TOOLCHAIN_IMAGE"],
            "module_files_base_revision_zero_diff": True,
            "go_mod_sha256": "sha256:" + common.sha256_file(ROOT / "go.mod"),
            "go_sum_sha256": "sha256:" + common.sha256_file(ROOT / "go.sum"),
            "new_dependencies": [],
            "production_imports": go_port["production_imports"],
            "implementation_supply_chain_log": log_evidence(
                copied_logs["supply_chain"]
            ),
            "existing_application_sbom_provenance_gate": "required_and_passed_by_validation_command",
        },
        "sensitive_scan": {
            "result": "passed",
            "source_files_scanned": source_count,
            "copied_logs_scanned": len(copied_logs),
            "source_structural_categories": [
                "complete_compact_token",
                "complete_private_key_pem",
                "captured_traceback",
            ],
            "artifact_categories": [
                "bearer_or_complete_token",
                "request_document_content",
                "checkpoint_content",
                "private_key_pem",
                "captured_traceback",
            ],
        },
        "data_retention": {
            "durable_writes": "none",
            "migrations": "none",
            "token_or_document_persistence": "none",
            "existing_sqlite_postgresql_temporal_facts": "unchanged_forward_only",
        },
        "proven": [
            "framework-neutral five-operation Go Port surface",
            "bounded immutable opaque values with defensive copies and redacted rendering",
            "closed read failure and four-state mutation outcome invariants",
            "outcome_unknown requires fresh Status/Event authority and forbids replay of the original mutation",
            "normal and Race component behavior with standard-library-only production imports",
        ],
        "not_proven": [
            "HTTP adapter status mapping endpoint TLS identity or network behavior",
            "installed Native Runtime cross-language mTLS HTTP SQLite component behavior",
            "reconciliation token issuance durable caller execution or Platform parent facts",
            "CanonicalEvent production Safety Controller PostgreSQL Temporal ownership or composition",
            "aggregate runtime-core-v1 reliability freeze security approval or production readiness",
        ],
    }
    if len(evidence["runtime_suite_case_inventory"]) != 17:
        raise AssertionError("a2.0 evidence must preserve 17 Suite case IDs")
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
    scan_artifact("Go Port outcome evidence", encoded)
    arguments.output.write_bytes(encoded)


if __name__ == "__main__":
    main()
