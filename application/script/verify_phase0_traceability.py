#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
CONTRACT_ROOT = Path(
    os.environ.get("AGENT_CONTRACT_ROOT", ROOT.parent / "contract")
).resolve()
LOCK_PATH = ROOT / "dependency-lock.json"
SEMANTIC_CONSTRAINTS_PATH = CONTRACT_ROOT / "semantic-constraints-v1.json"
MANIFEST_PATH = CONTRACT_ROOT / "compatibility/contract-manifest.json"
ALLOWED_EVIDENCE_TYPES = {
    "migration",
    "repository_test",
    "component_test",
    "conformance_test",
    "integration_test",
    "replay_test",
    "fault_test",
}
IMPLEMENTATION_EXTENSIONS = {
    ".go",
    ".json",
    ".py",
    ".sql",
    ".ts",
    ".tsx",
    ".yaml",
    ".yml",
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def application_file(relative: str) -> Path:
    if not relative or Path(relative).is_absolute():
        raise AssertionError(f"Evidence path must be Application-relative: {relative!r}")
    path = (ROOT / relative).resolve()
    if not path.is_relative_to(ROOT) or not path.is_file():
        raise AssertionError(f"Evidence file is missing or outside Application: {relative}")
    if path.suffix not in IMPLEMENTATION_EXTENSIONS or path.name.lower().startswith("readme"):
        raise AssertionError(f"Evidence must be implementation or executable test source: {relative}")
    return path


def phase0_mappings(constraints: dict[str, Any]) -> list[dict[str, Any]]:
    mappings: list[dict[str, Any]] = []
    identities: set[tuple[str, str, str, str]] = set()
    for constraint in constraints["constraints"]:
        for enforcement in constraint["enforcements"]:
            if enforcement["status"] != "phase0_implementation_required":
                continue
            identity = (
                constraint["constraint_id"],
                enforcement["kind"],
                enforcement["artifact"],
                enforcement["check_id"],
            )
            if identity in identities:
                raise AssertionError(f"Duplicate Phase 0 mapping: {identity}")
            identities.add(identity)
            mappings.append(
                {
                    "artifact": enforcement["artifact"],
                    "check_id": enforcement["check_id"],
                    "constraint_id": constraint["constraint_id"],
                    "enforcement_kind": enforcement["kind"],
                    "schema_id": constraint["schema_id"],
                    "statement": constraint["statement"],
                }
            )
    return sorted(
        mappings,
        key=lambda item: (
            item["check_id"],
            item["constraint_id"],
            item["enforcement_kind"],
            item["artifact"],
        ),
    )


def validate_contract_suite_references(mappings: list[dict[str, Any]]) -> None:
    suite_test_ids: dict[str, set[str]] = {}
    for mapping in mappings:
        artifact = mapping["artifact"]
        if mapping["enforcement_kind"] != "conformance_test" or not artifact.endswith("suite.json"):
            continue
        if artifact not in suite_test_ids:
            suite = json.loads((CONTRACT_ROOT / artifact).read_text(encoding="utf-8"))
            suite_test_ids[artifact] = {
                test["test_id"]
                for profile in suite["profiles"]
                for test in profile["tests"]
            }
        if mapping["check_id"] not in suite_test_ids[artifact]:
            raise AssertionError(
                f"Contract mapping {mapping['check_id']} is absent from {artifact}"
            )


def validate_claims(
    evidence_map: dict[str, Any],
    mappings: list[dict[str, Any]],
    lock: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    if set(evidence_map) != {"schema_version", "claims"} or evidence_map["schema_version"] != 1:
        raise AssertionError("Implementation evidence map shape is invalid")
    if not isinstance(evidence_map["claims"], list):
        raise AssertionError("Implementation evidence claims must be an array")

    mapped_checks = {mapping["check_id"] for mapping in mappings}
    locked_suites = {suite["path"]: suite for suite in lock["contract"]["suites"]}
    claims: dict[str, dict[str, Any]] = {}
    for claim in evidence_map["claims"]:
        if set(claim) != {"check_id", "status", "evidence"}:
            raise AssertionError("Implementation claim shape is invalid")
        check_id = claim["check_id"]
        if check_id not in mapped_checks:
            raise AssertionError(f"Claim references an unknown Phase 0 check: {check_id}")
        if check_id in claims:
            raise AssertionError(f"Duplicate implementation claim: {check_id}")
        if claim["status"] != "implemented" or not claim["evidence"]:
            raise AssertionError(f"Claim {check_id} must be implemented and carry evidence")

        resolved_evidence: list[dict[str, Any]] = []
        evidence_types: set[str] = set()
        conformance_case_ids: set[str] = set()
        for evidence in claim["evidence"]:
            if set(evidence) != {"evidence_type", "path", "case_ids"}:
                raise AssertionError(f"Evidence shape is invalid for {check_id}")
            evidence_type = evidence["evidence_type"]
            if evidence_type not in ALLOWED_EVIDENCE_TYPES:
                raise AssertionError(f"Unsupported evidence type for {check_id}: {evidence_type}")
            if not isinstance(evidence["case_ids"], list) or len(evidence["case_ids"]) != len(
                set(evidence["case_ids"])
            ):
                raise AssertionError(f"Evidence case IDs must be a unique array for {check_id}")
            path = application_file(evidence["path"])
            evidence_types.add(evidence_type)
            if evidence_type == "conformance_test":
                conformance_case_ids.update(evidence["case_ids"])
            resolved_evidence.append(
                {
                    **evidence,
                    "digest": f"sha256:{sha256_file(path)}",
                }
            )

        check_mappings = [mapping for mapping in mappings if mapping["check_id"] == check_id]
        if any(mapping["enforcement_kind"] == "ddl_responsibility" for mapping in check_mappings):
            required = {"migration", "integration_test"}
            if not required <= evidence_types:
                raise AssertionError(
                    f"DDL claim {check_id} requires migration and integration_test evidence"
                )
        if any(mapping["enforcement_kind"] == "conformance_test" for mapping in check_mappings):
            if "conformance_test" not in evidence_types or check_id not in conformance_case_ids:
                raise AssertionError(
                    f"Conformance claim {check_id} requires a matching conformance_test case ID"
                )
            for mapping in check_mappings:
                artifact = mapping["artifact"]
                if not artifact.endswith("suite.json"):
                    continue
                if artifact not in locked_suites:
                    raise AssertionError(
                        f"Conformance claim {check_id} requires locked Suite {artifact}"
                    )
                suite = json.loads((CONTRACT_ROOT / artifact).read_text(encoding="utf-8"))
                profile_tests = {
                    profile["profile_id"]: {test["test_id"] for test in profile["tests"]}
                    for profile in suite["profiles"]
                }
                locked_test_ids = set().union(
                    *(profile_tests[profile] for profile in locked_suites[artifact]["profiles"])
                )
                if check_id not in locked_test_ids:
                    raise AssertionError(
                        f"Conformance claim {check_id} is outside the locked profiles for {artifact}"
                    )

        claims[check_id] = {
            "check_id": check_id,
            "status": "implemented",
            "evidence": resolved_evidence,
        }
    return claims


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--evidence-map",
        type=Path,
        default=ROOT / "test/traceability/phase0-implementation-evidence.json",
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    lock = json.loads(LOCK_PATH.read_text(encoding="utf-8"))
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    if manifest["manifest_digest"] != lock["contract"]["manifest_digest"]:
        raise AssertionError("Contract Manifest differs from the verified dependency lock")

    constraints = json.loads(SEMANTIC_CONSTRAINTS_PATH.read_text(encoding="utf-8"))
    mappings = phase0_mappings(constraints)
    validate_contract_suite_references(mappings)
    evidence_map = json.loads(args.evidence_map.read_text(encoding="utf-8"))
    claims = validate_claims(evidence_map, mappings, lock)

    report_mappings = [
        {
            **mapping,
            "implementation_status": (
                "implemented" if mapping["check_id"] in claims else "unimplemented"
            ),
        }
        for mapping in mappings
    ]
    check_ids = sorted({mapping["check_id"] for mapping in mappings})
    unimplemented = [check_id for check_id in check_ids if check_id not in claims]
    report = {
        "schema_version": 1,
        "dependency_lock_digest": f"sha256:{sha256_file(LOCK_PATH)}",
        "contract_manifest_digest": manifest["manifest_digest"],
        "semantic_constraints": {
            "path": "semantic-constraints-v1.json",
            "digest": f"sha256:{sha256_file(SEMANTIC_CONSTRAINTS_PATH)}",
            "traceability_id": constraints["traceability_id"],
            "version": constraints["version"],
        },
        "evidence_map_digest": f"sha256:{sha256_file(args.evidence_map)}",
        "summary": {
            "required_mapping_count": len(mappings),
            "required_unique_check_count": len(check_ids),
            "implemented_mapping_count": len(mappings) - sum(
                check_id in unimplemented for check_id in (item["check_id"] for item in mappings)
            ),
            "implemented_unique_check_count": len(claims),
            "unimplemented_mapping_count": sum(
                check_id in unimplemented for check_id in (item["check_id"] for item in mappings)
            ),
            "unimplemented_unique_check_count": len(unimplemented),
        },
        "claims": [claims[check_id] for check_id in sorted(claims)],
        "unimplemented_check_ids": unimplemented,
        "mappings": report_mappings,
    }
    write_json(args.output, report)
    print(
        "Phase 0 traceability verified: "
        f"{len(mappings)} mappings, {len(check_ids)} unique checks, "
        f"{len(claims)} implemented checks, {len(unimplemented)} unimplemented checks."
    )


if __name__ == "__main__":
    main()
