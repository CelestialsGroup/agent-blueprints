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
TRACEBACK_BLOCK = re.compile(rb'Traceback \(most recent call last\):\r?\n\s+File "')
FORBIDDEN_ARTIFACT_FRAGMENTS = (
    b"Authorization: Bearer ",
    b"header.payload.signature",
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
    "doc/plan/B03.2a2.1-strict-unwired-http-adapter.md",
    "doc/plan/README.md",
    "go.mod",
    "go.sum",
    "internal/generated/runtimeapi/projection-manifest.json",
    "internal/runtimeport/README.md",
    "script/README.md",
    "script/check_implementation_supply_chain.py",
    "script/generate_go_port_outcome_evidence.py",
    "script/generate_http_adapter_evidence.py",
    "script/validate_implementation.sh",
    "toolchain/third-party.json",
    "toolchain/toolchain.env",
)
SOURCE_CACHE_ROOTS = ("internal/runtimeport", "script")
REQUIRED_TESTS = (
    "TestLockedRuntimeFixturesHaveDraft2020Parity",
    "TestGeneratedTransportUnmarshalsLockedCapability",
    "TestJCSMatchesLockedVectors",
    "TestJOSEAllowlistSupportsEdDSAAndES256",
    "TestJOSEAllowlistCannotBeMutatedToAcceptHS256",
    "TestRuntimeDocumentValidatorAcceptsLockedMutationExamples",
    "TestRuntimeDocumentValidatorRejectsStructuralAndBindingDrift",
    "TestRuntimeDocumentValidatorBindsSchemaAndEventRegistry",
    "TestRuntimeDocumentValidatorRejectsInvalidRegistryBinding",
    "TestNewRejectsMissingHarnessAuthorityAndUnsafeDefaults",
    "TestNewClonesAndBoundsInjectedClient",
    "TestMutationOperationsDispatchExactBodyOnce",
    "TestMutationPreDispatchFailuresMakeZeroRequests",
    "TestMutationMapsOnlyDeclaredKnownRejections",
    "TestMutationUncertaintyRequiresFreshReadsAndNoRetry",
    "TestMutationResponseLossAndDeadlineDispatchOnlyOnce",
    "TestMutationAcceptedResponseMustBindIdentityAndFencing",
    "TestReadOperationsUseExactAuthenticatedHTTP11Routes",
    "TestCapabilitiesBindsCanonicalImmutabilityUnderConcurrency",
    "TestReadStatusMapsOnlyDeclaredFailures",
    "TestReadAdapterRejectsResponseAndIdentityDrift",
    "TestEventReadMapsDeclaredCursorExpiry",
    "TestReadAdapterDoesNotDispatchInvalidAuthorityOrFollowRedirect",
)
EVIDENCE_MARKERS = (
    "real-mtls-http11-read-routes",
    "capabilities-canonical-concurrency",
    "closed-read-status-authority-map",
    "strict-response-identity-cursor-bounds",
    "one-dispatch-exact-mutation-body",
    "sealed-pre-dispatch-zero-network",
    "closed-known-mutation-rejections",
    "outcome-unknown-fresh-read-no-retry",
    "response-loss-deadline-single-dispatch",
)
EXPECTED_IMPORTS = {
    "contractprojection": (
        "bytes;crypto/sha256;encoding/json;errors;fmt;github.com/go-jose/go-jose/v4;"
        "github.com/gowebpki/jcs;github.com/santhosh-tekuri/jsonschema/v6;"
        "github.com/shell-echo/agent/internal/runtimeport;io;strings;unicode/utf8;"
    ),
    "httpadapter": (
        "bytes;context;crypto/sha256;crypto/tls;encoding/json;errors;"
        "github.com/shell-echo/agent/internal/generated/runtimeapi;"
        "github.com/shell-echo/agent/internal/runtimeport;"
        "github.com/shell-echo/agent/internal/runtimeport/contractprojection;"
        "io;net/http;net/url;strconv;strings;sync;time;"
    ),
}


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
    paths.extend((ROOT / "internal/runtimeport").rglob("*.go"))
    if any(
        not path.is_file() or "__pycache__" in path.parts or path.suffix == ".pyc"
        for path in paths
    ):
        raise AssertionError("HTTP adapter evidence source manifest is invalid")
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


def parse_adapter_log(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    scan_artifact("HTTP adapter validation log", text.encode())
    for test in REQUIRED_TESTS:
        observed = len(
            re.findall(rf"^=== RUN\s+{re.escape(test)}$", text, re.MULTILINE)
        )
        if observed != 2:
            raise AssertionError(f"HTTP adapter test {test} count differs: {observed}")
    markers: list[str] = []
    for marker in EVIDENCE_MARKERS:
        fragment = f"http-adapter-evidence:{marker}:passed"
        if text.count(fragment) != 2:
            raise AssertionError(f"HTTP adapter evidence marker {marker} count differs")
        markers.append(marker)
    summaries: dict[str, list[str]] = {}
    for package in ("contractprojection", "httpadapter"):
        matches = re.findall(
            rf"^ok\s+github\.com/shell-echo/agent/internal/runtimeport/{package}\s+[^\s]+$",
            text,
            re.MULTILINE,
        )
        if len(matches) != 2:
            raise AssertionError(f"{package} normal/Race summaries differ")
        summaries[package] = matches
    for package, imports in EXPECTED_IMPORTS.items():
        if text.count(f"{package}-imports:{imports}") != 1:
            raise AssertionError(f"{package} production import set differs")
    for marker in (
        "http-adapter-module-files-base-revision-zero-diff:passed",
        "http-adapter-production-importers:none",
        "http-adapter-client-do-calls:1",
    ):
        if text.count(marker) != 1:
            raise AssertionError(f"HTTP adapter static marker differs: {marker}")
    return {
        "normal_test_count": len(REQUIRED_TESTS),
        "race_test_count": len(REQUIRED_TESTS),
        "required_tests": list(REQUIRED_TESTS),
        "dynamic_markers": markers,
        "summaries": summaries,
        "production_importers": [],
        "client_do_call_sites": 1,
        "production_imports": {
            package: [item for item in imports.split(";") if item]
            for package, imports in EXPECTED_IMPORTS.items()
        },
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
    parser.add_argument("--http-adapter-log", type=Path, required=True)
    parser.add_argument("--supply-chain-log", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    if not common.GIT_REVISION.fullmatch(arguments.application_base_revision):
        raise AssertionError("Application base revision is not a full Git object ID")

    validation = parse_adapter_log(arguments.http_adapter_log)
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
        raise TypeError("runtime-core-v1 cases are absent")
    case_ids = [test["test_id"] for test in tests]
    if len(case_ids) != 17 or len(case_ids) != len(set(case_ids)):
        raise AssertionError("runtime-core-v1 case count or uniqueness changed")

    projection_path = ROOT / "internal/generated/runtimeapi/projection-manifest.json"
    projection = json.loads(projection_path.read_text(encoding="utf-8"))
    predecessor_path = (
        ROOT / "build/evidence/b03.2a2.0/framework-neutral-go-port-outcome-model.json"
    )
    predecessor = json.loads(predecessor_path.read_text(encoding="utf-8"))
    if (
        predecessor.get("result") != "passed"
        or predecessor.get("maturity") != "framework_neutral_go_port_component"
        or predecessor.get("conformance_profile_result") != "not_claimed"
    ):
        raise AssertionError("a2.0 predecessor evidence boundary differs")

    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    copied_logs = {
        "http_adapter": arguments.output.parent / "http-adapter-validation.log",
        "supply_chain": arguments.output.parent / "supply-chain.log",
    }
    for source, target in (
        (arguments.http_adapter_log, copied_logs["http_adapter"]),
        (arguments.supply_chain_log, copied_logs["supply_chain"]),
    ):
        shutil.copyfile(source, target)
        scan_artifact(f"copied log {target.name}", target.read_bytes())

    toolchain = load_toolchain()
    evidence: dict[str, Any] = {
        "evidence_version": 1,
        "slice_id": "B03.2a2.1",
        "scope": "strict_unwired_go_http_adapter",
        "result": "passed",
        "maturity": "strict_unwired_http_adapter_component",
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
                "status": "not_evaluated_in_a2_1",
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
        "adapter": {
            "operations": [
                "capabilities",
                "start",
                "read_status",
                "submit_command",
                "read_events",
            ],
            "harness_only": True,
            "production_composition_present": False,
            "installed_native_runtime_peer": False,
            "controlled_go_peer": True,
            "real_loopback_tls_http_socket": True,
            "mutual_tls_required": True,
            "http_version": "HTTP/1.1",
            "contract_validation": {
                "draft": "2020-12",
                "schema_count": projection["schema_count"],
                "event_registry_binding": "agent-runtime-core@1",
                "duplicate_utf8_depth_node_number_and_byte_bounds": True,
                "mutation_excluding_digest_jcs": True,
            },
            "read_boundary": {
                "capabilities_has_bearer": False,
                "status_and_events_single_bounded_bearer": True,
                "capabilities_canonical_immutability": True,
                "identity_fencing_order_limit_cursor_validation": True,
                "read_internal_retry": False,
                "status_event_400": "invalid_response_blocked_authority",
                "read_429": "invalid_response_blocked_authority",
            },
            "mutation_boundary": {
                "client_do_call_sites": 1,
                "transport_replay_surface": False,
                "sealed_pre_dispatch_failure": "not_dispatched",
                "accepted_statuses": [202],
                "declared_known_rejections_only": True,
                "post_dispatch_uncertainty": "outcome_unknown",
                "fresh_read_authority_required": True,
                "original_mutation_must_not_be_retried": True,
            },
            "response_boundary": {
                "content_type": "single_application_json",
                "normalized_content_length": "single_canonical_and_complete",
                "transfer_and_content_encoding": "rejected",
                "byte_and_header_bounds": True,
                "identical_duplicate_content_length_wire_multiplicity": (
                    "not_observable_after_net_http_normalization"
                ),
            },
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
                "reason": "parent classification mentions read 429 but locked read operations omit 429",
                "action": "map_to_invalid_response_and_do_not_guess",
            },
            {
                "gap_id": "reconciliation-read-authority",
                "status": "blocked",
                "reason": "fresh token authority and durable reconciliation caller are absent",
            },
            {
                "gap_id": "unconstructed-zero-mutation-reference",
                "status": "not_claimed",
                "reason": "a2.0 cannot represent not_dispatched without a valid MutationReference; zero request stays invalid and makes zero network calls",
            },
            {
                "gap_id": "identical-content-length-wire-multiplicity",
                "status": "not_claimed",
                "reason": "Go net/http normalizes identical duplicate Content-Length before the adapter boundary",
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
            **validation,
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
            "production_imports": validation["production_imports"],
            "production_importers": validation["production_importers"],
            "implementation_supply_chain_log": log_evidence(
                copied_logs["supply_chain"]
            ),
            "existing_application_sbom_provenance_gate": (
                "required_and_passed_by_validation_command"
            ),
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
            "test_ca_cert_keys_and_sockets": "ephemeral_memory_only",
            "capabilities_cache": "canonical_sha256_only",
            "existing_sqlite_postgresql_temporal_facts": "unchanged_forward_only",
        },
        "proven": [
            "harness-only five-operation Go HTTP adapter over real loopback mutual TLS and HTTP/1.1",
            "locked Draft 2020-12 Schema closure and admitted Runtime Event Registry validation before DTO mapping",
            "exact read routes bearer separation response bounds and closed declared status mapping",
            "single-dispatch Start and Command with four-state outcome and no original mutation retry",
            "normal and Race behavior with no production composition importer or new dependency",
        ],
        "not_proven": [
            "installed Native Runtime cross-language process SQLite or recovery behavior through this adapter",
            "raw identical duplicate Content-Length wire multiplicity before net/http normalization",
            "unconstructed zero mutation request as a valid referenced not_dispatched outcome",
            "reconciliation token issuance durable caller execution or Platform parent facts",
            "CanonicalEvent production Safety Controller PostgreSQL Temporal ownership or composition",
            "aggregate runtime-core-v1 reliability freeze security approval or production readiness",
        ],
    }
    if len(evidence["runtime_suite_case_inventory"]) != 17:
        raise AssertionError("a2.1 evidence must preserve 17 Suite case IDs")
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
    scan_artifact("HTTP adapter evidence", encoded)
    arguments.output.write_bytes(encoded)


if __name__ == "__main__":
    main()
