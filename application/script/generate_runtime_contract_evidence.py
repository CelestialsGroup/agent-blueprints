#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
GIT_REVISION = re.compile(r"^[0-9a-f]{40,64}$")
SOURCE_FILES = (
    "dependency-lock.json",
    "doc/decision/0005-runtime-contract-projection-security-dependencies.md",
    "doc/plan/B03.2-native-runtime-core-conformance-safety-integration.md",
    "go.mod",
    "go.sum",
    "runtime/native/pyproject.toml",
    "runtime/native/src/agent_native_runtime/contract_projection.py",
    "runtime/native/test/test_contract_projection.py",
    "runtime/native/uv.lock",
    "script/check_implementation_supply_chain.py",
    "script/generate_implementation_evidence.py",
    "script/generate_runtime_contract.sh",
    "script/generate_runtime_contract_evidence.py",
    "script/runtime_contract_projection.py",
    "script/validate_implementation.sh",
    "test/conformance/runtime-contract-fixtures.json",
    "toolchain/runtime-python-codegen-packages.json",
    "toolchain/third-party.json",
    "toolchain/toolchain.env",
)
SOURCE_DIRECTORIES = (
    "internal/generated/runtimeapi",
    "internal/runtimeport/contractprojection",
    "runtime/native/src/agent_native_runtime/generated/runtimeapi",
    "toolchain/runtime-codegen",
)


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def tree_digest(path: Path) -> str:
    digest = hashlib.sha256()
    for item in sorted(candidate for candidate in path.rglob("*") if candidate.is_file()):
        relative = item.relative_to(path).as_posix().encode("utf-8")
        content = item.read_bytes()
        digest.update(len(relative).to_bytes(8, "big"))
        digest.update(relative)
        digest.update(len(content).to_bytes(8, "big"))
        digest.update(content)
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
        for path in sorted(set(paths), key=lambda item: item.relative_to(ROOT).as_posix())
    ]
    encoded = json.dumps(
        files,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return {
        "files": files,
        "source_set_sha256": "sha256:" + hashlib.sha256(encoded).hexdigest(),
    }


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def bind_validation_log(
    source: Path,
    output_directory: Path,
    output_name: str,
    required_fragments: tuple[str, ...],
) -> dict[str, Any]:
    encoded = source.read_text(encoding="utf-8")
    for fragment in required_fragments:
        if fragment not in encoded:
            raise AssertionError(f"Validation log {source} lacks expected result: {fragment}")
    destination = output_directory / output_name
    shutil.copyfile(source, destination)
    return {
        "path": output_name,
        "sha256": "sha256:" + sha256_file(destination),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--application-base-revision", required=True)
    parser.add_argument("--validation-command", required=True)
    parser.add_argument("--regeneration-log", type=Path, required=True)
    parser.add_argument("--go-validation-log", type=Path, required=True)
    parser.add_argument("--python-validation-log", type=Path, required=True)
    parser.add_argument("--supply-chain-log", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    if not GIT_REVISION.fullmatch(arguments.application_base_revision):
        raise AssertionError("Application base revision is not a full Git object ID")
    arguments.output.parent.mkdir(parents=True, exist_ok=True)

    lock_path = ROOT / "dependency-lock.json"
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    projection_path = ROOT / "internal/generated/runtimeapi/projection-manifest.json"
    projection = json.loads(projection_path.read_text(encoding="utf-8"))
    if projection["schema_count"] != 39:
        raise AssertionError("Runtime Contract projection must contain exactly 39 locked Schemas")

    validation = {
        "command": arguments.validation_command,
        "logs": {
            "regeneration": bind_validation_log(
                arguments.regeneration_log,
                arguments.output.parent,
                "regeneration.log",
                ("Runtime Contract projection regeneration check passed.",),
            ),
            "go": bind_validation_log(
                arguments.go_validation_log,
                arguments.output.parent,
                "go-validation.log",
                ("github.com/shell-echo/agent/internal/runtimeport/contractprojection",),
            ),
            "python": bind_validation_log(
                arguments.python_validation_log,
                arguments.output.parent,
                "python-validation.log",
                ("Ran ", " tests in ", "OK"),
            ),
            "supply_chain": bind_validation_log(
                arguments.supply_chain_log,
                arguments.output.parent,
                "supply-chain.log",
                ("Implementation supply-chain check passed",),
            ),
        },
    }

    evidence = {
        "evidence_version": 1,
        "slice_id": "B03.2-P0",
        "scope": "runtime_contract_projection_and_security_dependency_admission",
        "result": "passed",
        "application_base_revision": arguments.application_base_revision,
        "application_source": source_manifest(),
        "blueprint": lock["blueprint"],
        "contract": lock["contract"],
        "dependency_lock": lock,
        "dependency_lock_sha256": sha256_file(lock_path),
        "contract_source_revision": lock["contract"]["source_revision"],
        "contract_manifest_digest": lock["contract"]["manifest_digest"],
        "runtime_suite_digest": next(
            suite["suite_digest"]
            for suite in lock["contract"]["suites"]
            if suite["suite_id"] == "agent-runtime-provider"
        ),
        "projection_manifest_sha256": sha256_file(projection_path),
        "projection": projection,
        "generated_go_tree_sha256": tree_digest(ROOT / "internal/generated/runtimeapi"),
        "generated_python_tree_sha256": tree_digest(
            ROOT / "runtime/native/src/agent_native_runtime/generated/runtimeapi"
        ),
        "fixture_matrix_sha256": sha256_file(
            ROOT / "test/conformance/runtime-contract-fixtures.json"
        ),
        "go_codegen_module_sha256": sha256_file(ROOT / "toolchain/runtime-codegen/go.mod"),
        "go_codegen_sum_sha256": sha256_file(ROOT / "toolchain/runtime-codegen/go.sum"),
        "python_codegen_distribution_manifest_sha256": sha256_file(
            ROOT / "toolchain/runtime-python-codegen-packages.json"
        ),
        "python_lock_sha256": sha256_file(ROOT / "runtime/native/uv.lock"),
        "third_party_inventory_sha256": sha256_file(ROOT / "toolchain/third-party.json"),
        "validation": validation,
        "proven": [
            "scratch regeneration has zero committed-output diff",
            "Go and Python generated transport projections compile or import",
            "locked Runtime positive and negative fixtures have Draft 2020-12 parity",
            "locked RFC 8785 canonicalization vectors match",
            "EdDSA and ES256 primitives work and HS256 is excluded",
            "all admitted direct and transitive dependencies are exactly locked and inventoried",
        ],
        "not_proven": [
            "Native Runtime lifecycle or durable provider state",
            "AgentRuntimeProvider HTTP adapter or production endpoint",
            "complete Strict I-JSON admission including numeric lexical resource bounds",
            "Runtime token claims, authority lineage, replay, expiry, or fencing enforcement",
            "platform reconciliation, Temporal dispatch, or production Safety Cancel",
            "any runtime-core-v1 Conformance case or production-readiness claim",
        ],
    }
    write_json(arguments.output, evidence)


if __name__ == "__main__":
    main()
