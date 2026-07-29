#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import tomllib
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
GIT_REVISION = re.compile(r"^[0-9a-f]{40,64}$")
SHA256_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
TEST_COUNT = re.compile(r"Ran (\d+) tests")
REQUIRED_TESTS = (
    "test_concurrent_migrate_serializes_schema_and_configuration",
    "test_interrupted_migration_and_binding_are_idempotently_recoverable",
    "test_invalid_tokens_never_open_store_or_reveal_run_existence",
    "test_missing_security_metadata_fails_open_current_without_write",
    "test_mutation_jti_is_consumed_only_with_committed_start",
    "test_open_current_missing_store_has_no_filesystem_side_effect",
    "test_open_current_rejects_noncurrent_migration_ledger_without_write",
    "test_secure_lifecycle_uses_both_algorithms_and_authorized_reads",
    "test_security_binding_interruption_is_idempotently_recoverable",
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
    "script/generate_implementation_evidence.py",
    "script/generate_pre_transport_safety_evidence.py",
    "script/validate_implementation.sh",
    "toolchain/third-party.json",
)
SOURCE_DIRECTORIES = (
    "runtime/native/src/agent_native_runtime",
    "runtime/native/test",
)
EXPECTED_DIRECT_DEPENDENCIES = (
    "cryptography==49.0.0",
    "jsonschema==4.26.0",
    "PyJWT==2.13.0",
    "rfc8785==0.1.4",
    "typing-extensions==4.15.0",
)
EXPECTED_DEV_DEPENDENCIES = (
    "mypy==2.3.0",
    "ruff==0.16.0",
)
EXPECTED_BUILD_DEPENDENCIES = ("hatchling==1.31.0",)
EXPECTED_MIGRATIONS = (
    "0001_runtime_durable_kernel.down.sql",
    "0001_runtime_durable_kernel.up.sql",
    "0002_secure_admission_core.down.sql",
    "0002_secure_admission_core.up.sql",
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


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
            "pre_transport_subset_passed",
            "immutable Runtime and security configuration now require explicit migration and read-only current-state admission; Capabilities HTTP is a1.1.1",
        ),
        "start-idempotent": (
            "a1_0_regression_passed",
            "fresh-JTI exact replay remains one RuntimeRun and one start event",
        ),
        "start-digest-conflict": (
            "a1_0_regression_passed",
            "request digest conflicts still fail before JTI consumption or Runtime facts",
        ),
        "start-executable-context-complete": (
            "presented_context_subset_passed",
            "signed presented context is checked before the transactional durable binding; production parent authority remains absent",
        ),
        "start-encoded-body-limit": (
            "byte_api_subset_passed",
            "the existing 8 MiB byte API limit remains; HTTP framing and pre-parse 413 are a1.1.2",
        ),
        "command-contiguous": (
            "a1_0_regression_passed",
            "pre-store signature admission preserves transactional contiguous command sequencing",
        ),
        "stale-fencing-rejected": (
            "a1_0_regression_passed",
            "valid signed requests still recheck durable fencing in the same transaction",
        ),
        "typed-event-payloads": (
            "a1_0_regression_subset_passed",
            "existing emitted Provider-local event variants remain Schema-valid; complete Registry emission is not claimed",
        ),
        "cursor-resume": (
            "a1_0_regression_passed",
            "signed Event descriptors still retain exact durable cursor semantics",
        ),
        "cursor-expired-explicit": (
            "a1_0_regression_passed",
            "signed Event reads retain explicit earliest/latest cursor recovery facts",
        ),
        "cancel-confirmed": (
            "a1_0_regression_subset_passed",
            "signed Cancel remains intent until private execution evidence confirms cancellation",
        ),
        "checkpoint-compatibility": (
            "same_revision_subset_passed",
            "explicit reopen preserves same-revision checkpoint recovery only",
        ),
        "adapter-restart-resume": (
            "provider_store_subset_passed",
            "explicit current-state reopen and interrupted migration/configuration recovery pass; no process or Go adapter is claimed",
        ),
        "authorization-renewal": (
            "platform_blocked",
            "requires authoritative append-only RuntimeAuthorization and ArtifactGrant lineage",
        ),
        "runtime-token-replay-and-expiry": (
            "pre_store_admission_subset_passed",
            "complete JWS verification and fixed claims precede every Command, Status and Event store access while mutation JTI remains transaction-bound",
        ),
        "system-safety-control": (
            "provider_subset_passed",
            "signed safety-control ID and digest now flow through pre-store admission into reduction-only transactional checks; production authority is absent",
        ),
        "outcome-unknown-reconcile": (
            "not_in_a1_1_0",
            "HTTP response uncertainty and Go adapter reconciliation remain outside this pre-transport slice",
        ),
    }
    tests = profile.get("tests")
    if not isinstance(tests, list) or not tests:
        raise AssertionError("locked runtime-core-v1 has no cases")
    case_ids = [test["test_id"] for test in tests]
    if len(case_ids) != len(set(case_ids)) or set(case_ids) != set(case_results):
        raise AssertionError("runtime-core-v1 cases and a1.1.0 evidence mapping differ")
    return [
        {
            "case_id": case_id,
            "verdict": case_results[case_id][0],
            "boundary": case_results[case_id][1],
        }
        for case_id in case_ids
    ]


def dependency_evidence() -> dict[str, Any]:
    pyproject = tomllib.loads(
        (ROOT / "runtime/native/pyproject.toml").read_text(encoding="utf-8")
    )
    direct = tuple(pyproject["project"]["dependencies"])
    dev = tuple(pyproject["dependency-groups"]["dev"])
    build = tuple(pyproject["build-system"]["requires"])
    if direct != EXPECTED_DIRECT_DEPENDENCIES:
        raise AssertionError("Native Runtime direct dependencies changed")
    if dev != EXPECTED_DEV_DEPENDENCIES:
        raise AssertionError("Native Runtime development dependencies changed")
    if build != EXPECTED_BUILD_DEPENDENCIES:
        raise AssertionError("Native Runtime build dependencies changed")
    return {
        "change_for_slice": "none",
        "runtime": list(direct),
        "development": list(dev),
        "build": list(build),
        "uv_lock_sha256": "sha256:" + sha256_file(ROOT / "runtime/native/uv.lock"),
    }


def migration_evidence() -> dict[str, Any]:
    migration_root = ROOT / "runtime/native/src/agent_native_runtime/migrations"
    names = tuple(sorted(path.name for path in migration_root.glob("*.sql")))
    if names != EXPECTED_MIGRATIONS:
        raise AssertionError("a1.1.0 must not add or remove a SQLite migration")
    return {
        "change_for_slice": "none",
        "schema_version": 2,
        "files": [
            {"path": name, "sha256": "sha256:" + sha256_file(migration_root / name)}
            for name in names
        ],
    }


def supply_chain_evidence(
    artifact: Path, rebuild: Path, evidence_dir: Path
) -> dict[str, Any]:
    if artifact.read_bytes() != rebuild.read_bytes():
        raise AssertionError("Native Runtime wheel rebuild is not reproducible")
    artifact_digest = "sha256:" + sha256_file(artifact)
    spdx_path = evidence_dir / "native-runtime.spdx.json"
    provenance_path = evidence_dir / "native-runtime.provenance.json"
    build_provenance_path = evidence_dir / "native-runtime.build-provenance.json"
    spdx = json.loads(spdx_path.read_text(encoding="utf-8"))
    provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
    build_provenance = json.loads(build_provenance_path.read_text(encoding="utf-8"))
    if spdx.get("spdxVersion") != "SPDX-2.3":
        raise AssertionError("Native Runtime SBOM is not SPDX 2.3")
    if provenance.get("predicateType") != "https://slsa.dev/provenance/v1":
        raise AssertionError("Native Runtime provenance is not SLSA v1")
    if provenance.get("subject") != [
        {
            "name": "agent-native-runtime-wheel",
            "digest": {"sha256": artifact_digest.removeprefix("sha256:")},
        }
    ]:
        raise AssertionError("Native Runtime provenance subject differs from wheel")
    for field in (
        "source_revision",
        "source_tree_digest",
        "build_artifact_digest",
        "sbom_digest",
        "provenance_statement_digest",
        "build_system",
    ):
        if field not in build_provenance:
            raise AssertionError(f"Native Runtime BuildProvenance lacks {field}")
    if build_provenance["build_artifact_digest"] != artifact_digest:
        raise AssertionError("Native Runtime BuildProvenance differs from wheel")
    if build_provenance["sbom_digest"] != "sha256:" + sha256_file(spdx_path):
        raise AssertionError("Native Runtime BuildProvenance differs from SPDX SBOM")
    if build_provenance["provenance_statement_digest"] != (
        "sha256:" + sha256_file(provenance_path)
    ):
        raise AssertionError(
            "Native Runtime BuildProvenance differs from SLSA statement"
        )
    return {
        "reproducible_wheel": {
            "artifact": artifact.name,
            "sha256": artifact_digest,
            "rebuild_sha256": "sha256:" + sha256_file(rebuild),
            "byte_identical": True,
        },
        "spdx_2_3": {
            "path": spdx_path.relative_to(ROOT).as_posix(),
            "sha256": "sha256:" + sha256_file(spdx_path),
        },
        "slsa_v1": {
            "path": provenance_path.relative_to(ROOT).as_posix(),
            "sha256": "sha256:" + sha256_file(provenance_path),
        },
        "build_provenance": {
            "path": build_provenance_path.relative_to(ROOT).as_posix(),
            "sha256": "sha256:" + sha256_file(build_provenance_path),
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--application-base-revision", required=True)
    parser.add_argument("--validation-command", required=True)
    parser.add_argument("--python-validation-log", type=Path, required=True)
    parser.add_argument("--supply-chain-log", type=Path, required=True)
    parser.add_argument("--native-runtime-artifact", type=Path, required=True)
    parser.add_argument("--native-runtime-rebuild", type=Path, required=True)
    parser.add_argument("--implementation-evidence-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    if not GIT_REVISION.fullmatch(arguments.application_base_revision):
        raise AssertionError("Application base revision is not a full Git object ID")

    validation_text = arguments.python_validation_log.read_text(encoding="utf-8")
    for fragment in (
        *REQUIRED_TESTS,
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
    if not counts or counts[-1] < len(REQUIRED_TESTS):
        raise AssertionError("Native Runtime validation log lacks the a1.1.0 test set")
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
    evidence = {
        "evidence_version": 1,
        "slice_id": "B03.2a1.1.0",
        "scope": "pre_transport_safety_preconditions",
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
        "dependencies": dependency_evidence(),
        "sqlite_migrations": migration_evidence(),
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
        "supply_chain": supply_chain_evidence(
            arguments.native_runtime_artifact,
            arguments.native_runtime_rebuild,
            arguments.implementation_evidence_dir,
        ),
        "proven": [
            "constructors do not create Runtime state directories, SQLite files or checkpoint paths",
            "migrate is explicit and idempotent while open_current rejects missing, old, newer, discontinuous or drifted schema without database writes",
            "immutable Runtime and security metadata plus checkpoint directory state are read-only startup preconditions",
            "Command, Status and Event complete bounded JWS verification before any Provider store access",
            "existing and nonexistent RuntimeRun targets have identical invalid-signature rejection without an existence oracle",
            "valid signed requests retain transaction-bound durable context, fencing and mutation JTI checks",
            "reproducible wheel, dependency audit, SPDX 2.3, SLSA v1 and BuildProvenance pass through the Application Gate",
        ],
        "not_proven": [
            "HTTP listener, HTTP/1.1 framing, TLS, mTLS, test PKI, certificate identity or a real Provider subprocess",
            "migrate or serve CLI, readiness, drain, SIGTERM, request concurrency or timeout behavior",
            "Capabilities, Start, Command, Status or Event transport encoding and StandardError mapping",
            "commit-boundary process crashes, response loss or kill -9 process recovery",
            "Status/Event HTTP 400 mapping, which remains blocked on authoritative OpenAPI interpretation",
            "Go adapter, production composition root, token issuer, private-key custody, ProviderResolution or production caller",
            "Platform PostgreSQL, Temporal caller, CanonicalEvent, production Safety Controller or aggregate runtime-core-v1 conformance",
        ],
    }
    for value in (
        evidence["dependency_lock_sha256"],
        evidence["contract_manifest_digest"],
        evidence["runtime_suite"]["suite_digest"],
    ):
        if not isinstance(value, str) or not SHA256_DIGEST.fullmatch(value):
            raise AssertionError("a1.1.0 governed digest is invalid")
    arguments.output.write_text(
        json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
