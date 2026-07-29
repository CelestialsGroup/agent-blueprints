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
KEY_FINGERPRINTS = re.compile(r"secure-admission-public-key-fingerprints:([^\r\n]+)")
REQUIRED_TESTS = (
    "test_command_digest_operation_and_time_fail_closed",
    "test_data_bearing_v1_store_cannot_invent_security_bindings",
    "test_digest_and_strict_json_fail_before_jti_consumption",
    "test_idempotent_command_replay_rechecks_authority",
    "test_mutation_jti_is_consumed_only_with_committed_start",
    "test_projection_loader_normalizes_non_object_lock_input",
    "test_read_path_and_cursor_replacement_are_rejected",
    "test_secure_lifecycle_uses_both_algorithms_and_authorized_reads",
    "test_security_configuration_is_immutable_and_rejects_private_keys",
    "test_start_nested_digest_and_gateway_semantics_fail_before_jti",
    "test_strict_ijson_matches_every_locked_vector",
    "test_strict_ijson_rejects_encoding_and_structural_overflow",
    "test_token_negative_matrix_has_no_runtime_or_jti_side_effect",
)
SOURCE_FILES = (
    "dependency-lock.json",
    "doc/decision/0005-runtime-contract-projection-security-dependencies.md",
    "doc/plan/B03.2-native-runtime-core-conformance-safety-integration.md",
    "doc/plan/B03.2a1-secure-provider-process.md",
    "internal/generated/runtimeapi/projection-manifest.json",
    "runtime/native/build-constraints.txt",
    "runtime/native/pyproject.toml",
    "runtime/native/uv.lock",
    "script/check_implementation_supply_chain.py",
    "script/generate_secure_admission_evidence.py",
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
    encoded = json.dumps(files, separators=(",", ":"), sort_keys=True).encode()
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
    return lock_entry, suite


def case_matrix(suite: dict[str, Any]) -> list[dict[str, str]]:
    profile = next(
        profile
        for profile in suite["profiles"]
        if profile["profile_id"] == "runtime-core-v1"
    )
    case_results = {
        "capabilities-immutable": (
            "configuration_subset_passed",
            "security configuration and public-key fingerprints are immutable; Capabilities HTTP remains a1.1",
        ),
        "start-idempotent": (
            "kernel_passed",
            "fresh-JTI exact replay remains one RuntimeRun and one start event",
        ),
        "start-digest-conflict": (
            "secure_admission_passed",
            "raw request digest conflicts fail before JTI consumption or Runtime facts",
        ),
        "start-executable-context-complete": (
            "presented_root_context_subset_passed",
            "Schema, nested digests and presented root bindings pass; production RunManifest authority and child runs remain absent",
        ),
        "start-encoded-body-limit": (
            "byte_api_subset_passed",
            "8 MiB is rejected before Strict JSON parsing; HTTP framing and 413 transport are a1.1",
        ),
        "command-contiguous": (
            "kernel_passed",
            "securely admitted supported commands retain contiguous sequence enforcement",
        ),
        "stale-fencing-rejected": (
            "provider_component_passed",
            "new mutations and authorized reads reject stale durable fencing",
        ),
        "typed-event-payloads": (
            "kernel_subset_passed",
            "a0 emitted event variants remain Schema-valid; complete Registry emission is not claimed",
        ),
        "cursor-resume": (
            "kernel_passed",
            "authorized reads retain exact event_sequence greater-than cursor behavior",
        ),
        "cursor-expired-explicit": (
            "kernel_passed",
            "authorized reads retain explicit earliest/latest cursor recovery facts",
        ),
        "cancel-confirmed": (
            "provider_subset_passed",
            "secure Cancel remains intent until private execution evidence confirms terminal cancellation",
        ),
        "checkpoint-compatibility": (
            "same_revision_subset_passed",
            "same-revision restore remains proven; cross-revision authority is absent",
        ),
        "adapter-restart-resume": (
            "store_restart_subset_passed",
            "v2 SQLite binding and a0 work recovery reopen safely; no Go adapter or process boundary exists",
        ),
        "authorization-renewal": (
            "platform_blocked",
            "requires authoritative append-only RuntimeAuthorization and ArtifactGrant lineage",
        ),
        "runtime-token-replay-and-expiry": (
            "secure_admission_subset_passed",
            "EdDSA/ES256, closed Header/Claims, scope/time/caller binding and mutation JTI pass; production issuer, mTLS and revocation are absent",
        ),
        "system-safety-control": (
            "provider_subset_passed",
            "signed reduction-only safety Cancel binding passes; production Safety Controller authority and dispatch are absent",
        ),
        "outcome-unknown-reconcile": (
            "not_in_a1_0",
            "HTTP uncertainty and Go adapter reconciliation belong to a2",
        ),
    }
    tests = profile.get("tests")
    if not isinstance(tests, list) or len(tests) != 17:
        raise AssertionError("locked runtime-core-v1 no longer contains 17 cases")
    case_ids = [test["test_id"] for test in tests]
    if set(case_ids) != set(case_results):
        raise AssertionError("runtime-core-v1 cases and a1.0 evidence mapping differ")
    return [
        {
            "case_id": case_id,
            "verdict": case_results[case_id][0],
            "boundary": case_results[case_id][1],
        }
        for case_id in case_ids
    ]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--application-base-revision", required=True)
    parser.add_argument("--validation-command", required=True)
    parser.add_argument("--python-validation-log", type=Path, required=True)
    parser.add_argument("--supply-chain-log", type=Path, required=True)
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
        raise AssertionError("Native Runtime validation log lacks the a1.0 test set")
    fingerprints_match = KEY_FINGERPRINTS.search(validation_text)
    if fingerprints_match is None:
        raise AssertionError(
            "Native Runtime validation log lacks test key fingerprints"
        )
    fingerprints = []
    for entry in fingerprints_match.group(1).split(","):
        kid, separator, digest = entry.partition("=")
        if separator != "=" or not re.fullmatch(r"sha256:[0-9a-f]{64}", digest):
            raise AssertionError("Native Runtime test key fingerprint is invalid")
        fingerprints.append({"kid": kid, "fingerprint": digest})
    supply_chain_text = arguments.supply_chain_log.read_text(encoding="utf-8")
    if "Implementation supply-chain check passed:" not in supply_chain_text:
        raise AssertionError("supply-chain validation log is incomplete")

    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    copied_validation = arguments.output.parent / "native-runtime-validation.log"
    copied_supply_chain = arguments.output.parent / "supply-chain.log"
    shutil.copyfile(arguments.python_validation_log, copied_validation)
    shutil.copyfile(arguments.supply_chain_log, copied_supply_chain)

    lock_path = ROOT / "dependency-lock.json"
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    lock_entry, suite = runtime_suite(lock)
    projection_path = ROOT / "internal/generated/runtimeapi/projection-manifest.json"
    projection = json.loads(projection_path.read_text(encoding="utf-8"))
    migration_root = ROOT / "runtime/native/src/agent_native_runtime/migrations"
    evidence = {
        "evidence_version": 1,
        "slice_id": "B03.2a1.0",
        "scope": "secure_admission_core",
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
            json.dumps(suite, separators=(",", ":"), sort_keys=True).encode()
        ).hexdigest(),
        "runtime_projection": {
            "manifest_sha256": "sha256:" + sha256_file(projection_path),
            "schema_count": projection["schema_count"],
            "schema_closure_sha256": "sha256:" + projection["schema_closure_sha256"],
            "openapi_sha256": "sha256:" + projection["openapi_sha256"],
        },
        "sqlite_migration_v2": {
            "up_sha256": "sha256:"
            + sha256_file(migration_root / "0002_secure_admission_core.up.sql"),
            "down_sha256": "sha256:"
            + sha256_file(migration_root / "0002_secure_admission_core.down.sql"),
            "data_bearing_v1_upgrade": "fail_closed",
            "data_bearing_v2_rollback": "forward_only",
        },
        "test_public_key_fingerprints": fingerprints,
        "validation": {
            "command": arguments.validation_command,
            "test_count": counts[-1],
            "quality": {
                "ruff_version": "0.16.0",
                "ruff_format": "passed",
                "ruff_lint": "passed",
                "mypy_version": "2.3.0",
                "mypy_strict": "passed",
            },
            "logs": {
                "native_runtime": {
                    "path": copied_validation.name,
                    "sha256": "sha256:" + sha256_file(copied_validation),
                },
                "supply_chain": {
                    "path": copied_supply_chain.name,
                    "sha256": "sha256:" + sha256_file(copied_supply_chain),
                },
            },
        },
        "runtime_core_case_matrix": case_matrix(suite),
        "proven": [
            "full locked Strict I-JSON vector admission with bounded number, depth and node resources",
            "locked Draft 2020-12 Start, Command, descriptor, JWS Header and Claims validation",
            "presented root Start nested digest, scope and authorization time consistency",
            "EdDSA and ES256 signature plus closed caller, audience, operation and request binding",
            "mutation JTI consumption atomic with durable accepted facts",
            "Provider-local immutable security binding and authorized read recheck in one transaction",
            "empty v1 to v2 migration and fail-closed data-bearing v1 upgrade",
        ],
        "not_proven": [
            "HTTP server, exact Content-Type, HTTP framing, StandardError transport or mTLS process identity",
            "production ProviderResolution, issuer, signing-key custody, rotation, revocation or workload identity",
            "production RunManifest, RuntimeAuthorization, Policy, Budget, Permission or ArtifactGrant authority",
            "Go adapter, production composition root, Platform PostgreSQL, Temporal caller or CanonicalEvent projection",
            "production Safety Controller, cross-revision restore, aggregate runtime-core-v1 or production readiness",
        ],
    }
    arguments.output.write_text(
        json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
