#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SHA256 = re.compile(r"^[0-9a-f]{64}$")
BUILD_PROVENANCE_KEYS = {
    "source_revision",
    "source_tree_digest",
    "build_artifact_digest",
    "sbom_digest",
    "provenance_statement_digest",
    "build_system",
}
COMPONENTS = {
    "agent-access": {
        "artifact_name": "agent-access-linux-arm64",
        "build_system": "go1.26.5 linux/arm64",
        "toolchain_keys": ["GO_TOOLCHAIN_IMAGE"],
        "source_files": ["go.mod", "go.sum", "script/validate_implementation.sh"],
        "source_directories": ["cmd/agent-access", "internal/agentaccess"],
    },
    "native-runtime": {
        "artifact_name": "agent-platform-native-runtime-wheel",
        "build_system": "uv0.11.30+hatchling1.31.0+python3.14.6",
        "toolchain_keys": ["PYTHON_TOOLCHAIN_IMAGE", "UV_BINARY_IMAGE"],
        "source_files": [
            "toolchain/uv-toolchain.Dockerfile",
            "runtime/native/build-constraints.txt",
            "runtime/native/pyproject.toml",
            "runtime/native/uv.lock",
            "script/validate_implementation.sh",
        ],
        "source_directories": ["runtime/native/src", "runtime/native/test"],
    },
}
COMMON_SOURCE_FILES = [
    "dependency-lock.json",
    "toolchain/third-party.json",
    "toolchain/toolchain.env",
    "script/check_implementation_supply_chain.py",
    "script/generate_implementation_evidence.py",
    "script/verify_dependency_lock.py",
    "script/verify_phase0_traceability.py",
    "test/traceability/phase0-implementation-evidence.json",
]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as artifact:
        for chunk in iter(lambda: artifact.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def load_env(path: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if line and not line.startswith("#"):
            key, separator, value = line.partition("=")
            if separator != "=" or not key or not value:
                raise AssertionError(f"Invalid toolchain entry: {raw_line}")
            result[key] = value
    return result


def source_paths(component: dict[str, Any]) -> list[Path]:
    paths = [ROOT / relative for relative in COMMON_SOURCE_FILES + component["source_files"]]
    for relative in component["source_directories"]:
        paths.extend(path for path in (ROOT / relative).rglob("*") if path.is_file())
    return sorted(set(paths), key=lambda path: path.relative_to(ROOT).as_posix())


def source_tree_digest(paths: list[Path]) -> str:
    digest = hashlib.sha256()
    for path in paths:
        relative = path.relative_to(ROOT).as_posix().encode("utf-8")
        content = path.read_bytes()
        digest.update(len(relative).to_bytes(8, "big"))
        digest.update(relative)
        digest.update(len(content).to_bytes(8, "big"))
        digest.update(content)
    return digest.hexdigest()


def spdx_id(name: str) -> str:
    return "SPDXRef-" + re.sub(r"[^A-Za-z0-9.-]", "-", name)


def create_sbom(component_name: str, source_digest: str, inventory: list[dict[str, Any]]) -> dict[str, Any]:
    root_id = spdx_id(component_name)
    packages = [
        {
            "SPDXID": root_id,
            "name": component_name,
            "versionInfo": "0.1.0",
            "downloadLocation": "NOASSERTION",
            "filesAnalyzed": False,
            "licenseConcluded": "NOASSERTION",
            "licenseDeclared": "NOASSERTION",
        }
    ]
    relationships: list[dict[str, str]] = []
    for dependency in sorted(inventory, key=lambda item: item["purl"]):
        dependency_id = spdx_id(dependency["name"])
        packages.append(
            {
                "SPDXID": dependency_id,
                "name": dependency["name"],
                "versionInfo": dependency["version"],
                "downloadLocation": dependency["source"],
                "filesAnalyzed": False,
                "licenseConcluded": dependency["license"],
                "licenseDeclared": dependency["license"],
                "externalRefs": [
                    {
                        "referenceCategory": "PACKAGE-MANAGER",
                        "referenceType": "purl",
                        "referenceLocator": dependency["purl"],
                    }
                ],
            }
        )
        relationships.append(
            {
                "spdxElementId": dependency_id,
                "relationshipType": "BUILD_DEPENDENCY_OF",
                "relatedSpdxElement": root_id,
            }
        )
    return {
        "spdxVersion": "SPDX-2.3",
        "dataLicense": "CC0-1.0",
        "SPDXID": "SPDXRef-DOCUMENT",
        "name": f"{component_name}-b01",
        "documentNamespace": f"https://agent-platform.invalid/spdx/{component_name}/{source_digest}",
        "creationInfo": {
            "created": "2000-01-01T00:00:00Z",
            "creators": ["Tool: agent-platform-b01-evidence-generator"],
        },
        "packages": packages,
        "relationships": relationships,
    }


def image_material(image: str) -> dict[str, Any]:
    uri, separator, digest = image.partition("@sha256:")
    if separator != "@sha256:" or not SHA256.fullmatch(digest):
        raise AssertionError(f"Toolchain image is not digest-pinned: {image}")
    return {"uri": f"pkg:docker/{uri}", "digest": {"sha256": digest}}


def governed_materials(lock: dict[str, Any], lock_digest: str) -> list[dict[str, Any]]:
    materials = [
        {
            "uri": "urn:agent-platform:application-dependency-lock:v1",
            "digest": {"sha256": lock_digest},
        },
        {
            "uri": "urn:agent-platform:blueprint:governed-source-snapshot",
            "digest": {"sha256": lock["blueprint"]["source_revision"]},
        },
        {
            "uri": "urn:agent-platform:contract:governed-source-snapshot",
            "digest": {"sha256": lock["contract"]["source_revision"]},
        },
        {
            "uri": "urn:agent-platform:contract:manifest",
            "digest": {"sha256": lock["contract"]["manifest_digest"].removeprefix("sha256:")},
        },
    ]
    for suite in lock["contract"]["suites"]:
        profiles = ",".join(suite["profiles"])
        materials.append(
            {
                "uri": (
                    "urn:agent-platform:contract:conformance-suite:"
                    f"{suite['suite_id']}:{suite['suite_version']}?profiles={profiles}"
                ),
                "digest": {"sha256": suite["suite_digest"].removeprefix("sha256:")},
            }
        )
    return materials


def create_provenance(
    component_name: str,
    artifact_name: str,
    artifact_digest: str,
    source_digest: str,
    build_system: str,
    toolchain_images: list[str],
    inventory: list[dict[str, Any]],
    upstream_materials: list[dict[str, Any]],
    target: str,
) -> dict[str, Any]:
    materials = [
        {
            "uri": f"urn:agent-platform:source-snapshot:{source_digest}",
            "digest": {"sha256": source_digest},
        }
    ]
    materials.extend(upstream_materials)
    materials.extend(image_material(image) for image in toolchain_images)
    materials.extend({"uri": dependency["purl"]} for dependency in sorted(inventory, key=lambda item: item["purl"]))
    return {
        "_type": "https://in-toto.io/Statement/v1",
        "subject": [{"name": artifact_name, "digest": {"sha256": artifact_digest}}],
        "predicateType": "https://slsa.dev/provenance/v1",
        "predicate": {
            "buildDefinition": {
                "buildType": "https://agent-platform.invalid/build-types/phase0-b01/v1",
                "externalParameters": {
                    "component": component_name,
                    "buildSystem": build_system,
                    "sourceDateEpoch": 946684800,
                    "sourceRevision": source_digest,
                    "target": target,
                },
                "internalParameters": {},
                "resolvedDependencies": materials,
            },
            "runDetails": {
                "builder": {"id": "urn:agent-platform:builder:phase0-b01"},
                "metadata": {"invocationId": source_digest},
            },
        },
    }


def verify_component_evidence(
    component_name: str,
    artifact: Path,
    source_digest: str,
    output_dir: Path,
) -> dict[str, str]:
    artifact_digest = sha256_file(artifact)
    sbom_path = output_dir / f"{component_name}.spdx.json"
    statement_path = output_dir / f"{component_name}.provenance.json"
    record_path = output_dir / f"{component_name}.build-provenance.json"
    sbom = json.loads(sbom_path.read_text(encoding="utf-8"))
    statement = json.loads(statement_path.read_text(encoding="utf-8"))
    record = json.loads(record_path.read_text(encoding="utf-8"))

    if set(record) != BUILD_PROVENANCE_KEYS:
        raise AssertionError(f"{component_name} BuildProvenance fields differ from the v1 contract")
    if record["source_revision"] != source_digest or record["source_tree_digest"] != f"sha256:{source_digest}":
        raise AssertionError(f"{component_name} source snapshot digest mismatch")
    if record["build_artifact_digest"] != f"sha256:{artifact_digest}":
        raise AssertionError(f"{component_name} artifact digest mismatch")
    if record["sbom_digest"] != f"sha256:{sha256_file(sbom_path)}":
        raise AssertionError(f"{component_name} SBOM digest mismatch")
    if record["provenance_statement_digest"] != f"sha256:{sha256_file(statement_path)}":
        raise AssertionError(f"{component_name} provenance statement digest mismatch")
    if sbom.get("spdxVersion") != "SPDX-2.3" or sbom.get("dataLicense") != "CC0-1.0":
        raise AssertionError(f"{component_name} SBOM is not SPDX 2.3")
    if statement.get("predicateType") != "https://slsa.dev/provenance/v1":
        raise AssertionError(f"{component_name} provenance is not SLSA v1")
    expected_subject = [
        {
            "name": COMPONENTS[component_name]["artifact_name"],
            "digest": {"sha256": artifact_digest},
        }
    ]
    if statement["subject"] != expected_subject:
        raise AssertionError(f"{component_name} provenance subject mismatch")
    return {
        "artifact": artifact.name,
        "artifact_digest": f"sha256:{artifact_digest}",
        "build_provenance": record_path.name,
        "build_provenance_digest": f"sha256:{sha256_file(record_path)}",
        "provenance_statement": statement_path.name,
        "sbom": sbom_path.name,
        "source_tree_digest": f"sha256:{source_digest}",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--agent-access-artifact", type=Path, required=True)
    parser.add_argument("--dependency-lock", type=Path, required=True)
    parser.add_argument("--native-runtime-artifact", type=Path, required=True)
    parser.add_argument("--traceability-map", type=Path, required=True)
    parser.add_argument("--traceability-report", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    artifacts = {
        "agent-access": args.agent_access_artifact,
        "native-runtime": args.native_runtime_artifact,
    }
    for path in artifacts.values():
        if not path.is_file():
            raise AssertionError(f"Build artifact is missing: {path}")
    for path in (args.dependency_lock, args.traceability_map, args.traceability_report):
        if not path.is_file():
            raise AssertionError(f"Governed evidence input is missing: {path}")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    lock = json.loads(args.dependency_lock.read_text(encoding="utf-8"))
    lock_digest = sha256_file(args.dependency_lock)
    upstream_materials = governed_materials(lock, lock_digest)
    traceability_report = json.loads(args.traceability_report.read_text(encoding="utf-8"))
    if traceability_report["dependency_lock_digest"] != f"sha256:{lock_digest}":
        raise AssertionError("Traceability report is not bound to the dependency lock")

    dependency_lock_evidence = args.output_dir / "dependency-lock.json"
    traceability_map_evidence = args.output_dir / "phase0-implementation-evidence-map.json"
    traceability_report_evidence = args.output_dir / "phase0-implementation-traceability.json"
    dependency_lock_evidence.write_bytes(args.dependency_lock.read_bytes())
    traceability_map_evidence.write_bytes(args.traceability_map.read_bytes())
    traceability_report_bytes = args.traceability_report.read_bytes()
    traceability_report_evidence.write_bytes(traceability_report_bytes)

    toolchain = load_env(ROOT / "toolchain/toolchain.env")
    inventory_path = ROOT / "toolchain/third-party.json"
    inventory = json.loads(inventory_path.read_text(encoding="utf-8"))["components"]
    manifest_components: dict[str, dict[str, str]] = {}

    for component_name, component in COMPONENTS.items():
        component_inventory = [item for item in inventory if component_name in item["components"]]
        snapshot_digest = source_tree_digest(source_paths(component))
        artifact_digest = sha256_file(artifacts[component_name])
        sbom = create_sbom(component_name, snapshot_digest, component_inventory)
        sbom_path = args.output_dir / f"{component_name}.spdx.json"
        write_json(sbom_path, sbom)
        statement = create_provenance(
            component_name,
            component["artifact_name"],
            artifact_digest,
            snapshot_digest,
            component["build_system"],
            [toolchain[key] for key in component["toolchain_keys"]],
            component_inventory,
            upstream_materials,
            "linux/arm64" if component_name == "agent-access" else "py3-none-any",
        )
        statement_path = args.output_dir / f"{component_name}.provenance.json"
        write_json(statement_path, statement)
        record = {
            "source_revision": snapshot_digest,
            "source_tree_digest": f"sha256:{snapshot_digest}",
            "build_artifact_digest": f"sha256:{artifact_digest}",
            "sbom_digest": f"sha256:{sha256_file(sbom_path)}",
            "provenance_statement_digest": f"sha256:{sha256_file(statement_path)}",
            "build_system": component["build_system"],
        }
        write_json(args.output_dir / f"{component_name}.build-provenance.json", record)
        manifest_components[component_name] = verify_component_evidence(
            component_name,
            artifacts[component_name],
            snapshot_digest,
            args.output_dir,
        )

    manifest = {
        "schema_version": 1,
        "governed_inputs": {
            "dependency_lock": {
                "artifact": dependency_lock_evidence.name,
                "digest": f"sha256:{sha256_file(dependency_lock_evidence)}",
                "blueprint": lock["blueprint"],
                "contract": lock["contract"],
            },
            "phase0_implementation_evidence_map": {
                "artifact": traceability_map_evidence.name,
                "digest": f"sha256:{sha256_file(traceability_map_evidence)}",
            },
            "phase0_implementation_traceability": {
                "artifact": traceability_report_evidence.name,
                "digest": f"sha256:{sha256_file(traceability_report_evidence)}",
                "summary": traceability_report["summary"],
            },
        },
        "components": manifest_components,
    }
    write_json(args.output_dir / "manifest.json", manifest)
    print(
        "Generated and verified locked upstream materials, Phase 0 traceability, "
        "SPDX 2.3, SLSA v1, and BuildProvenance evidence for 2 B01 artifacts."
    )


if __name__ == "__main__":
    main()
