#!/usr/bin/env python3
from __future__ import annotations

import copy
import ast
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

import rfc8785
import yaml

SCRIPT_ROOT = Path(__file__).resolve().parents[2]
CONTRACT_ROOT = Path(
    os.environ.get("AGENT_CONTRACT_ROOT", SCRIPT_ROOT.parent / "contract")
).resolve()
AGENT_RUN_RESOURCE_LIMIT_NAMES = (
    "max_input_tokens",
    "max_output_tokens",
    "max_model_requests",
    "max_sandbox_seconds",
    "max_network_bytes",
    "max_storage_bytes",
    "max_artifact_count",
    "max_conversion_count",
)


def read(relative: str) -> dict[str, Any]:
    return json.loads((CONTRACT_ROOT / relative).read_text(encoding="utf-8"))


def write(relative: str, value: dict[str, Any]) -> None:
    (CONTRACT_ROOT / relative).write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def read_yaml(relative: str) -> dict[str, Any]:
    return yaml.safe_load((CONTRACT_ROOT / relative).read_text(encoding="utf-8"))


def write_yaml(relative: str, value: dict[str, Any]) -> None:
    (CONTRACT_ROOT / relative).write_text(
        yaml.safe_dump(value, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )


def digest(value: Any) -> str:
    return "sha256:" + hashlib.sha256(rfc8785.dumps(value)).hexdigest()


def digest_without(value: dict[str, Any], field: str) -> str:
    unsigned = copy.deepcopy(value)
    unsigned.pop(field, None)
    return digest(unsigned)


def file_digest(relative: str) -> str:
    return "sha256:" + hashlib.sha256((CONTRACT_ROOT / relative).read_bytes()).hexdigest()


def bytes_digest(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


_C01_ACTIVE_SUITE = "conformance/runtime/v1/suite.json"
_C01_HISTORICAL_SUITE = "conformance/runtime/v1/revisions/1.0.0/suite.json"
_C01_ACTIVE_OPENAPI = "openapi/agent-runtime-provider-v1.yaml"
_C01_HISTORICAL_OPENAPI = "openapi/agent-runtime-provider-v1.0.0.snapshot.yaml"
_C01_HISTORICAL_SUITE_RAW_SHA256 = (
    "268ff34c549e01f223201262f2dab96d2718146aea383a8180d8cbf26a52eb44"
)
_C01_HISTORICAL_SUITE_DIGEST = (
    "sha256:9ef6d50df9f1032476ea2ada2c16d70c15d88368acf59794062df7dfce0bb356"
)
_C01_HISTORICAL_OPENAPI_SHA256 = (
    "f75bd9484d9059435021f65147cab1a22b4cb0376ea47ce6e165fde0494f5811"
)
_C01_RUNTIME_READ_CHECK = "runtime_read.http_authority"
_C01_MANIFEST_PENDING_PATHS = {
    "schemas/agent-runtime-read-bad-request-error.schema.json",
    "schemas/agent-runtime-read-throttled-error.schema.json",
    _C01_HISTORICAL_SUITE,
    _C01_HISTORICAL_OPENAPI,
}


def _c01_tree_hashes(root: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(item for item in root.rglob("*") if item.is_file())
    }


def _c01_manifest_inventory_paths(root: Path) -> set[str]:
    paths = [
        *sorted((root / "schemas").glob("*.json")),
        *sorted((root / "examples/schemas").glob("*.json")),
        *sorted((root / "openapi").glob("*.yaml")),
        *sorted((root / "state-machines").glob("*.json")),
        *sorted((root / "event-types").rglob("*.json")),
        *sorted((root / "conformance").rglob("*.json")),
        *sorted((root / "testdata").rglob("*")),
    ]
    return {path.relative_to(root).as_posix() for path in paths if path.is_file()}


def _c01_validate_manifest_preimage(root: Path) -> None:
    manifest = read_from(root, "compatibility/contract-manifest.json")
    listed = {resource["path"] for resource in manifest["resources"]}
    if manifest.get("resource_count") != len(manifest["resources"]) or len(listed) != len(manifest["resources"]):
        raise AssertionError("C01 Manifest declared/listed inventory is internally inconsistent")
    discovered = _c01_manifest_inventory_paths(root)
    if discovered - listed != _C01_MANIFEST_PENDING_PATHS or listed - discovered:
        raise AssertionError("C01 Manifest pre-finalize drift is not the reviewed four-path pending set")


def read_from(root: Path, relative: str) -> dict[str, Any]:
    return json.loads((root / relative).read_text(encoding="utf-8"))


def _c01_stable_constraint_id(entry: dict[str, Any]) -> str:
    material = f"{entry['schema_id']}\n{entry['constraint_index']}\n{entry['statement']}".encode()
    return "sem-" + hashlib.sha256(material).hexdigest()[:16]


def _c01_validator_marks_runtime_read(script_root: Path) -> None:
    path = script_root / "contract/validation/validate_semantics.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    known = False
    marks = False
    top_level_executes = False
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "KNOWN_CONTRACT_CHECKS"
            for target in node.targets
        ):
            known = any(
                isinstance(child, ast.Constant) and child.value == _C01_RUNTIME_READ_CHECK
                for child in ast.walk(node.value)
            )
        if isinstance(node, ast.FunctionDef) and node.name == "validate_c01_runtime_read_semantics":
            marks = any(
                isinstance(child, ast.Call)
                and isinstance(child.func, ast.Attribute)
                and child.func.attr == "add"
                and any(
                    isinstance(argument, ast.Name) and argument.id == "_C01_RUNTIME_READ_CHECK"
                    for argument in child.args
                )
                for child in ast.walk(node)
            )
    for node in tree.body:
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
            function = node.value.func
            if isinstance(function, ast.Name) and function.id == "validate_c01_runtime_read_semantics":
                top_level_executes = True
    if not (known and marks and top_level_executes):
        raise AssertionError("C01 semantic check is not known, marked, and executed by the normal Gate")


def _c01_supplemental_traceability(root: Path, script_root: Path) -> list[dict[str, Any]]:
    _c01_validator_marks_runtime_read(script_root)
    schemas: dict[str, dict[str, Any]] = {}
    for path in sorted((root / "schemas").glob("*.json")):
        schema = read_from(root, path.relative_to(root).as_posix())
        if schema["$id"] in schemas:
            raise AssertionError("C01 semantic Schema ID collision")
        schemas[schema["$id"]] = schema
    traceability = read_from(root, "semantic-constraints-v1.json")
    expected_critical = {
        schema_id for schema_id, schema in schemas.items()
        if schema.get("x-semantic-constraints")
    }
    declared_critical = traceability.get("critical_schema_ids", [])
    if len(declared_critical) != len(set(declared_critical)) or set(declared_critical) != expected_critical:
        raise AssertionError("C01 semantic critical_schema_ids drift")
    generated = {
        (schema_id, index): statement
        for schema_id in declared_critical
        for index, statement in enumerate(schemas[schema_id]["x-semantic-constraints"])
    }
    ids: set[str] = set()
    coordinates: set[tuple[str, int]] = set()
    critical_seen: set[tuple[str, int]] = set()
    supplemental: list[dict[str, Any]] = []
    for entry in traceability.get("constraints", []):
        if set(entry) != {"constraint_id", "schema_id", "constraint_index", "statement", "enforcements"}:
            raise AssertionError("C01 semantic traceability entry shape drift")
        if entry["schema_id"] not in schemas or entry["constraint_id"] != _c01_stable_constraint_id(entry):
            raise AssertionError("C01 semantic traceability unresolved Schema or stable ID drift")
        coordinate = (entry["schema_id"], entry["constraint_index"])
        if entry["constraint_id"] in ids or coordinate in coordinates:
            raise AssertionError("C01 semantic traceability ID/coordinate collision")
        ids.add(entry["constraint_id"])
        coordinates.add(coordinate)
        if coordinate in generated:
            if entry["statement"] != generated[coordinate]:
                raise AssertionError("C01 critical semantic statement drift")
            critical_seen.add(coordinate)
        else:
            if entry["schema_id"] in expected_critical:
                raise AssertionError("C01 damaged critical entry cannot be classified as supplemental")
            supplemental.append(copy.deepcopy(entry))
        for enforcement in entry["enforcements"]:
            if set(enforcement) != {"kind", "artifact", "check_id", "status"}:
                raise AssertionError("C01 supplemental enforcement shape drift")
            artifact = enforcement["artifact"]
            if artifact.startswith("urn:agent-platform:contract-validation:"):
                if enforcement["check_id"] != _C01_RUNTIME_READ_CHECK and entry in supplemental:
                    raise AssertionError("C01 supplemental Contract Gate check drift")
            elif artifact.startswith("urn:agent-platform:blueprint:"):
                continue
            elif not (root / artifact).is_file():
                raise AssertionError("C01 semantic enforcement artifact is unresolved")
    if critical_seen != set(generated):
        raise AssertionError("C01 semantic traceability lost a generated critical constraint")
    if [entry["schema_id"] for entry in supplemental] != [
        "urn:agent-platform:agent-runtime-read-bad-request-error:v1",
        "urn:agent-platform:agent-runtime-read-throttled-error:v1",
    ]:
        raise AssertionError("C01 supplemental traceability ordered set drift")
    return supplemental


def _c01_validate_immutable_registry(root: Path) -> dict[str, Any]:
    suite_path = root / _C01_HISTORICAL_SUITE
    openapi_path = root / _C01_HISTORICAL_OPENAPI
    if hashlib.sha256(suite_path.read_bytes()).hexdigest() != _C01_HISTORICAL_SUITE_RAW_SHA256:
        raise AssertionError("C01 historical Runtime Suite snapshot byte drift")
    suite = read_from(root, _C01_HISTORICAL_SUITE)
    if (
        suite.get("suite_id"), suite.get("suite_version"), suite.get("suite_digest")
    ) != ("agent-runtime-provider", "1.0.0", _C01_HISTORICAL_SUITE_DIGEST):
        raise AssertionError("C01 historical Runtime Suite tuple drift")
    if digest_without(suite, "suite_digest") != suite["suite_digest"]:
        raise AssertionError("C01 historical Runtime Suite self-digest drift")
    if hashlib.sha256(openapi_path.read_bytes()).hexdigest() != _C01_HISTORICAL_OPENAPI_SHA256:
        raise AssertionError("C01 historical Runtime OpenAPI snapshot byte drift")
    if read_yaml_from(root, _C01_HISTORICAL_OPENAPI).get("info", {}).get("version") != "1.0.0":
        raise AssertionError("C01 historical Runtime OpenAPI version drift")
    return suite


def read_yaml_from(root: Path, relative: str) -> dict[str, Any]:
    return yaml.safe_load((root / relative).read_text(encoding="utf-8"))


def _c01_reject_active_passed_facts(root: Path, active_digest: str) -> None:
    def walk(value: Any):
        if isinstance(value, dict):
            yield value
            for child in value.values():
                yield from walk(child)
        elif isinstance(value, list):
            for child in value:
                yield from walk(child)
    for path in sorted((root / "examples/contracts").glob("*.json")):
        for item in walk(read_from(root, path.relative_to(root).as_posix())):
            if (
                item.get("suite_id") == "agent-runtime-provider"
                and item.get("suite_version") == "1.0.1"
                and item.get("suite_digest") == active_digest
                and item.get("result") in {"passed", "certified"}
            ):
                raise AssertionError("C01 active 1.0.1 Suite is represented as passed/certified")


def _c01_validate_historical_fact_bindings(root: Path) -> None:
    historical_suite = (
        "agent-runtime-provider", "1.0.0", _C01_HISTORICAL_SUITE_DIGEST,
    )
    historical_port = (
        "agent-runtime-provider", "v1", "sha256:" + _C01_HISTORICAL_OPENAPI_SHA256,
    )

    def walk(value: Any):
        if isinstance(value, dict):
            yield value
            for child in value.values():
                yield from walk(child)
        elif isinstance(value, list):
            for child in value:
                yield from walk(child)

    suite_facts = 0
    port_facts = 0
    for path in sorted((root / "examples/contracts").glob("*.json")):
        for item in walk(read_from(root, path.relative_to(root).as_posix())):
            if item.get("suite_id") == "agent-runtime-provider" and {
                "suite_version", "suite_digest",
            } <= set(item):
                suite_facts += 1
                if (item["suite_id"], item["suite_version"], item["suite_digest"]) != historical_suite:
                    raise AssertionError(f"C01 historical Runtime Suite fact was rebound: {path.name}")
            if item.get("protocol") == "agent-runtime-provider" and {
                "protocol_version", "contract_digest",
            } <= set(item):
                port_facts += 1
                if (item["protocol"], item["protocol_version"], item["contract_digest"]) != historical_port:
                    raise AssertionError(f"C01 historical Runtime Port fact was rebound: {path.name}")
    if suite_facts == 0 or port_facts == 0:
        raise AssertionError("C01 historical Runtime fact closure was not discovered")


def _c01_finalize_active_suite(root: Path, script_root: Path) -> set[str]:
    _c01_validate_manifest_preimage(root)
    _c01_validate_immutable_registry(root)
    _c01_validate_historical_fact_bindings(root)
    _c01_supplemental_traceability(root, script_root)
    before = _c01_tree_hashes(root)
    suite_path = root / _C01_ACTIVE_SUITE
    suite = read_from(root, _C01_ACTIVE_SUITE)
    if suite.get("suite_id") != "agent-runtime-provider" or suite.get("suite_version") != "1.0.1":
        raise AssertionError("C01 active Runtime Suite identity/version drift")
    candidate = copy.deepcopy(suite)
    candidate["suite_digest"] = digest_without(candidate, "suite_digest")
    _c01_reject_active_passed_facts(root, candidate["suite_digest"])
    candidate_bytes = (json.dumps(candidate, indent=2, ensure_ascii=False) + "\n").encode()
    temporary = suite_path.with_name(f".{suite_path.name}.c01-{os.getpid()}")
    original_bytes = suite_path.read_bytes()
    try:
        temporary.write_bytes(candidate_bytes)
        os.replace(temporary, suite_path)
        after = _c01_tree_hashes(root)
        changed = {path for path in set(before) | set(after) if before.get(path) != after.get(path)}
        if changed - {_C01_ACTIVE_SUITE}:
            raise AssertionError(f"C01 active finalize changed forbidden paths: {sorted(changed)}")
        if read_from(root, _C01_ACTIVE_SUITE)["suite_digest"] != candidate["suite_digest"]:
            raise AssertionError("C01 active Runtime Suite finalize did not persist its self-digest")
    except Exception:
        suite_path.write_bytes(original_bytes)
        raise
    finally:
        if temporary.exists():
            temporary.unlink()
    return changed


def _c01_run_expected_failure(root: Path, script_root: Path, label: str) -> None:
    before = _c01_tree_hashes(root)
    try:
        _c01_finalize_active_suite(root, script_root)
    except (AssertionError, FileNotFoundError):
        pass
    else:
        raise AssertionError(f"C01 refresh mutation did not fail closed: {label}")
    if _c01_tree_hashes(root) != before:
        raise AssertionError(f"C01 refresh failed mutation was not atomic: {label}")


def _c01_self_test() -> None:
    protected_before = {
        "contract": _c01_tree_hashes(CONTRACT_ROOT),
        "build": _c01_tree_hashes(SCRIPT_ROOT / "build") if (SCRIPT_ROOT / "build").exists() else {},
        "evidence": _c01_tree_hashes(SCRIPT_ROOT / "evidence") if (SCRIPT_ROOT / "evidence").exists() else {},
    }
    with tempfile.TemporaryDirectory(prefix="c01-refresh-") as temporary:
        base = Path(temporary)
        contract_copy = base / "contract"
        script_copy = base / "script"
        shutil.copytree(CONTRACT_ROOT, contract_copy)
        shutil.copytree(SCRIPT_ROOT, script_copy, ignore=shutil.ignore_patterns("build", "evidence", ".venv", "node_modules"))
        active_suite_path = contract_copy / _C01_ACTIVE_SUITE
        active_suite = read_from(contract_copy, _C01_ACTIVE_SUITE)
        active_suite["suite_digest"] = "sha256:" + "0" * 64
        active_suite_path.write_text(
            json.dumps(active_suite, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        pre_finalize = _c01_tree_hashes(contract_copy)
        changed = _c01_finalize_active_suite(contract_copy, script_copy)
        if changed != {_C01_ACTIVE_SUITE}:
            raise AssertionError("C01 guarded finalize did not change exactly the active Runtime Suite")
        post_finalize = _c01_tree_hashes(contract_copy)
        if any(
            pre_finalize[path] != post_finalize[path]
            for path in pre_finalize if path != _C01_ACTIVE_SUITE
        ):
            raise AssertionError("C01 guarded finalize rewrote immutable/historical Contract bytes")

        broad_contract = base / "broad-contract"
        shutil.copytree(CONTRACT_ROOT, broad_contract)
        supplemental_before = _c01_supplemental_traceability(broad_contract, script_copy)
        broad_before = _c01_tree_hashes(broad_contract)
        environment = os.environ.copy()
        environment["AGENT_CONTRACT_ROOT"] = str(broad_contract)
        result = subprocess.run(
            [sys.executable, str(script_copy / "contract/maintenance/refresh_example_digests.py")],
            cwd=script_copy, env=environment, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            check=False,
        )
        if result.returncode != 0:
            raise AssertionError(f"C01 normal broad regeneration self-test failed: {result.stderr}")
        supplemental_after = _c01_supplemental_traceability(broad_contract, script_copy)
        if supplemental_after != supplemental_before:
            raise AssertionError("C01 normal broad regeneration changed supplemental ordered objects")
        broad_after = _c01_tree_hashes(broad_contract)
        broad_changed = {
            path for path in set(broad_before) | set(broad_after)
            if broad_before.get(path) != broad_after.get(path)
        }
        if broad_changed - {_C01_ACTIVE_SUITE}:
            raise AssertionError(f"C01 normal broad regeneration changed historical facts: {sorted(broad_changed)}")

        mutation_root = base / "mutations"
        shutil.copytree(CONTRACT_ROOT, mutation_root)
        snapshot = mutation_root / _C01_HISTORICAL_SUITE
        snapshot_bytes = snapshot.read_bytes()
        snapshot.unlink()
        _c01_run_expected_failure(mutation_root, script_copy, "snapshot-missing")
        snapshot.parent.mkdir(parents=True, exist_ok=True)
        snapshot.write_bytes(snapshot_bytes + b"\n")
        _c01_run_expected_failure(mutation_root, script_copy, "snapshot-drift")
        snapshot.write_bytes(snapshot_bytes)

        openapi_snapshot = mutation_root / _C01_HISTORICAL_OPENAPI
        openapi_snapshot_bytes = openapi_snapshot.read_bytes()
        openapi_snapshot.unlink()
        _c01_run_expected_failure(mutation_root, script_copy, "openapi-snapshot-missing")
        openapi_snapshot.write_bytes(openapi_snapshot_bytes + b"\n")
        _c01_run_expected_failure(mutation_root, script_copy, "openapi-snapshot-drift")
        openapi_snapshot.write_bytes(openapi_snapshot_bytes)

        manifest_path = mutation_root / "compatibility/contract-manifest.json"
        manifest_bytes = manifest_path.read_bytes()
        extra = mutation_root / "conformance/runtime/v1/revisions/extra.json"
        extra.write_text("{}\n", encoding="utf-8")
        _c01_run_expected_failure(mutation_root, script_copy, "manifest-path-set")
        extra.unlink()
        manifest_path.write_bytes(manifest_bytes)

        semantic_path = mutation_root / "semantic-constraints-v1.json"
        semantic_bytes = semantic_path.read_bytes()
        semantic_mutations = {
            "supplemental-delete": lambda value, indexes: value["constraints"].pop(indexes[0]),
            "supplemental-modify": lambda value, indexes: value["constraints"][indexes[0]].update({"statement": "drift"}),
            "supplemental-duplicate": lambda value, indexes: value["constraints"].append(copy.deepcopy(value["constraints"][indexes[0]])),
            "supplemental-collision": lambda value, indexes: value["constraints"][indexes[1]].update({
                "constraint_id": value["constraints"][indexes[0]]["constraint_id"],
            }),
            "supplemental-unresolved-schema": lambda value, indexes: value["constraints"][indexes[0]].update({
                "schema_id": "urn:missing",
            }),
            "supplemental-reorder": lambda value, indexes: value["constraints"].__setitem__(
                slice(indexes[0], indexes[1] + 1),
                [value["constraints"][indexes[1]], value["constraints"][indexes[0]]],
            ),
        }
        for label, mutate in semantic_mutations.items():
            traceability = json.loads(semantic_bytes)
            indexes = [
                index for index, entry in enumerate(traceability["constraints"])
                if entry["schema_id"].startswith("urn:agent-platform:agent-runtime-read-")
            ]
            mutate(traceability, indexes)
            semantic_path.write_text(json.dumps(traceability, indent=2) + "\n", encoding="utf-8")
            _c01_run_expected_failure(mutation_root, script_copy, label)
            semantic_path.write_bytes(semantic_bytes)

        validator_path = script_copy / "contract/validation/validate_semantics.py"
        validator_bytes = validator_path.read_bytes()
        validator_source = validator_bytes.decode("utf-8")
        validator_path.write_text(
            validator_source.replace(
                '    "runtime_read.http_authority",\n}',
                '}',
                1,
            ),
            encoding="utf-8",
        )
        _c01_run_expected_failure(mutation_root, script_copy, "supplemental-unknown-check")
        validator_path.write_bytes(validator_bytes)
        validator_path.write_text(
            validator_source.replace(
                "validate_c01_runtime_read_semantics(\n    CONTRACT_ROOT, KNOWN_CONTRACT_CHECKS, EXECUTED_CONTRACT_CHECKS,\n)",
                "_c01_runtime_read_normal_execution_removed()",
                1,
            ),
            encoding="utf-8",
        )
        _c01_run_expected_failure(mutation_root, script_copy, "supplemental-known-but-unexecuted")
        validator_path.write_bytes(validator_bytes)

        revision_path = mutation_root / "examples/contracts/agent-runtime-provider-revision.json"
        revision_bytes = revision_path.read_bytes()
        revision = json.loads(revision_bytes)
        active = read_from(mutation_root, _C01_ACTIVE_SUITE)
        active_digest = digest_without(active, "suite_digest")
        revision["conformance"][0].update({
            "suite_version": "1.0.1", "suite_digest": active_digest, "result": "passed",
        })
        revision_path.write_text(json.dumps(revision, indent=2) + "\n", encoding="utf-8")
        _c01_run_expected_failure(mutation_root, script_copy, "active-passed")
        revision_path.write_bytes(revision_bytes)

        revision = json.loads(revision_bytes)
        revision["port"]["contract_digest"] = "sha256:" + hashlib.sha256(
            (mutation_root / _C01_ACTIVE_OPENAPI).read_bytes()
        ).hexdigest()
        revision_path.write_text(json.dumps(revision, indent=2) + "\n", encoding="utf-8")
        _c01_run_expected_failure(mutation_root, script_copy, "historical-port-rebind")
        revision_path.write_bytes(revision_bytes)

    protected_after = {
        "contract": _c01_tree_hashes(CONTRACT_ROOT),
        "build": _c01_tree_hashes(SCRIPT_ROOT / "build") if (SCRIPT_ROOT / "build").exists() else {},
        "evidence": _c01_tree_hashes(SCRIPT_ROOT / "evidence") if (SCRIPT_ROOT / "evidence").exists() else {},
    }
    if protected_after != protected_before:
        raise AssertionError("C01 refresh self-test changed current Contract/build/evidence state")


if sys.argv[1:] == ["--self-test-c01-runtime-read"]:
    _c01_self_test()
    print("C01 Runtime read refresh self-test passed.")
    raise SystemExit(0)
if sys.argv[1:] == ["--c01-runtime-read-finalize"]:
    changed = _c01_finalize_active_suite(CONTRACT_ROOT, SCRIPT_ROOT)
    print(f"C01 Runtime read active Suite finalized: {sorted(changed)}")
    raise SystemExit(0)
if len(sys.argv) != 1:
    raise SystemExit(f"Unknown arguments: {sys.argv[1:]}")


C01_SUPPLEMENTAL_TRACEABILITY = _c01_supplemental_traceability(CONTRACT_ROOT, SCRIPT_ROOT)
HISTORICAL_RUNTIME_SUITE = _c01_validate_immutable_registry(CONTRACT_ROOT)
_c01_validate_historical_fact_bindings(CONTRACT_ROOT)


suite_paths = {
    "agent_access": "conformance/agent-access/v1/suite.json",
    "agent_runtime": "conformance/runtime/v1/suite.json",
    "sandbox": "conformance/sandbox/v1/suite.json",
    "runtime_gateway": "conformance/runtime-gateway/v1/suite.json",
    "capability_provider": "conformance/capability/v1/suite.json",
    "execution_gateway": "conformance/execution-gateway/v1/suite.json",
    "credential_gateway": "conformance/credential/v1/suite.json",
}
suites: dict[str, dict[str, Any]] = {}
for target_kind, path in suite_paths.items():
    suite = read(path)
    suite["suite_digest"] = digest_without(suite, "suite_digest")
    suites[target_kind] = suite
    write(path, suite)

sandbox_capabilities = read("examples/contracts/sandbox-capabilities.json")
sandbox_capabilities["snapshot_restore_profiles"] = [
    {
        "profile_id": profile_id,
        "level": level,
        "suite_id": suites["sandbox"]["suite_id"],
        "suite_version": suites["sandbox"]["suite_version"],
        "suite_digest": suites["sandbox"]["suite_digest"],
    }
    for profile_id, level in (
        ("sandbox-snapshot-workspace-v1", "workspace"),
        ("sandbox-snapshot-filesystem-v1", "filesystem"),
        ("sandbox-snapshot-process-v1", "process"),
    )
]
write("examples/contracts/sandbox-capabilities.json", sandbox_capabilities)

runtime_checkpoint = read("examples/contracts/agent-runtime-checkpoint-manifest.json")
runtime_checkpoint["source_runtime_revision"] = runtime_checkpoint.pop(
    "runtime_version", "native-runtime-2026.07"
)
runtime_checkpoint["compatibility_profile"] = "runtime-checkpoint-compatibility-v1"
runtime_checkpoint["portability"] = "compatible_revision"
runtime_compatibility_evidence = {
    "evidence_id": "cevd_runtime_01J00000000000000000",
    "evidence_digest": "sha256:" + "0" * 64,
    "subject_kind": "runtime_checkpoint",
    "source_provider_revision_id": runtime_checkpoint["provider_revision_id"],
    "source_runtime_revision": runtime_checkpoint["source_runtime_revision"],
    "target_provider_revision_id": "apr_01J00000000000000000000001",
    "target_runtime_revision": "native-runtime-2026.08",
    "suite_id": HISTORICAL_RUNTIME_SUITE["suite_id"],
    "suite_version": HISTORICAL_RUNTIME_SUITE["suite_version"],
    "suite_digest": HISTORICAL_RUNTIME_SUITE["suite_digest"],
    "profile_id": runtime_checkpoint["compatibility_profile"],
    "test_run_reference": "conformance://runtime/checkpoint/run-01",
    "test_run_digest": digest({"runtime_checkpoint_test_run": "run-01"}),
    "result": "passed",
    "completed_at": "2026-07-16T10:11:00Z",
}
runtime_compatibility_evidence["evidence_digest"] = digest_without(
    runtime_compatibility_evidence, "evidence_digest"
)
runtime_compatibility_decision = {
    "decision_id": "cmpd_runtime_01J0000000000000000",
    "decision_digest": "sha256:" + "0" * 64,
    "subject_kind": "runtime_checkpoint",
    "subject_id": runtime_checkpoint["checkpoint_id"],
    "subject_digest": runtime_checkpoint["digest"],
    "source_provider_revision_id": runtime_checkpoint["provider_revision_id"],
    "source_runtime_revision": runtime_checkpoint["source_runtime_revision"],
    "target_provider_revision_id": runtime_compatibility_evidence["target_provider_revision_id"],
    "target_runtime_revision": runtime_compatibility_evidence["target_runtime_revision"],
    "compatibility_profile": runtime_checkpoint["compatibility_profile"],
    "evidence": [runtime_compatibility_evidence],
    "result": "compatible",
    "reason_codes": ["suite_passed"],
    "decided_at": "2026-07-16T10:12:00Z",
}
runtime_compatibility_decision["decision_digest"] = digest_without(
    runtime_compatibility_decision, "decision_digest"
)
runtime_checkpoint["compatibility_decision"] = copy.deepcopy(runtime_compatibility_decision)
write("examples/contracts/runtime-compatibility-evidence.json", runtime_compatibility_evidence)
write("examples/contracts/runtime-compatibility-decision.json", runtime_compatibility_decision)
write("examples/contracts/agent-runtime-checkpoint-manifest.json", runtime_checkpoint)
runtime_checkpoint_missing_decision = copy.deepcopy(runtime_checkpoint)
runtime_checkpoint_missing_decision.pop("compatibility_decision")
write(
    "tests/invalid/runtime-checkpoint-compatible-missing-decision.json",
    runtime_checkpoint_missing_decision,
)

for path in (
    "examples/capabilities/html.generate.yaml",
    "examples/capabilities/converter.html-to-pptx.yaml",
):
    capability = read_yaml(path)
    capability["conformance"] = {
        "suite_id": suites["capability_provider"]["suite_id"],
        "suite_version": suites["capability_provider"]["suite_version"],
        "suite_digest": suites["capability_provider"]["suite_digest"],
        "suite_profile_id": "capability-core-v1",
    }
    write_yaml(path, capability)

for provider_kind, prefix, instance_id, capability_id, decision_prefix in (
    ("editor", "epr", "epi_artifact_editor", "artifact.edit.html", "pad_editor"),
    ("converter", "cpr", "cpi_html_to_pptx", "artifact.convert.pptx", "pad_converter"),
):
    generated_revision = read("examples/contracts/renderer-provider-revision.json")
    generated_revision["provider_revision_id"] = f"{prefix}_01J00000000000000000000000"
    generated_revision["provider_instance_id"] = instance_id
    generated_revision["provider_kind"] = provider_kind
    generated_revision["conformance"][0].update({
        "capability": capability_id,
        "profile": "default",
    })
    generated_revision["implementation"]["implementation_id"] = f"{provider_kind}-provider.fixture"
    generated_revision["provider_revision_digest"] = "sha256:" + "0" * 64
    write(f"examples/contracts/{provider_kind}-provider-revision.json", generated_revision)
    generated_decision = read("examples/contracts/renderer-provider-admission-decision.json")
    generated_decision["decision_id"] = f"{decision_prefix}_01J000000000000000000"
    generated_decision["provider_revision_id"] = generated_revision["provider_revision_id"]
    generated_decision["provider_revision_digest"] = generated_revision["provider_revision_digest"]
    generated_decision["decision_digest"] = "sha256:" + "0" * 64
    write(f"examples/contracts/{provider_kind}-provider-admission-decision.json", generated_decision)


revision_paths = [
    "examples/contracts/sandbox-provider-revision.json",
    "examples/contracts/agent-runtime-provider-revision.json",
    "examples/contracts/tool-provider-revision.json",
    "examples/contracts/html-skill-provider-revision.json",
    "examples/contracts/renderer-provider-revision.json",
    "examples/contracts/template-provider-revision.json",
    "examples/contracts/editor-provider-revision.json",
    "examples/contracts/converter-provider-revision.json",
]
decision_paths = [
    "examples/contracts/provider-admission-decision.json",
    "examples/contracts/agent-runtime-admission-decision.json",
    "examples/contracts/tool-provider-admission-decision.json",
    "examples/contracts/html-skill-provider-admission-decision.json",
    "examples/contracts/renderer-provider-admission-decision.json",
    "examples/contracts/template-provider-admission-decision.json",
    "examples/contracts/editor-provider-admission-decision.json",
    "examples/contracts/converter-provider-admission-decision.json",
]
revisions: dict[str, dict[str, Any]] = {}
for path in revision_paths:
    revision = read(path)
    legacy_implementation_id = revision.pop("plugin_id", None)
    legacy_implementation_version = revision.pop("plugin_version", None)
    legacy_manifest_digest = revision.pop("manifest_digest", None)
    legacy_distribution_digest = revision.pop("package_digest", None)
    legacy_image_digest = revision.pop("image_digest", None)
    legacy_binding_digest = revision.pop("runtime_binding_digest", None)
    revision.pop("sandbox_conformance_report_digest", None)
    revision.pop("governed_conformance_report_digest", None)
    if "implementation" not in revision:
        distribution_type = {
            "agent_runtime": "oci_image",
            "sandbox": "oci_image",
            "template": "static_catalog",
        }.get(revision["provider_kind"], "package")
        distribution_digest = legacy_distribution_digest or digest({"distribution": revision["provider_revision_id"]})
        implementation = {
            "implementation_id": legacy_implementation_id or f"provider.{revision['provider_revision_id']}",
            "implementation_version": legacy_implementation_version or "1.0.0",
            "distribution_type": distribution_type,
            "distribution_digest": distribution_digest,
            "manifest_digest": legacy_manifest_digest or digest({"manifest": revision["provider_revision_id"]}),
            "provenance": {
                "source_revision": hashlib.sha256(revision["provider_revision_id"].encode()).hexdigest(),
                "source_tree_digest": digest({"source_tree": revision["provider_revision_id"]}),
                "build_artifact_digest": distribution_digest,
                "sbom_digest": digest({"sbom": revision["provider_revision_id"]}),
                "provenance_statement_digest": digest({"provenance": revision["provider_revision_id"]}),
                "build_system": "contract-fixture-build-v1",
            },
        }
        if distribution_type == "oci_image":
            implementation["image_digest"] = legacy_image_digest or digest({"image": revision["provider_revision_id"]})
        revision["implementation"] = implementation
    if "port" not in revision:
        protocol = {
            "agent_runtime": "agent-runtime-provider",
            "sandbox": "sandbox-provider",
        }.get(revision["provider_kind"], "capability-provider")
        contract_path = {
            "agent_runtime": _C01_HISTORICAL_OPENAPI,
            "sandbox": "openapi/sandbox-provider-v1.yaml",
        }.get(revision["provider_kind"], "openapi/capability-provider-v1.yaml")
        revision["port"] = {
            "protocol": protocol,
            "protocol_version": "v1",
            "contract_digest": file_digest(contract_path),
            "binding_digest": legacy_binding_digest or digest({"binding": revision["provider_revision_id"]}),
        }
    contract_path = {
        "agent_runtime": _C01_HISTORICAL_OPENAPI,
        "sandbox": "openapi/sandbox-provider-v1.yaml",
    }.get(revision["provider_kind"], "openapi/capability-provider-v1.yaml")
    revision["port"]["contract_digest"] = file_digest(contract_path)
    if revision["provider_kind"] == "agent_runtime":
        suite = HISTORICAL_RUNTIME_SUITE
        profile_for = lambda capability: "governed-v1" if capability == "agent.runtime.execute" else "runtime-general-v1"
    elif revision["provider_kind"] == "sandbox":
        suite = suites["sandbox"]
        profile_for = lambda _capability: "sandbox-core-v1"
    else:
        suite = suites["capability_provider"]
        profile_for = lambda _capability: "capability-core-v1"
    for result in revision["conformance"]:
        result["suite_id"] = suite["suite_id"]
        result["suite_version"] = suite["suite_version"]
        result["suite_digest"] = suite["suite_digest"]
        result["suite_profile_id"] = profile_for(result["capability"])
    revision["conformance_set_digest"] = digest(revision["conformance"])
    revision["provider_revision_digest"] = digest_without(revision, "provider_revision_digest")
    revisions[revision["provider_revision_id"]] = revision
    write(path, revision)

decisions: dict[str, dict[str, Any]] = {}
for path in decision_paths:
    decision = read(path)
    revision = revisions[decision["provider_revision_id"]]
    decision["provider_revision_digest"] = revision["provider_revision_digest"]
    decision["decision_digest"] = digest_without(decision, "decision_digest")
    decisions[decision["decision_id"]] = decision
    write(path, decision)


def snapshot(revision_id: str, decision_id: str) -> dict[str, Any]:
    revision = revisions[revision_id]
    decision = decisions[decision_id]
    result = {
        "provider_revision_id": revision_id,
        "provider_revision_digest": revision["provider_revision_digest"],
        "provider_kind": revision["provider_kind"],
        "implementation": revision["implementation"],
        "port": revision["port"],
        "configuration_digest": revision["configuration_digest"],
        "approved_permissions_digest": revision["approved_permissions_digest"],
        "credential_binding_digest": revision["credential_binding_digest"],
        "conformance_set_digest": revision["conformance_set_digest"],
        "admission_decision_id": decision_id,
        "admission_decision_digest": decision["decision_digest"],
        "admission_status": "certified",
    }
    return result


ui_schema = read("examples/schemas/html-generation-ui.schema.json")
scenario_path = "examples/scenarios/html-generation.yaml"
scenario = read_yaml(scenario_path)
scenario["ui"]["schema"]["digest"] = digest(ui_schema)
scenario["definition_digest"] = digest_without(scenario, "definition_digest")
write_yaml(scenario_path, scenario)
scenario_identity = {
    "id": scenario["id"],
    "version": scenario["version"],
    "definition_digest": scenario["definition_digest"],
}
required_capabilities = [
    {"id": "agent.general", "version": "1.0", "profile": "default"},
    {"id": "html.generate", "version": "1.0", "profile": "responsive"},
    {"id": "artifact.preview.html", "version": "1.0", "profile": "default"},
]
capability_definitions = [
    {
        "id": "agent.general", "version": "1.0", "profile": "default",
        "definition_digest": "sha256:" + "33" * 32,
        "allowed_provider_kinds": ["agent_runtime"],
    },
    {
        "id": "html.generate", "version": "1.0", "profile": "responsive",
        "definition_digest": "sha256:" + "34" * 32,
        "allowed_provider_kinds": ["tool", "skill"],
    },
    {
        "id": "artifact.preview.html", "version": "1.0", "profile": "default",
        "definition_digest": "sha256:" + "35" * 32,
        "allowed_provider_kinds": ["renderer"],
    },
    {
        "id": "sandbox.exec", "version": "1.0", "profile": "hardened",
        "definition_digest": "sha256:" + "30" * 32,
        "allowed_provider_kinds": ["sandbox"],
    },
    {
        "id": "agent.runtime.execute", "version": "1.0", "profile": "governed",
        "definition_digest": "sha256:" + "32" * 32,
        "allowed_provider_kinds": ["agent_runtime"],
    },
    {
        "id": "artifact.edit.html", "version": "1.0", "profile": "default",
        "definition_digest": "sha256:" + "36" * 32,
        "allowed_provider_kinds": ["editor"],
    },
    {
        "id": "artifact.convert.pptx", "version": "1.0", "profile": "default",
        "definition_digest": "sha256:" + "37" * 32,
        "allowed_provider_kinds": ["converter"],
    },
]
definition_by_capability = {item["id"]: item for item in capability_definitions}

principal_context_path = "examples/contracts/principal-context-snapshot.json"
principal_context = read(principal_context_path)
principal_context["issued_at"] = "2026-07-16T08:59:30Z"
principal_context["expires_at"] = "2026-07-16T09:30:00Z"
principal_context["principal_context_digest"] = digest_without(
    principal_context, "principal_context_digest"
)
write(principal_context_path, principal_context)


def resolution(
    resolution_id: str, capability: dict[str, Any], revision_id: str,
    decision_id: str, resolved_at: str,
    execution_scope: dict[str, Any] | None = None,
) -> dict[str, Any]:
    revision = revisions[revision_id]
    scope = execution_scope or {
        "kind": "work_order",
        "work_order_id": "wrk_01J00000000000000000000000",
    }
    provider_audience = f"urn:agent-platform:provider-instance:{revision['provider_instance_id']}"
    resolution_input = {
        "tenant_id": "ten_01J00000000000000000000000",
        "client_app_id": "html-product",
        "execution_scope": copy.deepcopy(scope),
        "principal_context_digest": principal_context["principal_context_digest"],
        "capability": capability,
        "capability_definition_digest": definition_by_capability[capability["id"]]["definition_digest"],
        "provider_revision_id": revision_id,
        "routing_precedence": [
            "tenant_binding", "client_binding", "scenario_requirement", "platform_default", "explicit_fallback",
        ],
    }
    candidate_evidence = {
        "provider_instance_id": revision["provider_instance_id"],
        "provider_revision_id": revision_id,
        "provider_audience": provider_audience,
        "admission_decision_id": decision_id,
        "operational_health": "healthy",
        "capacity": "available",
        "placement": "compatible",
    }
    evidence = {
        "resolution_id": resolution_id,
        "input": resolution_input,
        "candidates": [candidate_evidence],
    }
    value = {
        "resolution_id": resolution_id,
        "tenant_id": "ten_01J00000000000000000000000",
        "client_app_id": "html-product",
        "execution_scope": copy.deepcopy(scope),
        "principal_context_digest": principal_context["principal_context_digest"],
        "identity_dependency": {
            "mode": "principal_context",
            "declaration_digest": digest({
                "resolver": "provider-resolver",
                "identity_dependency": "principal_context",
            }),
        },
        "capability": capability,
        "selected_provider_instance_id": revision["provider_instance_id"],
        "selected_provider_audience": provider_audience,
        "routing_reason": "scenario_requirement",
        "resolver_revision": {
            "id": "provider-resolver",
            "version": "1.0.0",
            "digest": digest({"resolver": "provider-resolver", "version": "1.0.0"}),
        },
        "resolution_input_digest": digest(resolution_input),
        "candidate_evaluations": [{
            "provider_instance_id": revision["provider_instance_id"],
            "provider_revision_id": revision_id,
            "provider_audience": provider_audience,
            "outcome": "selected",
            "reason_codes": ["scenario_match"],
            "evidence_digest": digest(candidate_evidence),
        }],
        "resolution_evidence_reference": f"resolution-evidence/{resolution_id}",
        "resolution_evidence_digest": digest(evidence),
        "resolved_at": resolved_at,
        "capability_definition_digest": definition_by_capability[capability["id"]]["definition_digest"],
        "selected_provider_revision": snapshot(revision_id, decision_id),
        "decision_digest": "sha256:" + "0" * 64,
    }
    value["decision_digest"] = digest_without(value, "decision_digest")
    return value


template_path = "examples/contracts/template-revision.json"
template = read(template_path)
template["provider_revision"] = snapshot(
    "tplpr_01J0000000000000000000000",
    "tplad_01J0000000000000000000000",
)
template["revision_digest"] = digest_without(template, "revision_digest")
write(template_path, template)

grant_path = "examples/contracts/execution-grant-claims.json"
grant = read(grant_path)
grant["iat"] = 1784192400
grant["nbf"] = 1784192400
grant["exp"] = 1784192700
grant["request_contract_id"] = "urn:agent-platform:conversation-turn-request:v1"
grant["request_digest_profile"] = "rfc8785-request-excluding-execution-grant-v1"
grant["principal_context"] = copy.deepcopy(principal_context)
grant["principal_context_digest"] = principal_context["principal_context_digest"]
grant["limits"].update({
    "max_agent_runs": 8,
    "max_agent_depth": 4,
    "max_parallel_agent_runs": 3,
})
commercial_path = "examples/contracts/commercial-authorization-snapshot.json"
commercial = read(commercial_path)
commercial["commercial_authorization_id"] = commercial.pop(
    "authorization_id", commercial.get("commercial_authorization_id")
)
commercial.pop("authorization_digest", None)
commercial["issued_at"] = "2026-07-16T08:59:30Z"
commercial["expires_at"] = "2026-07-16T09:30:00Z"
commercial["authorized_entitlements"] = ["experience.html.premium"]
commercial["authorized_capabilities"] = grant["capabilities"]
commercial["authorized_limits"] = grant["limits"]
commercial["authorized_limits_digest"] = digest(commercial["authorized_limits"])
commercial["commercial_authorization_digest"] = digest_without(commercial, "commercial_authorization_digest")
write(commercial_path, commercial)
commercial_binding = {
    "commercial_authorization_id": commercial["commercial_authorization_id"],
    "commercial_authorization_digest": commercial["commercial_authorization_digest"],
    "expires_at": commercial["expires_at"],
}
write("examples/contracts/commercial-authorization-binding.json", commercial_binding)
grant["commercial_authorization"] = commercial
write(grant_path, grant)

workspace_manifest_path = "examples/contracts/workspace-content-manifest.json"
workspace_manifest = read(workspace_manifest_path)
workspace_manifest["path_case_policy"] = workspace_manifest.get("path_case_policy", "case_sensitive")
workspace_manifest["entry_count"] = len(workspace_manifest["entries"])
workspace_manifest["total_file_bytes"] = sum(
    entry.get("size_bytes", 0) for entry in workspace_manifest["entries"]
    if entry["entry_type"] == "file"
)
workspace_manifest["manifest_digest"] = digest_without(workspace_manifest, "manifest_digest")
write(workspace_manifest_path, workspace_manifest)

workspace_revision_path = "examples/contracts/workspace-revision.json"
workspace_revision = read(workspace_revision_path)
workspace_revision["content_manifest_schema_id"] = "urn:agent-platform:workspace-content-manifest:v1"
workspace_revision["content_manifest_artifact"]["digest"] = workspace_manifest["manifest_digest"]
workspace_revision["content_manifest_artifact"]["size_bytes"] = (CONTRACT_ROOT / workspace_manifest_path).stat().st_size
workspace_revision["revision_digest"] = digest_without(workspace_revision, "revision_digest")
write(workspace_revision_path, workspace_revision)

conversation_branch = read("examples/contracts/conversation-branch.json")
conversation_branch["workspace_head_revision_id"] = workspace_revision["workspace_revision_id"]
conversation_branch["workspace_head_revision_digest"] = workspace_revision["revision_digest"]
write("examples/contracts/conversation-branch.json", conversation_branch)
conversation_branch_page = read("examples/contracts/conversation-branch-page.json")
conversation_branch_page["branches"] = [copy.deepcopy(conversation_branch)]
write("examples/contracts/conversation-branch-page.json", conversation_branch_page)

sandbox_spec = read("examples/contracts/sandbox-spec.json")
sandbox_spec["branch_id"] = workspace_revision["branch_id"]
sandbox_spec["provider_resolution_id"] = "res_sandbox_exec_01J0000000000000"
sandbox_spec["workspace"]["base_revision_id"] = workspace_revision["workspace_revision_id"]
sandbox_spec["workspace"]["base_revision_digest"] = workspace_revision["revision_digest"]
sandbox_spec["workspace"].pop("base_branch_version", None)
sandbox_spec["workspace"]["base_workspace_head_version"] = conversation_branch["workspace_head_version"]
sandbox_spec["workspace"]["commit_mode"] = "cas_new_revision"
sandbox_spec["lease"]["expires_at"] = "2026-07-16T09:15:00Z"
sandbox_spec["lease"]["max_extension_seconds"] = 600
write("examples/contracts/sandbox-spec.json", sandbox_spec)
sandbox_create = read("examples/contracts/sandbox-create-request.json")
sandbox_create["spec"] = copy.deepcopy(sandbox_spec)
sandbox_create["deadline_at"] = "2026-07-16T09:05:00Z"
sandbox_create["request_digest"] = digest_without(sandbox_create, "request_digest")
write("examples/contracts/sandbox-create-request.json", sandbox_create)
sandbox_restore = read("examples/contracts/sandbox-restore-request.json")
sandbox_restore["spec"]["branch_id"] = workspace_revision["branch_id"]
sandbox_restore["spec"]["provider_resolution_id"] = "res_sandbox_exec_01J0000000000000"
sandbox_restore["spec"]["workspace"]["base_revision_id"] = workspace_revision["workspace_revision_id"]
sandbox_restore["spec"]["workspace"]["base_revision_digest"] = workspace_revision["revision_digest"]
sandbox_restore["spec"]["workspace"].pop("base_branch_version", None)
sandbox_restore["spec"]["workspace"]["base_workspace_head_version"] = conversation_branch["workspace_head_version"]
sandbox_restore["spec"]["workspace"]["commit_mode"] = "cas_new_revision"
sandbox_snapshot = sandbox_restore["snapshot"]
sandbox_snapshot["source_provider_revision_id"] = sandbox_snapshot.pop(
    "provider_revision_id", "spr_01J00000000000000000000000"
)
sandbox_snapshot["source_runtime_revision"] = "sandbox-runtime-1.0.0"
sandbox_snapshot["portability"] = "portable"
sandbox_snapshot.pop("portable", None)
sandbox_snapshot.pop("compatibility", None)
sandbox_snapshot["compatibility_profile"] = "sandbox-snapshot-workspace-v1"
sandbox_compatibility_evidence = {
    "evidence_id": "cevd_sandbox_01J00000000000000000",
    "evidence_digest": "sha256:" + "0" * 64,
    "subject_kind": "sandbox_snapshot",
    "source_provider_revision_id": sandbox_snapshot["source_provider_revision_id"],
    "source_runtime_revision": sandbox_snapshot["source_runtime_revision"],
    "target_provider_revision_id": sandbox_restore["spec"]["provider_revision_id"],
    "target_runtime_revision": "sandbox-runtime-1.1.0",
    "suite_id": suites["sandbox"]["suite_id"],
    "suite_version": suites["sandbox"]["suite_version"],
    "suite_digest": suites["sandbox"]["suite_digest"],
    "profile_id": sandbox_snapshot["compatibility_profile"],
    "test_run_reference": "conformance://sandbox/snapshot-workspace/run-01",
    "test_run_digest": digest({"sandbox_snapshot_test_run": "run-01"}),
    "result": "passed",
    "completed_at": "2026-07-16T10:05:00Z",
}
sandbox_compatibility_evidence["evidence_digest"] = digest_without(
    sandbox_compatibility_evidence, "evidence_digest"
)
sandbox_compatibility_decision = {
    "decision_id": "cmpd_sandbox_01J0000000000000000",
    "decision_digest": "sha256:" + "0" * 64,
    "subject_kind": "sandbox_snapshot",
    "subject_id": sandbox_snapshot["snapshot_id"],
    "subject_digest": sandbox_snapshot["digest"],
    "source_provider_revision_id": sandbox_snapshot["source_provider_revision_id"],
    "source_runtime_revision": sandbox_snapshot["source_runtime_revision"],
    "target_provider_revision_id": sandbox_restore["spec"]["provider_revision_id"],
    "target_runtime_revision": "sandbox-runtime-1.1.0",
    "compatibility_profile": sandbox_snapshot["compatibility_profile"],
    "evidence": [sandbox_compatibility_evidence],
    "result": "compatible",
    "reason_codes": ["suite_passed"],
    "decided_at": "2026-07-16T10:06:00Z",
}
sandbox_compatibility_decision["decision_digest"] = digest_without(
    sandbox_compatibility_decision, "decision_digest"
)
sandbox_snapshot["compatibility_decision"] = copy.deepcopy(sandbox_compatibility_decision)
sandbox_restore["target_provider_revision_id"] = sandbox_compatibility_decision["target_provider_revision_id"]
sandbox_restore["target_runtime_revision"] = sandbox_compatibility_decision["target_runtime_revision"]
sandbox_restore["compatibility_decision"] = copy.deepcopy(sandbox_compatibility_decision)
write("examples/contracts/sandbox-compatibility-evidence.json", sandbox_compatibility_evidence)
write("examples/contracts/sandbox-compatibility-decision.json", sandbox_compatibility_decision)
sandbox_snapshot_missing_decision = copy.deepcopy(sandbox_snapshot)
sandbox_snapshot_missing_decision.pop("compatibility_decision")
write(
    "tests/invalid/sandbox-snapshot-portable-missing-decision.json",
    sandbox_snapshot_missing_decision,
)
write("tests/semantic-invalid/compatibility-decision-cases.json", {
    "runtime_subject": runtime_checkpoint,
    "runtime_decision": runtime_compatibility_decision,
    "sandbox_subject": sandbox_snapshot,
    "sandbox_decision": sandbox_compatibility_decision,
    "sandbox_restore": sandbox_restore,
    "cases": [
        {"id": "runtime-compatible-with-failed-evidence", "mutation": "runtime_failed_evidence"},
        {"id": "runtime-compatible-target-mismatch", "mutation": "runtime_target_mismatch"},
        {"id": "sandbox-restore-target-mismatch", "mutation": "sandbox_restore_target_mismatch"},
    ],
})
sandbox_restore["request_digest"] = digest_without(sandbox_restore, "request_digest")
write("examples/contracts/sandbox-restore-request.json", sandbox_restore)
sandbox_requests: dict[str, tuple[str, dict[str, Any], str]] = {
    "create": ("examples/contracts/sandbox-create-request.json", sandbox_create, sandbox_spec["sandbox_id"]),
    "restore": ("examples/contracts/sandbox-restore-request.json", sandbox_restore, sandbox_restore["spec"]["sandbox_id"]),
}
for operation, filename in {
    "set_desired_state": "sandbox-desired-state-request.json",
    "extend_lease": "sandbox-lease-request.json",
    "exec": "sandbox-exec-request.json",
    "cancel_exec": "sandbox-cancel-exec-request.json",
    "open_runtime_session": "sandbox-runtime-session-open-request.json",
    "snapshot": "sandbox-snapshot-request.json",
    "terminate": "sandbox-terminate-request.json",
}.items():
    path = f"examples/contracts/{filename}"
    request = read(path)
    if operation == "snapshot":
        request["compatibility_profile"] = "sandbox-snapshot-workspace-v1"
    request["request_digest"] = digest_without(request, "request_digest")
    write(path, request)
    sandbox_requests[operation] = (path, request, sandbox_spec["sandbox_id"])
work_session = read("examples/contracts/work-session-request.json")
work_session["commercial_authorization"] = commercial
work_session["principal_context"] = copy.deepcopy(principal_context)
write("examples/contracts/work-session-request.json", work_session)

meter_path = "examples/contracts/meter-definition.json"
meter = read(meter_path)
meter["definition_digest"] = digest_without(meter, "definition_digest")
write(meter_path, meter)

budget_path = "examples/contracts/execution-budget.json"
budget = read(budget_path)
budget["tenant_id"] = "ten_01J00000000000000000000000"
work_order_id = "wrk_01J00000000000000000000000"
budget.pop("work_order_id", None)
budget["execution_scope"] = {"kind": "work_order", "work_order_id": work_order_id}
budget["limits"] = copy.deepcopy(commercial["authorized_limits"])
budget["budget_digest"] = digest_without(budget, "budget_digest")
write(budget_path, budget)

root_budget_allocation = {
    "allocation_id": "abal_root_01J000000000000000000000",
    "allocation_digest": "sha256:" + "0" * 64,
    "tenant_id": budget["tenant_id"],
    "work_order_id": work_order_id,
    "agent_run_id": "agr_01J00000000000000000000000",
    "work_order_budget_id": budget["budget_id"],
    "work_order_budget_digest": budget["budget_digest"],
    "limits": {
        name: budget["limits"][name] for name in AGENT_RUN_RESOURCE_LIMIT_NAMES
    },
    "issued_at": "2026-07-16T09:01:00Z",
    "expires_at": budget["expires_at"],
}
root_budget_allocation["allocation_digest"] = digest_without(
    root_budget_allocation, "allocation_digest"
)
write("examples/contracts/agent-run-budget-allocation.json", root_budget_allocation)

permissions_path = "examples/contracts/effective-permissions.json"
permissions = read(permissions_path)
permissions["tenant_id"] = budget["tenant_id"]
permissions.pop("work_order_id", None)
permissions["execution_scope"] = {"kind": "work_order", "work_order_id": work_order_id}
legacy_artifact_permissions = permissions["artifact"]
permissions["artifact"] = {
    "read": legacy_artifact_permissions["read"],
    "stage_new_version": legacy_artifact_permissions.get(
        "stage_new_version", legacy_artifact_permissions.get("write", False)
    ),
}
permissions["egress"]["allowed_destination_classes"] = [
    value for value in permissions["egress"]["allowed_destination_classes"]
    if value != "public-docs-origin"
]
if "public_documentation" not in permissions["egress"]["allowed_destination_classes"]:
    permissions["egress"]["allowed_destination_classes"].append("public_documentation")
permissions["permissions_digest"] = digest_without(permissions, "permissions_digest")
write(permissions_path, permissions)

service_access_token = {
    "iss": "https://business.example.test",
    "sub": "business-html-product",
    "aud": "https://agent-api.agent-platform.internal",
    "iat": 1784192400,
    "nbf": 1784192400,
    "exp": 1784192700,
    "jti": "sat_01J00000000000000000000000",
    "client_id": principal_context["client_app_id"],
    "scope": "conversation:create session:create",
    "cnf": {"jkt": "n4bQgYhMfWWaL-qgxVrQFaO_TxsrCkVJqkR1bQ"},
}
write("examples/contracts/service-access-token-claims.json", service_access_token)
service_access_token_unknown = copy.deepcopy(service_access_token)
service_access_token_unknown["unregistered_claim"] = "must-fail"
write(
    "tests/invalid/service-access-token-with-unknown-claim.json",
    service_access_token_unknown,
)

work_session_claims = {
    "jti": "wsc_01J00000000000000000000000",
    "iss": "agent-platform",
    "aud": "agent-workbench",
    "iat": 1784192400,
    "nbf": 1784192400,
    "exp": 1784193300,
    "session_id": "wss_01J00000000000000000000000",
    "client_app_id": principal_context["client_app_id"],
    "tenant_id": budget["tenant_id"],
    "principal_id": work_session["external_principal_id"],
    "conversation_id": grant["conversation_id"],
    "commercial_authorization_id": commercial["commercial_authorization_id"],
    "commercial_authorization_digest": commercial["commercial_authorization_digest"],
    "commercial_authorization_expires_at": commercial["expires_at"],
    "principal_context_digest": principal_context["principal_context_digest"],
    "scopes": work_session["scopes"],
    "session_version": 1,
}
write("examples/contracts/work-session-claims.json", work_session_claims)
work_session_missing_context = copy.deepcopy(work_session_claims)
work_session_missing_context.pop("principal_context_digest")
write(
    "tests/invalid/work-session-claims-missing-principal-context.json",
    work_session_missing_context,
)

plugin_request = read("examples/contracts/plugin-invocation-request.json")
plugin_request["tenant_id"] = budget["tenant_id"]
plugin_request["client_app_id"] = principal_context["client_app_id"]
plugin_request["work_order_id"] = work_order_id
plugin_request["deadline_at"] = "2026-07-16T09:20:00Z"
for artifact in plugin_request["input_artifacts"]:
    artifact["expires_at"] = "2026-07-16T09:10:00Z"
plugin_request["output_staging"]["expires_at"] = "2026-07-16T09:20:00Z"
plugin_request["request_digest"] = digest_without(plugin_request, "request_digest")
write("examples/contracts/plugin-invocation-request.json", plugin_request)
plugin_status_descriptor = {
    "operation": "status",
    "invocation_id": plugin_request["invocation_id"],
    "invocation_attempt_id": plugin_request["invocation_attempt_id"],
    "fencing_token": plugin_request["fencing_token"],
}
write("examples/contracts/plugin-status-operation-descriptor.json", plugin_status_descriptor)
plugin_cancel_request = {
    "invocation_id": plugin_request["invocation_id"],
    "provider_operation_id": "legacy-provider-operation-0001",
    "fencing_token": plugin_request["fencing_token"],
    "reason": "workflow cancelled",
    "invocation_attempt_id": plugin_request["invocation_attempt_id"],
    "request_digest": "sha256:" + "0" * 64,
}
plugin_cancel_request["request_digest"] = digest_without(plugin_cancel_request, "request_digest")
write("examples/contracts/plugin-cancellation-request.json", plugin_cancel_request)
plugin_event_descriptor = {
    "operation": "read_events",
    "invocation_id": plugin_request["invocation_id"],
    "invocation_attempt_id": plugin_request["invocation_attempt_id"],
    "fencing_token": plugin_request["fencing_token"],
    "after_sequence": 0,
}
write("examples/contracts/plugin-event-read-operation-descriptor.json", plugin_event_descriptor)
plugin_token_base = {
    "iss": "agent-platform",
    "sub": "spn_agent_capability_bridge",
    "aud": "urn:agent-platform:provider-instance:legacy-html-to-pptx",
    "iat": 1784192460,
    "nbf": 1784192460,
    "exp": 1784192760,
    "tenant_id": plugin_request["tenant_id"],
    "client_app_id": plugin_request["client_app_id"],
    "work_order_id": plugin_request["work_order_id"],
    "plugin_id": "html-to-pptx",
    "provider_revision_id": "legacypr_html_to_pptx_01",
    "invocation_id": plugin_request["invocation_id"],
    "invocation_attempt_id": plugin_request["invocation_attempt_id"],
    "fencing_token": plugin_request["fencing_token"],
    "capability_id": plugin_request["capability"]["id"],
    "capability_version": plugin_request["capability"]["version"],
    "staging_session_id": plugin_request["output_staging"]["session_id"],
    "permissions_digest": permissions["permissions_digest"],
    "invocation_request_digest": plugin_request["request_digest"],
    "deadline_at": plugin_request["deadline_at"],
}
plugin_operations = {
    "invoke": (
        "examples/contracts/plugin-invocation-token-claims.json",
        "urn:agent-platform:plugin-invocation-request:v1",
        "rfc8785-request-excluding-request-digest-v1",
        plugin_request["request_digest"],
        plugin_request,
    ),
    "status": (
        "examples/contracts/plugin-status-token-claims.json",
        "urn:agent-platform:plugin-status-operation-descriptor:v1",
        "rfc8785-full-document-v1",
        digest(plugin_status_descriptor),
        plugin_status_descriptor,
    ),
    "cancel": (
        "examples/contracts/plugin-cancellation-token-claims.json",
        "urn:agent-platform:plugin-cancellation-request:v1",
        "rfc8785-request-excluding-request-digest-v1",
        plugin_cancel_request["request_digest"],
        plugin_cancel_request,
    ),
    "read_events": (
        "examples/contracts/plugin-events-token-claims.json",
        "urn:agent-platform:plugin-event-read-operation-descriptor:v1",
        "rfc8785-full-document-v1",
        digest(plugin_event_descriptor),
        plugin_event_descriptor,
    ),
}
plugin_tokens: dict[str, dict[str, Any]] = {}
for index, (operation, (path, contract_id, profile, operation_digest, document)) in enumerate(
    plugin_operations.items(), start=1
):
    plugin_token = copy.deepcopy(plugin_token_base)
    plugin_token.update({
        "jti": f"pit_{index:02d}_01J00000000000000000000000",
        "authority_mode": "execution" if operation == "invoke" else "safety_control",
        "operation": operation,
        "operation_contract_id": contract_id,
        "operation_digest_profile": profile,
        "operation_request_digest": operation_digest,
        "invocation_id": document["invocation_id"],
        "invocation_attempt_id": document["invocation_attempt_id"],
        "fencing_token": document["fencing_token"],
    })
    if operation != "invoke":
        plugin_token.update({"iat": 1784193660, "nbf": 1784193660, "exp": 1784193960})
    plugin_tokens[operation] = plugin_token
    write(path, plugin_token)
plugin_token_missing_contract = copy.deepcopy(plugin_tokens["invoke"])
plugin_token_missing_contract.pop("operation_contract_id")
write(
    "tests/invalid/plugin-token-missing-operation-contract.json",
    plugin_token_missing_contract,
)
plugin_token_contract_replay = copy.deepcopy(plugin_tokens["read_events"])
plugin_token_contract_replay["operation_contract_id"] = (
    "urn:agent-platform:plugin-status-operation-descriptor:v1"
)
write(
    "tests/invalid/plugin-token-operation-contract-replay.json",
    plugin_token_contract_replay,
)
plugin_safety_invoke = copy.deepcopy(plugin_tokens["invoke"])
plugin_safety_invoke["authority_mode"] = "safety_control"
write("tests/invalid/plugin-safety-token-authorizes-invoke.json", plugin_safety_invoke)

runtime_input_path = "examples/contracts/runtime-input-envelope.json"
runtime_input = read(runtime_input_path)
runtime_input["source_kind"] = "conversation_message"
runtime_input.pop("child_agent_spawn_request_id", None)
runtime_input["content_digest"] = digest(runtime_input["content"])
write(runtime_input_path, runtime_input)

child_spawn_request = {
    "spawn_request_id": "spawn_01J0000000000000000000000",
    "request_digest": "sha256:" + "0" * 64,
    "tenant_id": budget["tenant_id"],
    "work_order_id": work_order_id,
    "workflow_run_id": "wfr_01J00000000000000000000000",
    "root_agent_run_id": "agr_01J00000000000000000000000",
    "parent_agent_run_id": "agr_01J00000000000000000000000",
    "parent_runtime_run_id": "rtr_01J00000000000000000000000",
    "parent_run_depth": 0,
    "requested_agent_role": "researcher",
    "required_for_work_order_completion": True,
    "delegated_input": {
        "input_id": "rin_child_01J00000000000000000000",
        "source_kind": "delegated_task",
        "child_agent_spawn_request_id": "spawn_01J0000000000000000000000",
        "content_digest": "sha256:" + "0" * 64,
        "content": [{"type": "text", "text": "Research the cited sources and return verified findings."}],
    },
    "required_capabilities": [
        {"id": "agent.general", "version": "1.0", "profile": "default"}
    ],
    "workspace_mode": "isolated_revision",
    "sandbox_mode": "dedicated",
    "requested_at": "2026-07-16T09:02:00Z",
}
child_spawn_request["delegated_input"]["content_digest"] = digest(
    child_spawn_request["delegated_input"]["content"]
)
child_spawn_request["request_digest"] = digest_without(
    child_spawn_request, "request_digest"
)
write("examples/contracts/child-agent-run-spawn-request.json", child_spawn_request)

context_package_path = "examples/contracts/context-package.json"
context_package = read(context_package_path)
context_package["items"][0]["digest"] = workspace_manifest["manifest_digest"]
context_package["items"][0]["size_bytes"] = workspace_revision["content_manifest_artifact"]["size_bytes"]
context_package["context_package_digest"] = digest_without(context_package, "context_package_digest")
write(context_package_path, context_package)

gateway_bindings = read("examples/contracts/runtime-gateway-bindings.json")
gateway_contracts = {
    "model": (
        "urn:agent-platform:openapi:capability-provider:v1",
        "openapi/capability-provider-v1.yaml",
    ),
    "tool": (
        "urn:agent-platform:openapi:capability-provider:v1",
        "openapi/capability-provider-v1.yaml",
    ),
    "artifact": (
        "urn:agent-platform:openapi:artifact-gateway:v1",
        "openapi/artifact-gateway-v1.yaml",
    ),
    "egress": (
        "urn:agent-platform:openapi:egress-gateway:v1",
        "openapi/egress-gateway-v1.yaml",
    ),
}
for kind, binding in gateway_bindings.items():
    contract_id, contract_path = gateway_contracts[kind]
    legacy = copy.deepcopy(binding)
    gateway_bindings[kind] = {
        "kind": kind,
        "mode": "enabled",
        "port": {
            "gateway_kind": kind,
            "gateway_id": legacy.get("gateway_id", f"{kind}-gateway"),
            "route_id": legacy.get("route_id", f"{kind}-route-work-order"),
            "protocol_version": "v1",
            "contract_id": contract_id,
            "contract_digest": file_digest(contract_path),
            "binding_digest": legacy.get("binding_digest", digest({"gateway": kind})),
            "audience": legacy.get("audience", f"agent-{kind}-gateway"),
        },
    }
write("examples/contracts/runtime-gateway-bindings.json", gateway_bindings)

artifact_grant = read("examples/contracts/artifact-grant.json")
artifact_grant["artifact_digest"] = workspace_manifest["manifest_digest"]
artifact_grant["execution_scope"] = {
    "kind": "work_order",
    "work_order_id": work_order_id,
}
artifact_grant["runtime_run_id"] = "rtr_01J00000000000000000000000"
artifact_grant["invocation_id"] = "inv_runtime_start_01J000000000000"
artifact_grant["invocation_attempt_id"] = "iat_runtime_start_01J00000000000"
artifact_grant.pop("work_order_id", None)
artifact_grant["permissions"] = [
    "stage_new_version" if permission == "write_new_version" else permission
    for permission in artifact_grant["permissions"]
    if permission != "finalize"
]
artifact_grant.pop("gateway_route_id", None)
artifact_grant["gateway_binding"] = copy.deepcopy(gateway_bindings["artifact"]["port"])
artifact_grant["grant_digest"] = digest_without(artifact_grant, "grant_digest")
write("examples/contracts/artifact-grant.json", artifact_grant)
artifact_requirement_path = "examples/contracts/artifact-access-requirement.json"
artifact_requirement = read(artifact_requirement_path)
for field in ("tenant_id", "artifact_id", "version_id", "artifact_digest"):
    artifact_requirement[field] = artifact_grant[field]
artifact_requirement["work_order_id"] = work_order_id
artifact_requirement["allowed_permissions"] = copy.deepcopy(artifact_grant["permissions"])
write(artifact_requirement_path, artifact_requirement)

usage_entry_path = "examples/contracts/technical-usage-entry.json"
usage_entry = read(usage_entry_path)
usage_entry.pop("work_order_id", None)
usage_entry["execution_scope"] = {"kind": "work_order", "work_order_id": work_order_id}
usage_entry["meter_id"] = meter["meter_id"]
usage_entry["meter_version"] = meter["meter_version"]
usage_entry["meter_definition_digest"] = meter["definition_digest"]
usage_entry["unit"] = meter["base_unit"]
usage_entry["producer"]["provider_revision_digest"] = revisions[
    usage_entry["producer"]["provider_revision_id"]
]["provider_revision_digest"]
usage_entry["evidence_digest"] = digest({"evidence_reference": usage_entry["evidence_reference"]})
usage_entry["source_observation_id"] = "uobs_01J000000000000000000000"
write(usage_entry_path, usage_entry)

usage_observation_path = "examples/contracts/usage-observation.json"
usage_observation = read(usage_observation_path)
usage_observation["meter_id"] = meter["meter_id"]
usage_observation["meter_version"] = meter["meter_version"]
usage_observation["unit"] = meter["base_unit"]
usage_observation["evidence_digest"] = digest({
    "evidence_reference": usage_observation["evidence_reference"]
})
write(usage_observation_path, usage_observation)
for field in (
    "meter_id", "meter_version", "quantity", "unit", "measurement_status",
    "evidence_reference", "evidence_digest", "occurred_at",
):
    usage_entry[field] = usage_observation[field]
usage_entry["source_observation_id"] = usage_observation["observation_id"]
write(usage_entry_path, usage_entry)

usage_report_path = "examples/contracts/usage-report.json"
usage_report = read(usage_report_path)
usage_report.pop("work_order_id", None)
usage_report["execution_scope"] = copy.deepcopy(usage_entry["execution_scope"])
usage_report["commercial_authorization_id"] = commercial["commercial_authorization_id"]
usage_report["commercial_authorization_digest"] = commercial["commercial_authorization_digest"]
usage_report["quota_reservation_id"] = commercial["quota_reservation_id"]
usage_report["quota_reservation_digest"] = commercial["quota_reservation_digest"]
usage_report["entries"] = [usage_entry]
usage_report["report_sequence"] = 1
usage_report.pop("supersedes_usage_report_id", None)
usage_report["usage_report_digest"] = digest_without(usage_report, "usage_report_digest")
write(usage_report_path, usage_report)

first_correction = copy.deepcopy(usage_report)
first_correction["usage_report_id"] = "usr_invalid_first_correction"
first_correction["report_status"] = "correction"
first_correction["report_sequence"] = 1
first_correction["entries"][0]["measurement_status"] = "corrected"
first_correction["entries"][0]["quantity"] = -1
first_correction["entries"][0]["correction_of_entry_id"] = usage_entry["entry_id"]
first_correction["entries"][0]["correction_reason"] = "Invalid first report cannot be a correction."
first_correction["usage_report_digest"] = digest_without(first_correction, "usage_report_digest")
write("tests/invalid/usage-report-first-correction.json", first_correction)

settlement_path = "examples/contracts/business-settlement-envelope.json"
settlement = read(settlement_path)
settlement.pop("work_order_id", None)
settlement.pop("work_order_terminal_status", None)
settlement["execution_scope"] = copy.deepcopy(usage_report["execution_scope"])
settlement["terminal_status"] = "completed"
settlement["commercial_authorization_id"] = commercial["commercial_authorization_id"]
settlement["commercial_authorization_digest"] = commercial["commercial_authorization_digest"]
settlement["quota_reservation_id"] = commercial["quota_reservation_id"]
settlement["quota_reservation_digest"] = commercial["quota_reservation_digest"]
settlement["settlement_target_id"] = commercial["settlement_target_id"]
settlement.pop("usage_report_id", None)
settlement.pop("usage_report_digest", None)
settlement["usage_report"] = usage_report
settlement["envelope_sequence"] = 1
settlement.pop("supersedes_settlement_envelope_id", None)
settlement["settlement_envelope_digest"] = digest_without(settlement, "settlement_envelope_digest")
write(settlement_path, settlement)

reconcile_with_final = copy.deepcopy(settlement)
reconcile_with_final["settlement_envelope_id"] = "set_invalid_reconcile_final"
reconcile_with_final["action"] = "reconcile"
reconcile_with_final["envelope_sequence"] = 2
reconcile_with_final["supersedes_settlement_envelope_id"] = settlement["settlement_envelope_id"]
reconcile_with_final["settlement_envelope_digest"] = digest_without(reconcile_with_final, "settlement_envelope_digest")
write("tests/invalid/settlement-reconcile-final-report.json", reconcile_with_final)

policy_path = "examples/contracts/policy-decision.json"
policy = read(policy_path)
policy.pop("work_order_id", None)
policy["execution_scope"] = {"kind": "work_order", "work_order_id": work_order_id}
policy["decision_point"] = "run_admission"
policy["commercial_authorization_id"] = commercial["commercial_authorization_id"]
policy["commercial_authorization_digest"] = commercial["commercial_authorization_digest"]
policy["execution_budget_id"] = budget["budget_id"]
policy["execution_budget_digest"] = budget["budget_digest"]
policy["effective_permissions_digest"] = permissions["permissions_digest"]
policy["decision_digest"] = digest_without(policy, "decision_digest")
write(policy_path, policy)

for invocation_path in (
    "examples/contracts/invocation-record.json",
    "examples/contracts/invocation-attempt-sequence-record.json",
    "examples/contracts/invocation-non-idempotent-retry.json",
):
    invocation_fixture = read(invocation_path)
    invocation_fixture["execution_scope"] = {
        "kind": "work_order",
        "work_order_id": invocation_fixture["work_order_id"],
    }
    write(invocation_path, invocation_fixture)


def digest_artifact_operation_request(value: dict[str, Any]) -> str:
    unsigned = copy.deepcopy(value)
    unsigned["operation_context"].pop("request_digest", None)
    return digest(unsigned)


def build_artifact_operation(
    operation_kind: str,
    capability: dict[str, Any],
    revision_id: str,
    decision_id: str,
) -> tuple[
    dict[str, Any], dict[str, Any], dict[str, Any],
    dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any],
]:
    operation_id = f"aop_{operation_kind}_01J000000000000000000"
    scope = {"kind": "artifact_operation", "artifact_operation_id": operation_id}
    operation_budget = copy.deepcopy(budget)
    operation_budget["budget_id"] = f"bud_{operation_kind}_01J000000000000000000"
    operation_budget["execution_scope"] = copy.deepcopy(scope)
    operation_budget["created_at"] = "2026-07-16T09:06:01Z"
    operation_budget["limits"]["max_agent_runs"] = 1
    operation_budget["limits"]["max_agent_depth"] = 1
    operation_budget["limits"]["max_parallel_agent_runs"] = 1
    operation_budget["policies"]["model_gateway_required"] = False
    operation_budget["policies"]["tool_gateway_required"] = False
    operation_budget["policies"]["egress_gateway_required"] = False
    operation_budget["policies"]["external_communication"] = False
    operation_budget["budget_digest"] = digest_without(operation_budget, "budget_digest")
    operation_policy = copy.deepcopy(policy)
    operation_policy["decision_id"] = f"pol_{operation_kind}_01J000000000000000000"
    operation_policy["execution_scope"] = copy.deepcopy(scope)
    operation_policy["decision_point"] = "artifact_operation"
    operation_policy["decided_at"] = "2026-07-16T09:06:01Z"
    operation_policy["execution_budget_id"] = operation_budget["budget_id"]
    operation_policy["execution_budget_digest"] = operation_budget["budget_digest"]
    operation_policy["evaluations"] = [{
        "subject_kind": "artifact",
        "subject_id": capability["id"],
        "action": "allow",
        "source": "commercial",
        "rule_digest": digest({"artifact_operation_policy": operation_kind}),
    }]
    operation_policy["decision_digest"] = digest_without(operation_policy, "decision_digest")
    operation_permissions = copy.deepcopy(permissions)
    operation_permissions["permissions_id"] = f"perm_{operation_kind}_01J00000000000000000"
    operation_permissions["execution_scope"] = copy.deepcopy(scope)
    operation_permissions["model"]["allowed_model_profiles"] = []
    operation_permissions["tool"]["allowed_capabilities"] = [capability["id"]]
    operation_permissions["artifact"] = {"read": True, "stage_new_version": True}
    operation_permissions["egress"] = {"mode": "none", "allowed_destination_classes": []}
    operation_permissions["sandbox_slots"] = []
    operation_permissions["permissions_digest"] = digest_without(
        operation_permissions, "permissions_digest"
    )
    operation_policy["effective_permissions_digest"] = operation_permissions["permissions_digest"]
    operation_policy["decision_digest"] = digest_without(operation_policy, "decision_digest")
    context = {
        "operation_kind": operation_kind,
        "tenant_id": budget["tenant_id"],
        "client_app_id": principal_context["client_app_id"],
        "principal_context": copy.deepcopy(principal_context),
        "artifact_id": "art_01J00000000000000000000000",
        "source_version_id": "ver_01J00000000000000000000000",
        "source_version_digest": digest({"artifact_version": "source-v1"}),
        "capability": copy.deepcopy(capability),
        "commercial_authorization": copy.deepcopy(commercial_binding),
        "quota_reservation_id": commercial["quota_reservation_id"],
        "quota_reservation_digest": commercial["quota_reservation_digest"],
        "idempotency_key": f"artifact-{operation_kind}-idempotency-0001",
        "request_digest": "sha256:" + "0" * 64,
        "requested_at": "2026-07-16T09:06:00Z",
    }
    operation_resolution = resolution(
        f"res_{operation_kind}_01J000000000000000000",
        capability,
        revision_id,
        decision_id,
        "2026-07-16T09:06:01Z",
        execution_scope=scope,
    )
    invocation = {
        "invocation_id": f"inv_{operation_kind}_01J000000000000000000",
        "tenant_id": context["tenant_id"],
        "execution_scope": copy.deepcopy(scope),
        "artifact_operation_id": operation_id,
        "capability_id": capability["id"],
        "capability_version": capability["version"],
        "provider_instance_id": operation_resolution["selected_provider_instance_id"],
        "provider_resolution_id": operation_resolution["resolution_id"],
        "provider_revision_id": operation_resolution["selected_provider_revision"]["provider_revision_id"],
        "idempotency_key": f"invocation-{operation_kind}-idempotency-0001",
        "request_digest": "sha256:" + "0" * 64,
        "side_effect": "idempotent",
        "status": "succeeded",
        "current_attempt_id": f"iat_{operation_kind}_01J00000000000000000",
        "result_reference": f"artifact-operation-result://{operation_id}",
        "created_at": "2026-07-16T09:06:02Z",
        "updated_at": "2026-07-16T09:06:05Z",
        "completed_at": "2026-07-16T09:06:05Z",
        "attempt_count": 1,
        "max_attempts": 3,
    }
    operation = {
        "artifact_operation_id": operation_id,
        "operation_kind": operation_kind,
        "tenant_id": context["tenant_id"],
        "client_app_id": context["client_app_id"],
        "principal_context_digest": principal_context["principal_context_digest"],
        "artifact_id": context["artifact_id"],
        "source_version_id": context["source_version_id"],
        "source_version_digest": context["source_version_digest"],
        "request_digest": "sha256:" + "0" * 64,
        "invocation_request_digest": "sha256:" + "0" * 64,
        "commercial_authorization_id": commercial_binding["commercial_authorization_id"],
        "commercial_authorization_digest": commercial_binding["commercial_authorization_digest"],
        "quota_reservation_id": commercial["quota_reservation_id"],
        "quota_reservation_digest": commercial["quota_reservation_digest"],
        "policy_decision_id": operation_policy["decision_id"],
        "policy_decision_digest": operation_policy["decision_digest"],
        "execution_budget_id": operation_budget["budget_id"],
        "execution_budget_digest": operation_budget["budget_digest"],
        "effective_permissions_id": operation_permissions["permissions_id"],
        "effective_permissions_digest": operation_permissions["permissions_digest"],
        "artifact_gateway_binding_digest": gateway_bindings["artifact"]["port"]["binding_digest"],
        "provider_resolution_id": operation_resolution["resolution_id"],
        "provider_revision_id": operation_resolution["selected_provider_revision"]["provider_revision_id"],
        "invocation_id": invocation["invocation_id"],
        "status": "succeeded",
        "state_version": 5,
        "terminal_stage": "finalization",
        "result_reference": invocation["result_reference"],
        "terminal_evidence_digest": digest({"artifact_operation_outcome": operation_id}),
        "created_at": "2026-07-16T09:06:00Z",
        "updated_at": "2026-07-16T09:06:05Z",
        "completed_at": "2026-07-16T09:06:05Z",
    }
    return (
        context, operation_budget, operation_policy, operation_permissions,
        operation_resolution, invocation, operation,
    )


artifact_operation_materials = {}
for operation_kind, capability, revision_id, decision_id in (
    (
        "preview", {"id": "artifact.preview.html", "version": "1.0", "profile": "default"},
        "rpr_01J00000000000000000000000", "pad_renderer_01J0000000000000000",
    ),
    (
        "edit", {"id": "artifact.edit.html", "version": "1.0", "profile": "default"},
        "epr_01J00000000000000000000000", "pad_editor_01J000000000000000000",
    ),
    (
        "conversion", {"id": "artifact.convert.pptx", "version": "1.0", "profile": "default"},
        "cpr_01J00000000000000000000000", "pad_converter_01J000000000000000000",
    ),
):
    artifact_operation_materials[operation_kind] = build_artifact_operation(
        operation_kind, capability, revision_id, decision_id
    )

preview_context, preview_budget, preview_policy, preview_permissions, preview_resolution, preview_invocation, preview_operation = artifact_operation_materials["preview"]
preview_request = {"operation_context": copy.deepcopy(preview_context), "options": {"theme": "system"}}
preview_request["operation_context"]["request_digest"] = digest_artifact_operation_request(preview_request)
preview_invocation["request_digest"] = preview_request["operation_context"]["request_digest"]
preview_operation["request_digest"] = preview_request["operation_context"]["request_digest"]
write("examples/contracts/artifact-operation-context.json", preview_request["operation_context"])
write("examples/contracts/artifact-operation-execution-budget.json", preview_budget)
write("examples/contracts/artifact-operation-policy-decision.json", preview_policy)
write("examples/contracts/artifact-operation-effective-permissions.json", preview_permissions)
write("examples/contracts/artifact-operation-provider-resolution.json", preview_resolution)
write("examples/contracts/artifact-operation-invocation.json", preview_invocation)
write("examples/contracts/artifact-operation.json", preview_operation)
write("examples/contracts/preview-session-request.json", preview_request)
artifact_operation_client_supplied_admission = copy.deepcopy(preview_request)
artifact_operation_client_supplied_admission["operation_context"].update({
    "artifact_operation_id": preview_operation["artifact_operation_id"],
    "policy_decision_id": preview_policy["decision_id"],
    "policy_decision_digest": preview_policy["decision_digest"],
    "execution_budget_id": preview_budget["budget_id"],
    "execution_budget_digest": preview_budget["budget_digest"],
    "effective_permissions_id": preview_permissions["permissions_id"],
    "effective_permissions_digest": preview_permissions["permissions_digest"],
    "artifact_gateway_binding": copy.deepcopy(gateway_bindings["artifact"]["port"]),
})
write(
    "tests/invalid/artifact-operation-client-supplied-admission.json",
    artifact_operation_client_supplied_admission,
)
write("examples/contracts/preview-session.json", {
    "preview_session_id": "prv_01J00000000000000000000000",
    "artifact_operation": preview_operation,
    "status": "ready",
    "preview_url": "https://preview.agent-platform.test/session/prv_01",
    "expires_at": "2026-07-16T09:16:05Z",
})

edit_context, _, _, _, _, edit_invocation, edit_operation = artifact_operation_materials["edit"]
edit_request = {"operation_context": copy.deepcopy(edit_context), "mode": "source", "options": {}}
edit_request["operation_context"]["request_digest"] = digest_artifact_operation_request(edit_request)
edit_invocation["request_digest"] = edit_request["operation_context"]["request_digest"]
edit_operation["request_digest"] = edit_request["operation_context"]["request_digest"]
write("examples/contracts/edit-session-request.json", edit_request)
write("examples/contracts/edit-session.json", {
    "edit_session_id": "edt_01J00000000000000000000000",
    "artifact_operation": edit_operation,
    "status": "active",
    "mode": "source",
    "draft_reference": "artifact-draft://edt_01",
    "created_at": "2026-07-16T09:06:05Z",
    "expires_at": "2026-07-16T09:26:05Z",
    "draft_revision": 0,
})

conversion_context, _, _, _, _, conversion_invocation, conversion_operation = artifact_operation_materials["conversion"]
conversion_request = {
    "operation_context": copy.deepcopy(conversion_context),
    "target_media_type": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "options": {"page_size": "wide"},
}
conversion_request["operation_context"]["request_digest"] = digest_artifact_operation_request(conversion_request)
conversion_invocation["request_digest"] = conversion_request["operation_context"]["request_digest"]
conversion_operation["request_digest"] = conversion_request["operation_context"]["request_digest"]
write("examples/contracts/conversion-request.json", conversion_request)
write("examples/contracts/conversion-job.json", {
    "conversion_job_id": "cnv_01J00000000000000000000000",
    "artifact_operation": conversion_operation,
    "target_media_type": conversion_request["target_media_type"],
    "result_artifact_id": "art_derived_01J0000000000000000000",
    "result_version_id": "ver_derived_01J0000000000000000000",
})

artifact_operation_admission_failed = copy.deepcopy(preview_operation)
for field in (
    "provider_resolution_id", "provider_revision_id", "invocation_id",
    "invocation_request_digest", "result_reference",
):
    artifact_operation_admission_failed.pop(field, None)
artifact_operation_admission_failed.update({
    "artifact_operation_id": "aop_admission_failed_01J000000000000",
    "status": "failed",
    "state_version": 1,
    "terminal_stage": "admission",
    "error": {
        "code": "ARTIFACT_OPERATION_ADMISSION_DENIED",
        "message": "Artifact operation admission was denied before Provider resolution.",
        "retryable": False,
        "trace_id": "trace-artifact-operation-admission-denied",
    },
    "terminal_evidence_digest": digest({"admission_decision": "denied"}),
    "updated_at": "2026-07-16T09:06:01Z",
    "completed_at": "2026-07-16T09:06:01Z",
})
write(
    "examples/contracts/artifact-operation-admission-failed.json",
    artifact_operation_admission_failed,
)

write("tests/semantic-invalid/artifact-operation-cases.json", {
    "operation": copy.deepcopy(preview_operation),
    "request": copy.deepcopy(preview_request),
    "budget": copy.deepcopy(preview_budget),
    "policy": copy.deepcopy(preview_policy),
    "permissions": copy.deepcopy(preview_permissions),
    "resolution": copy.deepcopy(preview_resolution),
    "invocation": copy.deepcopy(preview_invocation),
    "cases": [
        {"id": "provider-resolution-mismatch", "mutation": "provider_resolution_mismatch"},
        {"id": "invocation-scope-mismatch", "mutation": "invocation_scope_mismatch"},
        {"id": "invocation-request-digest-mismatch", "mutation": "invocation_request_digest_mismatch"},
        {"id": "permissions-scope-mismatch", "mutation": "permissions_scope_mismatch"},
        {"id": "provider-revision-mismatch", "mutation": "provider_revision_mismatch"},
        {"id": "source-version-digest-mismatch", "mutation": "source_version_digest_mismatch"},
        {"id": "terminal-evidence-missing", "mutation": "terminal_evidence_missing"},
        {"id": "provider-request-owner-digest-mismatch", "mutation": "provider_request_owner_digest_mismatch"},
        {"id": "platform-policy-binding-mismatch", "mutation": "platform_policy_binding_mismatch"},
        {"id": "platform-gateway-binding-mismatch", "mutation": "platform_gateway_binding_mismatch"},
    ],
})
invalid_ingest_invocation = copy.deepcopy(preview_invocation)
invalid_ingest_invocation["execution_scope"] = {
    "kind": "artifact_ingest",
    "artifact_ingest_session_id": "ing_01J00000000000000000000000",
}
write("tests/invalid/invocation-artifact-ingest-scope.json", invalid_ingest_invocation)

branch_create_request = {
    "branch_request_id": "breq_01J00000000000000000000000",
    "conversation_id": conversation_branch["conversation_id"],
    "branch_id": "debug-rerun-01",
    "mode": "fork",
    "source_branch_id": conversation_branch["branch_id"],
    "source_message_id": conversation_branch["head_message_id"],
    "source_message_sequence": conversation_branch["head_message_sequence"],
    "source_message_head_version": conversation_branch["message_head_version"],
    "source_workspace_revision_id": conversation_branch["workspace_head_revision_id"],
    "source_workspace_revision_digest": conversation_branch["workspace_head_revision_digest"],
    "source_workspace_head_version": conversation_branch["workspace_head_version"],
    "idempotency_key": "conversation-branch-fork-idempotency-0001",
    "request_digest": "sha256:" + "0" * 64,
}
branch_create_request["request_digest"] = digest_without(branch_create_request, "request_digest")
fork_workspace_revision = copy.deepcopy(workspace_revision)
fork_workspace_revision.update({
    "workspace_revision_id": "wsr_fork_01J000000000000000000000",
    "branch_id": branch_create_request["branch_id"],
    "revision_number": 1,
    "parent_revision_id": None,
    "forked_from_revision_id": workspace_revision["workspace_revision_id"],
    "created_at": "2026-07-16T09:07:00Z",
})
fork_workspace_revision["revision_digest"] = digest_without(
    fork_workspace_revision, "revision_digest"
)
forked_branch = copy.deepcopy(conversation_branch)
forked_branch.update({
    "branch_id": branch_create_request["branch_id"],
    "forked_from_branch_id": branch_create_request["source_branch_id"],
    "forked_from_message_id": branch_create_request["source_message_id"],
    "active_work_order_id": None,
    "workspace_head_revision_id": fork_workspace_revision["workspace_revision_id"],
    "workspace_head_revision_digest": fork_workspace_revision["revision_digest"],
    "message_head_version": 1,
    "workspace_head_version": 1,
    "active_work_version": 1,
    "branch_version": 1,
    "created_at": "2026-07-16T09:07:00Z",
    "updated_at": "2026-07-16T09:07:00Z",
})
write("examples/contracts/conversation-branch-create-request.json", branch_create_request)
branch_created = {
    "branch_request_id": branch_create_request["branch_request_id"],
    "request_digest": branch_create_request["request_digest"],
    "branch": forked_branch,
    "workspace_revision": fork_workspace_revision,
}
write("examples/contracts/conversation-branch-created.json", branch_created)

empty_branch_request = {
    "branch_request_id": "breq_empty_01J0000000000000000000",
    "conversation_id": conversation_branch["conversation_id"],
    "branch_id": "parallel-empty-01",
    "mode": "create",
    "idempotency_key": "conversation-branch-create-idempotency-0001",
    "request_digest": "sha256:" + "0" * 64,
}
empty_branch_request["request_digest"] = digest_without(
    empty_branch_request, "request_digest"
)
empty_workspace_revision = copy.deepcopy(workspace_revision)
empty_workspace_revision.update({
    "workspace_revision_id": "wsr_empty_01J00000000000000000000",
    "branch_id": empty_branch_request["branch_id"],
    "revision_number": 1,
    "parent_revision_id": None,
    "forked_from_revision_id": workspace_revision["workspace_revision_id"],
    "created_at": "2026-07-16T09:07:30Z",
})
empty_workspace_revision.pop("produced_by_work_order_id", None)
empty_workspace_revision["revision_digest"] = digest_without(
    empty_workspace_revision, "revision_digest"
)
empty_branch = copy.deepcopy(conversation_branch)
empty_branch.update({
    "branch_id": empty_branch_request["branch_id"],
    "head_message_id": None,
    "head_message_sequence": 0,
    "active_work_order_id": None,
    "workspace_head_revision_id": empty_workspace_revision["workspace_revision_id"],
    "workspace_head_revision_digest": empty_workspace_revision["revision_digest"],
    "message_head_version": 1,
    "workspace_head_version": 1,
    "active_work_version": 1,
    "branch_version": 1,
    "created_at": "2026-07-16T09:07:30Z",
    "updated_at": "2026-07-16T09:07:30Z",
})
empty_branch.pop("forked_from_branch_id", None)
empty_branch.pop("forked_from_message_id", None)
empty_branch_created = {
    "branch_request_id": empty_branch_request["branch_request_id"],
    "request_digest": empty_branch_request["request_digest"],
    "branch": empty_branch,
    "workspace_revision": empty_workspace_revision,
}
write("examples/contracts/conversation-branch-empty-create-request.json", empty_branch_request)
write("examples/contracts/conversation-branch-empty-created.json", empty_branch_created)
write("tests/semantic-invalid/conversation-branch-create-cases.json", {
    "request": branch_create_request,
    "created": branch_created,
    "source_branch": conversation_branch,
    "source_message": read("examples/contracts/conversation-message.json"),
    "source_workspace": workspace_revision,
    "empty_request": empty_branch_request,
    "empty_created": empty_branch_created,
    "cases": [
        {"id": "fork-message-cas-stale", "mutation": "message_cas_stale"},
        {"id": "fork-workspace-digest-mismatch", "mutation": "workspace_digest_mismatch"},
        {"id": "fork-created-at-wrong-cut", "mutation": "created_wrong_cut"},
        {"id": "create-inherits-message", "mutation": "create_inherits_message"},
        {"id": "create-wrong-initial-workspace", "mutation": "create_wrong_workspace"},
    ],
})

no_usage_attestation = {
    "attestation_id": "nua_01J00000000000000000000000",
    "attestation_digest": "sha256:" + "0" * 64,
    "tenant_id": budget["tenant_id"],
    "execution_scope": {"kind": "work_order", "work_order_id": work_order_id},
    "commercial_authorization_id": commercial["commercial_authorization_id"],
    "commercial_authorization_digest": commercial["commercial_authorization_digest"],
    "quota_reservation_id": commercial["quota_reservation_id"],
    "quota_reservation_digest": commercial["quota_reservation_digest"],
    "reason": "failed_before_dispatch",
    "evidence_reference": "ledger://work-orders/wrk_01/no-dispatch-proof",
    "evidence_digest": digest({"dispatch_attempt_count": 0, "technical_usage_count": 0}),
    "confirmed_at": "2026-07-16T09:07:30Z",
}
no_usage_attestation["attestation_digest"] = digest_without(
    no_usage_attestation, "attestation_digest"
)
write("examples/contracts/no-usage-attestation.json", no_usage_attestation)
delivery_no_usage = {
    "delivery_id": "del_no_usage_01J00000000000000000",
    "work_order_id": work_order_id,
    "status": "failed",
    "summary": "Admission failed before any Provider or Gateway dispatch.",
    "artifacts": [],
    "usage_accounting": {
        "kind": "confirmed_no_usage",
        "no_usage_attestation": copy.deepcopy(no_usage_attestation),
    },
    "completed_at": "2026-07-16T09:07:31Z",
}
write("examples/contracts/delivery-package-no-usage.json", delivery_no_usage)
release_settlement = copy.deepcopy(settlement)
release_settlement.update({
    "settlement_envelope_id": "set_release_01J0000000000000000000",
    "terminal_status": "failed",
    "action": "release",
    "idempotency_key": "settlement-release-idempotency-0001",
    "no_usage_attestation": copy.deepcopy(no_usage_attestation),
})
release_settlement.pop("usage_report", None)
release_settlement["settlement_envelope_digest"] = digest_without(
    release_settlement, "settlement_envelope_digest"
)
write("examples/contracts/business-settlement-release-envelope.json", release_settlement)
artifact_operation_no_usage = copy.deepcopy(no_usage_attestation)
artifact_operation_no_usage.update({
    "attestation_id": "nua_aop_01J000000000000000000000",
    "execution_scope": {
        "kind": "artifact_operation",
        "artifact_operation_id": "aop_admission_failed_01J000000000000",
    },
    "evidence_reference": "ledger://artifact-operations/aop_admission_failed/no-dispatch-proof",
    "evidence_digest": digest({
        "artifact_operation_id": "aop_admission_failed_01J000000000000",
        "dispatch_attempt_count": 0,
        "technical_usage_count": 0,
    }),
})
artifact_operation_no_usage["attestation_digest"] = digest_without(
    artifact_operation_no_usage, "attestation_digest"
)
write(
    "examples/contracts/artifact-operation-no-usage-attestation.json",
    artifact_operation_no_usage,
)
artifact_operation_release = copy.deepcopy(release_settlement)
artifact_operation_release.update({
    "settlement_envelope_id": "set_release_aop_01J00000000000000000",
    "execution_scope": copy.deepcopy(artifact_operation_no_usage["execution_scope"]),
    "terminal_status": "failed",
    "idempotency_key": "settlement-release-artifact-operation-0001",
    "no_usage_attestation": copy.deepcopy(artifact_operation_no_usage),
})
artifact_operation_release["settlement_envelope_digest"] = digest_without(
    artifact_operation_release, "settlement_envelope_digest"
)
write(
    "examples/contracts/artifact-operation-business-settlement-release-envelope.json",
    artifact_operation_release,
)
invalid_no_usage = copy.deepcopy(no_usage_attestation)
invalid_no_usage["reason"] = "failed_before_dispatch"
write("tests/semantic-invalid/no-usage-cases.json", {
    "attestation": invalid_no_usage,
    "cases": [{"id": "attempt-dispatched-before-zero-confirmation", "mutation": "dispatched_attempt_exists"}],
})

sandbox_exec_request = sandbox_requests["exec"][1]
secret_operation_intent = copy.deepcopy(sandbox_exec_request)
for field in ("request_digest", "secret_reference_ids", "secret_grant_id", "secret_grant_digest"):
    secret_operation_intent.pop(field, None)
secret_target_digest = digest(secret_operation_intent)
secret_grant = {
    "secret_grant_id": "secg_01J00000000000000000000000",
    "secret_grant_digest": "sha256:" + "0" * 64,
    "tenant_id": sandbox_spec["tenant_id"],
    "principal_context_digest": principal_context["principal_context_digest"],
    "execution_scope": {"kind": "work_order", "work_order_id": sandbox_spec["work_order_id"]},
    "provider_instance_id": "spi_native_sandbox",
    "provider_revision_id": "spr_01J00000000000000000000000",
    "provider_audience": "urn:agent-platform:provider-instance:spi_native_sandbox",
    "workload_identity": "spiffe://agent-platform/provider/spi_native_sandbox/workload/exec",
    "secret_reference_ids": ["secret-ref-api-token-01"],
    "purpose": "process_environment",
    "target": {
        "target_kind": "sandbox_exec",
        "target_id": sandbox_exec_request["operation_id"],
        "target_digest": secret_target_digest,
    },
    "operation": "credential_access",
    "target_request_contract_id": "urn:agent-platform:sandbox-exec-request:v1",
    "target_request_digest_profile": "rfc8785-sandbox-exec-intent-excluding-secret-grant-and-request-digest-v1",
    "target_request_digest": secret_target_digest,
    "sender_constraint": {
        "method": "mtls_spiffe",
        "subject": "spiffe://agent-platform/provider/spi_native_sandbox/workload/exec",
    },
    "issued_at": "2026-07-16T09:08:00Z",
    "expires_at": "2026-07-16T09:13:00Z",
    "max_uses": 1,
    "persistence_policy": {
        "provider_cache_allowed": False,
        "provider_persistence_allowed": False,
        "platform_event_material_allowed": False,
        "temporal_history_material_allowed": False,
    },
}
secret_grant["secret_grant_digest"] = digest_without(secret_grant, "secret_grant_digest")
sandbox_exec_request["secret_reference_ids"] = copy.deepcopy(secret_grant["secret_reference_ids"])
sandbox_exec_request["secret_grant_id"] = secret_grant["secret_grant_id"]
sandbox_exec_request["secret_grant_digest"] = secret_grant["secret_grant_digest"]
sandbox_exec_request["request_digest"] = digest_without(sandbox_exec_request, "request_digest")
write("examples/contracts/sandbox-exec-request.json", sandbox_exec_request)
credential_request = {
    "credential_request_id": "creq_01J00000000000000000000000",
    "secret_grant_id": secret_grant["secret_grant_id"],
    "secret_grant_digest": secret_grant["secret_grant_digest"],
    "secret_reference_ids": copy.deepcopy(secret_grant["secret_reference_ids"]),
    "target": copy.deepcopy(secret_grant["target"]),
    "purpose": secret_grant["purpose"],
    "request_digest": "sha256:" + "0" * 64,
}
credential_request["request_digest"] = digest_without(credential_request, "request_digest")
credential_token = {
    "iss": "agent-platform",
    "sub": secret_grant["workload_identity"],
    "aud": "urn:agent-platform:credential-gateway:primary",
    "jti": "cot_01J00000000000000000000000",
    "iat": 1784192880,
    "nbf": 1784192880,
    "exp": 1784193180,
    "tenant_id": secret_grant["tenant_id"],
    "secret_grant_id": secret_grant["secret_grant_id"],
    "secret_grant_digest": secret_grant["secret_grant_digest"],
    "operation": "credential_access",
    "request_contract_id": "urn:agent-platform:credential-access-request:v1",
    "request_digest_profile": "rfc8785-request-excluding-request-digest-v1",
    "request_digest": credential_request["request_digest"],
}
credential_delivery = {
    "credential_request_id": credential_request["credential_request_id"],
    "delivery_handle": "opaque-workload-bound-single-operation-handle-000000000001",
    "delivery_mode": secret_grant["purpose"],
    "expires_at": "2026-07-16T09:13:00Z",
    "audit_event_id": "evt_credential_access_01J000000000000",
}
secret_revocation = {
    "revocation_id": "secr_01J00000000000000000000000",
    "revocation_digest": "sha256:" + "0" * 64,
    "tenant_id": secret_grant["tenant_id"],
    "secret_grant_id": secret_grant["secret_grant_id"],
    "secret_grant_digest": secret_grant["secret_grant_digest"],
    "reason": "operation_cancelled",
    "revoked_at": "2026-07-16T09:09:00Z",
}
secret_revocation["revocation_digest"] = digest_without(secret_revocation, "revocation_digest")
write("examples/contracts/secret-grant.json", secret_grant)
write("examples/contracts/secret-grant-revocation.json", secret_revocation)
write("examples/contracts/credential-access-request.json", credential_request)
write("examples/contracts/credential-operation-token-claims.json", credential_token)
write("examples/contracts/credential-operation-jws-header.json", {
    "alg": "EdDSA", "kid": "credential-gateway-key-2026-01", "typ": "agent-credential-operation+jwt",
})
write("examples/contracts/credential-delivery.json", credential_delivery)
missing_secret_grant = copy.deepcopy(sandbox_exec_request)
missing_secret_grant.pop("secret_grant_id")
missing_secret_grant.pop("secret_grant_digest")
write("tests/invalid/sandbox-exec-secret-reference-missing-grant.json", missing_secret_grant)
write("tests/semantic-invalid/credential-mediation-cases.json", {
    "secret_grant": secret_grant,
    "request": credential_request,
    "token": credential_token,
    "delivery": credential_delivery,
    "cases": [
        {"id": "target-digest-mismatch", "mutation": "target_digest_mismatch"},
        {"id": "sender-mismatch", "mutation": "sender_mismatch"},
        {"id": "token-expiry-exceeds-grant", "mutation": "expiry_exceeds_grant"},
        {"id": "revoked-before-use", "mutation": "revoked_before_use"},
    ],
})

ingest_session_id = "ing_01J00000000000000000000000"
ingest_scope = {
    "kind": "artifact_ingest", "artifact_ingest_session_id": ingest_session_id,
}
ingest_budget = copy.deepcopy(preview_budget)
ingest_budget["budget_id"] = "bud_ingest_01J0000000000000000000"
ingest_budget["execution_scope"] = copy.deepcopy(ingest_scope)
ingest_budget["created_at"] = "2026-07-16T09:10:01Z"
ingest_budget["budget_digest"] = digest_without(ingest_budget, "budget_digest")
ingest_permissions = copy.deepcopy(preview_permissions)
ingest_permissions["permissions_id"] = "perm_ingest_01J00000000000000000"
ingest_permissions["execution_scope"] = copy.deepcopy(ingest_scope)
ingest_permissions["tool"]["allowed_capabilities"] = []
ingest_permissions["artifact"] = {"read": False, "stage_new_version": True}
ingest_permissions["permissions_digest"] = digest_without(
    ingest_permissions, "permissions_digest"
)
ingest_policy = copy.deepcopy(preview_policy)
ingest_policy["decision_id"] = "pol_ingest_01J0000000000000000000"
ingest_policy["execution_scope"] = copy.deepcopy(ingest_scope)
ingest_policy["decision_point"] = "artifact"
ingest_policy["decided_at"] = "2026-07-16T09:10:01Z"
ingest_policy["execution_budget_id"] = ingest_budget["budget_id"]
ingest_policy["execution_budget_digest"] = ingest_budget["budget_digest"]
ingest_policy["effective_permissions_digest"] = ingest_permissions["permissions_digest"]
ingest_policy["evaluations"] = [{
    "subject_kind": "artifact",
    "subject_id": "art_ingest_01J0000000000000000000",
    "action": "allow",
    "source": "commercial",
    "rule_digest": digest({
        "artifact_id": "art_ingest_01J0000000000000000000",
        "media_type": "application/pdf",
    }),
}]
ingest_policy["decision_digest"] = digest_without(ingest_policy, "decision_digest")
ingest_request = {
    "ingest_request_id": "ireq_01J00000000000000000000000",
    "tenant_id": budget["tenant_id"],
    "client_app_id": principal_context["client_app_id"],
    "principal_context": copy.deepcopy(principal_context),
    "artifact_id": "art_ingest_01J0000000000000000000",
    "name": "research-input.pdf",
    "media_type": "application/pdf",
    "size_bytes": 4096,
    "content_digest": bytes_digest(b"artifact-ingest-fixture-bytes"),
    "commercial_authorization": copy.deepcopy(commercial_binding),
    "idempotency_key": "artifact-ingest-idempotency-0001",
    "request_digest": "sha256:" + "0" * 64,
    "requested_at": "2026-07-16T09:10:00Z",
}
ingest_request["request_digest"] = digest_without(ingest_request, "request_digest")
artifact_ingest_client_supplied_admission = copy.deepcopy(ingest_request)
artifact_ingest_client_supplied_admission.update({
    "policy_decision_id": ingest_policy["decision_id"],
    "policy_decision_digest": ingest_policy["decision_digest"],
    "execution_budget_id": ingest_budget["budget_id"],
    "execution_budget_digest": ingest_budget["budget_digest"],
    "effective_permissions_id": ingest_permissions["permissions_id"],
    "effective_permissions_digest": ingest_permissions["permissions_digest"],
})
write(
    "tests/invalid/artifact-ingest-client-supplied-admission.json",
    artifact_ingest_client_supplied_admission,
)
ingest_session = {
    "ingest_session_id": ingest_session_id,
    "tenant_id": ingest_request["tenant_id"],
    "client_app_id": ingest_request["client_app_id"],
    "principal_context_digest": principal_context["principal_context_digest"],
    "artifact_id": ingest_request["artifact_id"],
    "request_digest": ingest_request["request_digest"],
    "commercial_authorization_id": commercial_binding["commercial_authorization_id"],
    "commercial_authorization_digest": commercial_binding["commercial_authorization_digest"],
    "policy_decision_id": ingest_policy["decision_id"],
    "policy_decision_digest": ingest_policy["decision_digest"],
    "execution_budget_id": ingest_budget["budget_id"],
    "execution_budget_digest": ingest_budget["budget_digest"],
    "effective_permissions_id": ingest_permissions["permissions_id"],
    "effective_permissions_digest": ingest_permissions["permissions_digest"],
    "status": "finalized",
    "state_version": 7,
    "confirmed_upload_digest": ingest_request["content_digest"],
    "scan_result_id": "iscan_01J0000000000000000000000",
    "scan_result_digest": "sha256:" + "0" * 64,
    "artifact_version_id": "ver_ingest_01J0000000000000000000",
    "artifact_version_digest": digest({"artifact_ingest_version": "v1"}),
    "created_at": "2026-07-16T09:10:00Z",
    "expires_at": "2026-07-16T09:40:00Z",
    "updated_at": "2026-07-16T09:11:00Z",
    "completed_at": "2026-07-16T09:11:00Z",
}
ingest_confirm = {
    "ingest_session_id": ingest_session_id,
    "upload_object_id": "quarantine/object/ing-01",
    "media_type": ingest_request["media_type"],
    "size_bytes": ingest_request["size_bytes"],
    "content_digest": ingest_request["content_digest"],
    "request_digest": "sha256:" + "0" * 64,
}
ingest_confirm["request_digest"] = digest_without(ingest_confirm, "request_digest")
ingest_scan = {
    "scan_result_id": ingest_session["scan_result_id"],
    "scan_result_digest": "sha256:" + "0" * 64,
    "ingest_session_id": ingest_session_id,
    "content_digest": ingest_request["content_digest"],
    "scanner_provider_revision_id": "spr_scanner_01J0000000000000000000",
    "scanner_profile": "artifact-malware-and-content-v1",
    "scanner_suite_digest": digest({"scanner_suite": "artifact-malware-and-content-v1"}),
    "result": "passed",
    "evidence_reference": "scan-evidence://ing-01",
    "evidence_digest": digest({"scan_evidence": "ing-01"}),
    "completed_at": "2026-07-16T09:10:50Z",
}
ingest_scan["scan_result_digest"] = digest_without(ingest_scan, "scan_result_digest")
ingest_session["scan_result_digest"] = ingest_scan["scan_result_digest"]
ingest_finalize = {
    "finalize_command_id": "ifin_01J00000000000000000000000",
    "command_digest": "sha256:" + "0" * 64,
    "authority": "platform_artifact_ledger",
    "ingest_session_id": ingest_session_id,
    "expected_state_version": 6,
    "confirmed_upload_digest": ingest_session["confirmed_upload_digest"],
    "scan_result_id": ingest_scan["scan_result_id"],
    "scan_result_digest": ingest_scan["scan_result_digest"],
    "idempotency_key": "artifact-ingest-finalize-idempotency-0001",
    "issued_at": "2026-07-16T09:10:55Z",
}
ingest_finalize["command_digest"] = digest_without(ingest_finalize, "command_digest")
write("examples/contracts/artifact-ingest-request.json", ingest_request)
write("examples/contracts/artifact-ingest-execution-budget.json", ingest_budget)
write("examples/contracts/artifact-ingest-policy-decision.json", ingest_policy)
write("examples/contracts/artifact-ingest-effective-permissions.json", ingest_permissions)
write("examples/contracts/artifact-ingest-session.json", ingest_session)
write("examples/contracts/artifact-ingest-response.json", {
    "session": ingest_session,
    "upload_url": "https://upload.agent-platform.test/quarantine/ing-01",
    "required_headers": {"Digest": "sha-256=:fixture:"},
})
write("examples/contracts/artifact-ingest-confirm-request.json", ingest_confirm)
write("examples/contracts/artifact-ingest-status-operation-descriptor.json", {
    "operation": "read_artifact_ingest_session", "ingest_session_id": ingest_session_id,
})
write("examples/contracts/artifact-ingest-scan-result.json", ingest_scan)
write("examples/contracts/artifact-ingest-finalize-command.json", ingest_finalize)
write("tests/semantic-invalid/artifact-ingest-cases.json", {
    "session": ingest_session,
    "request": ingest_request,
    "budget": ingest_budget,
    "policy": ingest_policy,
    "permissions": ingest_permissions,
    "scan_result": ingest_scan,
    "finalize_command": ingest_finalize,
    "cases": [
        {"id": "finalize-with-failed-scan", "mutation": "failed_scan"},
        {"id": "finalize-digest-mismatch", "mutation": "scan_digest_mismatch"},
        {"id": "provider-authority-finalize", "mutation": "provider_finalize_authority"},
        {"id": "session-policy-binding-mismatch", "mutation": "session_policy_binding_mismatch"},
        {"id": "policy-media-binding-mismatch", "mutation": "policy_media_binding_mismatch"},
        {"id": "permissions-scope-mismatch", "mutation": "permissions_scope_mismatch"},
    ],
})

event_data_schema = read("schemas/agent-runtime-event-data.schema.json")
event_registry_path = "event-types/agent-runtime-core-v1.json"
event_registry = read(event_registry_path)
event_dependencies = sorted(
    [
        read("schemas/capability-error.schema.json"),
        read("schemas/child-agent-run-spawn-request.schema.json"),
        read("schemas/runtime-input-envelope.schema.json"),
        read("schemas/runtime-input-content.schema.json"),
        read("schemas/usage-observation.schema.json"),
    ],
    key=lambda schema: schema["$id"],
)
event_data_digest = digest({"root": event_data_schema, "dependencies": event_dependencies})
for definition in event_registry["definitions"]:
    definition["data_schema"]["digest"] = event_data_digest
    definition["data_schema"]["digest_profile"] = "rfc8785-schema-closure-v1"
event_registry["registry_digest"] = digest_without(event_registry, "registry_digest")
write(event_registry_path, event_registry)

platform_event_schema = read("schemas/platform-core-event-data.schema.json")
platform_event_dependencies = [read("schemas/work-order-state.schema.json")]
platform_event_schema_digest = digest({
    "root": platform_event_schema,
    "dependencies": sorted(platform_event_dependencies, key=lambda schema: schema["$id"]),
})
platform_registry_path = "event-types/platform-core-v1.json"
platform_event_registry = read(platform_registry_path)
for definition in platform_event_registry["definitions"]:
    definition["data_schema"]["digest"] = platform_event_schema_digest
    definition["data_schema"]["digest_profile"] = "rfc8785-schema-closure-v1"
platform_event_registry["registry_digest"] = digest_without(platform_event_registry, "registry_digest")
write(platform_registry_path, platform_event_registry)
artifact_event_definition = next(
    item for item in platform_event_registry["definitions"]
    if item["type"] == "artifact.version.created"
)
write("examples/contracts/event-type-artifact-version-created.json", artifact_event_definition)

canonical_event = read("examples/contracts/canonical-event-v2.json")
canonical_event["producer_kind"] = "platform"
canonical_event["event_registry"] = {
    "registry_id": platform_event_registry["registry_id"],
    "registry_version": platform_event_registry["registry_version"],
    "registry_digest": platform_event_registry["registry_digest"],
}
canonical_event["dedupe_key"] = digest({
    "tenant_id": canonical_event["tenant_id"],
    "producer_id": canonical_event["producer_id"],
    "source_stream_id": canonical_event["source_stream_id"],
    "source_event_id": canonical_event["source_event_id"],
})
write("examples/contracts/canonical-event-v2.json", canonical_event)
write("examples/contracts/platform-core-event-data.json", canonical_event["data"])


def platform_core_event(
    fixture_name: str, event_type: str, aggregate_type: str, aggregate_id: str,
    data: dict[str, Any], *, conversation_id: str | None = None,
    execution_scope: dict[str, Any] | None = None,
) -> dict[str, Any]:
    event = copy.deepcopy(canonical_event)
    for field in (
        "conversation_id", "work_order_id", "turn_id", "branch_id",
        "input_message_id", "workspace_id", "work_sequence", "references",
        "execution_scope",
    ):
        event.pop(field, None)
    event.update({
        "event_id": f"evt_{fixture_name}_01J00000000000000000",
        "producer_id": "platform-core-ledger",
        "source_stream_id": f"{aggregate_type}/{aggregate_id}",
        "source_event_id": f"{event_type}/1",
        "source_cursor": "1",
        "aggregate": {"type": aggregate_type, "id": aggregate_id, "sequence": 1},
        "type": event_type,
        "data": data,
        "occurred_at": "2026-07-16T09:10:00Z",
        "recorded_at": "2026-07-16T09:10:00.100Z",
        "metadata": {
            "trace_id": f"trace-{fixture_name}",
            "correlation_id": aggregate_id,
        },
    })
    if conversation_id is not None:
        event["conversation_id"] = conversation_id
    if execution_scope is not None:
        event["execution_scope"] = copy.deepcopy(execution_scope)
    event["dedupe_key"] = digest({
        "tenant_id": event["tenant_id"],
        "producer_id": event["producer_id"],
        "source_stream_id": event["source_stream_id"],
        "source_event_id": event["source_event_id"],
    })
    write(f"examples/contracts/canonical-event-{fixture_name}.json", event)
    return event


branch_core_event = platform_core_event(
    "conversation-branch-forked", "conversation.branch.forked",
    "conversation_branch", branch_created["branch"]["branch_id"],
    {
        "branch_request_id": branch_create_request["branch_request_id"],
        "branch_id": branch_created["branch"]["branch_id"],
        "mode": "fork",
        "source_branch_id": branch_create_request["source_branch_id"],
        "source_message_id": branch_create_request["source_message_id"],
        "source_message_sequence": branch_create_request["source_message_sequence"],
        "workspace_revision_id": branch_created["workspace_revision"]["workspace_revision_id"],
        "workspace_revision_digest": branch_created["workspace_revision"]["revision_digest"],
        "request_digest": branch_create_request["request_digest"],
    },
    conversation_id=branch_create_request["conversation_id"],
)
artifact_operation_core_event = platform_core_event(
    "artifact-operation-succeeded", "artifact.operation.state.changed",
    "artifact_operation", preview_operation["artifact_operation_id"],
    {
        "artifact_operation_id": preview_operation["artifact_operation_id"],
        "operation_kind": preview_operation["operation_kind"],
        "state": preview_operation["status"],
        "state_version": preview_operation["state_version"],
        "provider_resolution_id": preview_operation["provider_resolution_id"],
        "invocation_id": preview_operation["invocation_id"],
        "request_digest": preview_operation["request_digest"],
        "invocation_request_digest": preview_operation["invocation_request_digest"],
        "terminal_stage": preview_operation["terminal_stage"],
        "terminal_evidence_digest": preview_operation["terminal_evidence_digest"],
    },
    execution_scope={
        "kind": "artifact_operation",
        "artifact_operation_id": preview_operation["artifact_operation_id"],
    },
)
artifact_ingest_core_event = platform_core_event(
    "artifact-ingest-finalized", "artifact.ingest.state.changed",
    "artifact_ingest", ingest_session["ingest_session_id"],
    {
        "ingest_session_id": ingest_session["ingest_session_id"],
        "state": ingest_session["status"],
        "state_version": ingest_session["state_version"],
        "content_digest": ingest_session["confirmed_upload_digest"],
        "scan_result_digest": ingest_scan["scan_result_digest"],
        "artifact_version_id": ingest_session["artifact_version_id"],
    },
    execution_scope={
        "kind": "artifact_ingest",
        "artifact_ingest_session_id": ingest_session["ingest_session_id"],
    },
)
compatibility_core_event = platform_core_event(
    "compatibility-decided", "compatibility.decided", "compatibility_decision",
    runtime_compatibility_decision["decision_id"],
    {
        "decision_id": runtime_compatibility_decision["decision_id"],
        "decision_digest": runtime_compatibility_decision["decision_digest"],
        "subject_kind": runtime_compatibility_decision["subject_kind"],
        "subject_id": runtime_compatibility_decision["subject_id"],
        "result": runtime_compatibility_decision["result"],
        "source_provider_revision_id": runtime_compatibility_decision["source_provider_revision_id"],
        "target_provider_revision_id": runtime_compatibility_decision["target_provider_revision_id"],
    },
)
secret_grant_core_event = platform_core_event(
    "secret-grant-issued", "secret.grant.state.changed", "secret_grant",
    secret_grant["secret_grant_id"],
    {
        "secret_grant_id": secret_grant["secret_grant_id"],
        "secret_grant_digest": secret_grant["secret_grant_digest"],
        "state": "issued",
        "evidence_digest": digest({"secret_grant_issued": secret_grant["secret_grant_id"]}),
    },
    execution_scope=secret_grant["execution_scope"],
)
write("tests/semantic-invalid/canonical-core-event-cases.json", {
    "artifact_operation": artifact_operation_core_event,
    "artifact_ingest": artifact_ingest_core_event,
    "compatibility": compatibility_core_event,
    "secret_grant": secret_grant_core_event,
    "cases": [
        {"id": "artifact-operation-event-missing-scope", "mutation": "artifact_operation_missing_scope"},
        {"id": "artifact-ingest-event-cross-scope", "mutation": "artifact_ingest_cross_scope"},
        {"id": "compatibility-event-with-execution-scope", "mutation": "compatibility_with_scope"},
        {"id": "secret-grant-event-missing-scope", "mutation": "secret_grant_missing_scope"},
    ],
})


manifest_path = "examples/contracts/run-manifest-v2.json"
manifest = read(manifest_path)
manifest["agent_run_id"] = manifest.pop("run_id", "agr_01J00000000000000000000000")
manifest["workflow_run_id"] = "wfr_01J00000000000000000000000"
manifest["tenant_id"] = "ten_01J00000000000000000000000"
manifest["run_topology"] = {
    "run_kind": "root",
    "root_agent_run_id": manifest["agent_run_id"],
    "run_depth": 0,
    "required_for_work_order_completion": True,
}
legacy_temporal = manifest.pop("temporal", None)
if "orchestration_binding" not in manifest:
    temporal_reference = legacy_temporal or {
        "namespace": "agent-platform",
        "workflow_id": "work-order/wrk_01J00000000000000000000000",
        "workflow_run_id": "temporal-run-01J00000000000000000",
    }
    orchestration_binding = {
        "engine_id": "temporal",
        "engine_version": "1.27",
        "workflow_execution_id": "wfx_01J00000000000000000000000",
        "native_execution_reference_digest": digest(temporal_reference),
        "worker_deployment": temporal_reference.get("worker_deployment", "agent-worker"),
        "worker_build_id": temporal_reference.get("worker_build_id", "worker-2026-07-16.1"),
        "versioning_behavior": "pinned",
        "binding_digest": "sha256:" + "0" * 64,
    }
    orchestration_binding["binding_digest"] = digest_without(orchestration_binding, "binding_digest")
    manifest["orchestration_binding"] = orchestration_binding
manifest["scenario"] = scenario_identity
manifest["capability_resolutions"] = [
    resolution(
        "res_agent_general_01J00000000000000", required_capabilities[0],
        "apr_01J00000000000000000000000", "pad_runtime_01J00000000000000000",
        "2026-07-16T09:01:00Z",
    ),
    resolution(
        "res_html_generate_01J0000000000000", required_capabilities[1],
        "hpr_01J00000000000000000000000", "pad_html_skill_01J000000000000000",
        "2026-07-16T09:01:01Z",
    ),
    resolution(
        "res_html_preview_01J00000000000000", required_capabilities[2],
        "rpr_01J00000000000000000000000", "pad_renderer_01J0000000000000000",
        "2026-07-16T09:01:02Z",
    ),
    resolution(
        "res_sandbox_exec_01J0000000000000",
        {"id": "sandbox.exec", "version": "1.0", "profile": "hardened"},
        "spr_01J00000000000000000000000", "pad_01J00000000000000000000000",
        "2026-07-16T09:01:03Z",
    ),
]
manifest["agent_runtime"] = {"resolution_id": manifest["capability_resolutions"][0]["resolution_id"]}
for sandbox in manifest["sandboxes"]:
    sandbox.pop("provider_revision", None)
    sandbox.pop("provider_instance_id", None)
    sandbox["resolution_id"] = "res_sandbox_exec_01J0000000000000"
    sandbox["sandbox_spec_digest"] = digest(sandbox_spec)
manifest["selected_experiences"] = [
    {
        "selection": {
            "kind": "template",
            "catalog_entry_id": template["template_id"],
            "revision_id": template["template_revision_id"],
            "revision_digest": template["revision_digest"],
            "capability_id": template["capability"]["id"],
            "parameter_values": {"theme": "dark"},
        },
        "provider_instance_id": revisions["tplpr_01J0000000000000000000000"]["provider_instance_id"],
        "provider_revision": template["provider_revision"],
    }
]
manifest.pop("commercial_authorization_digest", None)
manifest.pop("policy_decision_digest", None)
manifest.pop("execution_budget_digest", None)
manifest.pop("event_schema_version", None)
manifest["commercial_authorization"] = {
    "commercial_authorization_id": commercial["commercial_authorization_id"],
    "commercial_authorization_digest": commercial["commercial_authorization_digest"],
    "expires_at": commercial["expires_at"],
}
manifest["input"] = copy.deepcopy(runtime_input)
manifest["context_package"] = copy.deepcopy(context_package)
manifest.pop("artifact_grants", None)
manifest["artifact_access_requirements"] = [copy.deepcopy(artifact_requirement)]
manifest["execution_budget"] = copy.deepcopy(budget)
manifest["agent_run_budget_allocation"] = copy.deepcopy(root_budget_allocation)
manifest["policy_decision"] = copy.deepcopy(policy)
manifest["effective_permissions"] = copy.deepcopy(permissions)
manifest["gateway_bindings"] = copy.deepcopy(gateway_bindings)
manifest["authorization_renewal_policy"] = read(
    "examples/contracts/authorization-renewal-policy.json"
)
manifest["admission_limits"] = {
    "max_encoded_request_bytes": 8388608,
    "max_inline_input_bytes": 262144,
    "max_context_items": 512,
    "max_artifact_grants": 256,
}
manifest["event_registry"] = {
    "registry_id": event_registry["registry_id"],
    "registry_version": event_registry["registry_version"],
    "registry_digest": event_registry["registry_digest"],
}
manifest["conversation"]["workspace_revision_id"] = workspace_revision["workspace_revision_id"]
manifest["conversation"]["workspace_revision_digest"] = workspace_revision["revision_digest"]
manifest["workspace_binding"] = {
    "workspace_mode": "shared_branch_cas",
    "base_workspace_revision_id": workspace_revision["workspace_revision_id"],
    "base_workspace_revision_digest": workspace_revision["revision_digest"],
    "mount_access": "copy_on_write",
    "commit_mode": "shared_branch_cas",
    "expected_workspace_head_version": conversation_branch["workspace_head_version"],
}
manifest["location"] = {
    "placement_mode": "platform_managed",
    "region_id": "ap-southeast-1",
    "placement_policy_reference": "placement-policy/default-v1",
    "placement_decision_digest": "sha256:" + "0" * 64,
}
manifest["location"]["placement_decision_digest"] = digest_without(
    manifest["location"], "placement_decision_digest"
)
turn_request_for_manifest = read("examples/contracts/conversation-turn-request.json")
manifest.pop("request_digest", None)
manifest["request_binding"] = {
    "request_contract_id": "urn:agent-platform:conversation-turn-request:v1",
    "request_digest_profile": "rfc8785-request-excluding-execution-grant-v1",
    "request_digest": digest_without(turn_request_for_manifest, "execution_grant"),
}
manifest["run_manifest_digest"] = digest_without(manifest, "run_manifest_digest")
write(manifest_path, manifest)
manifest_with_provider_topology = copy.deepcopy(manifest)
manifest_with_provider_topology["location"]["cluster_id"] = "cluster-a"
write(
    "tests/invalid/run-manifest-location-with-provider-topology.json",
    manifest_with_provider_topology,
)

missing_sandbox_resolution = copy.deepcopy(manifest)
missing_sandbox_resolution["sandboxes"][0].pop("resolution_id")
write("tests/invalid/run-manifest-missing-sandbox-resolution.json", missing_sandbox_resolution)

empty_execution = copy.deepcopy(manifest)
empty_execution["capability_resolutions"] = []
write("tests/invalid/run-manifest-empty-execution.json", empty_execution)

no_sandbox_manifest = copy.deepcopy(manifest)
no_sandbox_manifest["capability_resolutions"] = [
    item for item in no_sandbox_manifest["capability_resolutions"]
    if item["resolution_id"] != "res_sandbox_exec_01J0000000000000"
]
no_sandbox_manifest["sandboxes"] = []
no_sandbox_manifest.pop("primary_sandbox_slot_key", None)
no_sandbox_manifest["effective_permissions"]["sandbox_slots"] = []
no_sandbox_manifest["effective_permissions"]["permissions_digest"] = digest_without(
    no_sandbox_manifest["effective_permissions"], "permissions_digest"
)
no_sandbox_manifest["policy_decision"]["effective_permissions_digest"] = no_sandbox_manifest[
    "effective_permissions"
]["permissions_digest"]
no_sandbox_manifest["policy_decision"]["decision_digest"] = digest_without(
    no_sandbox_manifest["policy_decision"], "decision_digest"
)
no_sandbox_manifest["location"] = {
    "placement_mode": "provider_managed",
    "region_id": None,
    "placement_policy_reference": "placement-policy/provider-managed-v1",
    "placement_decision_digest": "sha256:" + "0" * 64,
}
no_sandbox_manifest["location"]["placement_decision_digest"] = digest_without(
    no_sandbox_manifest["location"], "placement_decision_digest"
)
no_sandbox_manifest["run_manifest_digest"] = digest_without(no_sandbox_manifest, "run_manifest_digest")
write("examples/contracts/run-manifest-no-sandbox.json", no_sandbox_manifest)

context_path = "examples/contracts/run-admission-context.json"
context = read(context_path)
context["scenario"] = scenario_identity
context["scenario_definition"] = scenario
context["required_capabilities"] = required_capabilities
context["capability_definitions"] = capability_definitions
context["agent_runtime_capability"] = definition_by_capability["agent.runtime.execute"]
context["provider_revisions"] = list(revisions.values())
context["admission_decisions"] = list(decisions.values())
context["experience_requirements"] = copy.deepcopy(scenario["experience_requirements"])
context["experience_revisions"] = [template]
context["commercial_authorization"] = commercial
write(context_path, context)

scenario_digest = scenario["definition_digest"]
scenario_reference_paths = [
    ("examples/contracts/conversation-create-request.json", ("default_scenario", "definition_digest")),
    ("examples/contracts/conversation.json", ("default_scenario", "definition_digest")),
    ("examples/contracts/conversation-turn-request.json", ("scenario", "definition_digest")),
    ("examples/contracts/execution-grant-claims.json", ("scenario_definition_digest",)),
    ("examples/contracts/work-order.json", ("work", "scenario_definition_digest")),
]
for path, keys in scenario_reference_paths:
    value = read(path)
    target = value
    for key in keys[:-1]:
        target = target[key]
    target[keys[-1]] = scenario_digest
    write(path, value)

conversation_create_unbounded_metadata = read("examples/contracts/conversation-create-request.json")
conversation_create_unbounded_metadata["metadata"] = {"nested": {"unbounded": True}}
write(
    "tests/invalid/conversation-create-unbounded-metadata.json",
    conversation_create_unbounded_metadata,
)
work_order_unbounded_metadata = read("examples/contracts/work-order.json")
work_order_unbounded_metadata["metadata"] = {"nested": {"unbounded": True}}
write(
    "tests/invalid/work-order-unbounded-metadata.json",
    work_order_unbounded_metadata,
)

sandbox_status = {
    "sandbox_id": sandbox_spec["sandbox_id"],
    "tenant_id": sandbox_spec["tenant_id"],
    "work_order_id": sandbox_spec["work_order_id"],
    "workspace_id": sandbox_spec["workspace_id"],
    "provider_revision_id": sandbox_spec["provider_revision_id"],
    "desired_state": "ready",
    "observed_state": "ready",
    "generation": 1,
    "observed_generation": 1,
    "runtime_profile": sandbox_spec["runtime_profile"],
    "runtime_endpoint_reference": "provider-route:runtime-session-primary",
    "provider_state_reference": "provider-state:sandbox-primary",
    "lease_expires_at": sandbox_spec["lease"]["expires_at"],
    "created_at": "2026-07-16T09:00:00Z",
    "updated_at": "2026-07-16T09:01:00Z",
    "sandbox_slot_key": sandbox_spec["sandbox_slot_key"],
}
write("examples/contracts/sandbox-status.json", sandbox_status)
sandbox_status_with_topology = copy.deepcopy(sandbox_status)
sandbox_status_with_topology.update({
    "cluster_id": "cluster-a",
    "node_id": "node-a",
})
write(
    "tests/invalid/sandbox-status-with-provider-topology.json",
    sandbox_status_with_topology,
)

template_reference_paths = [
    ("examples/contracts/conversation-turn-request.json", ("experience_selections", 0, "revision_digest")),
    ("examples/contracts/work-order.json", ("work", "experience_selections", 0, "revision_digest")),
    ("examples/contracts/experience-catalog-entry.json", ("current_revision_digest",)),
    ("examples/contracts/experience-catalog-page.json", ("items", 0, "current_revision_digest")),
]
for path, keys in template_reference_paths:
    value = read(path)
    target: Any = value
    for key in keys[:-1]:
        target = target[key]
    target[keys[-1]] = template["revision_digest"]
    write(path, value)

grant = read(grant_path)
conversation_turn_request = read("examples/contracts/conversation-turn-request.json")
grant["principal_context"] = copy.deepcopy(principal_context)
grant["principal_context_digest"] = principal_context["principal_context_digest"]
grant["request_contract_id"] = "urn:agent-platform:conversation-turn-request:v1"
grant["request_digest_profile"] = "rfc8785-request-excluding-execution-grant-v1"
grant["request_digest"] = digest_without(conversation_turn_request, "execution_grant")
write(grant_path, grant)

manifest["request_binding"] = {
    "request_contract_id": grant["request_contract_id"],
    "request_digest_profile": grant["request_digest_profile"],
    "request_digest": grant["request_digest"],
}
manifest["run_manifest_digest"] = digest_without(manifest, "run_manifest_digest")
write(manifest_path, manifest)
no_sandbox_manifest["request_binding"] = copy.deepcopy(manifest["request_binding"])
no_sandbox_manifest["run_manifest_digest"] = digest_without(
    no_sandbox_manifest, "run_manifest_digest"
)
write("examples/contracts/run-manifest-no-sandbox.json", no_sandbox_manifest)

work_order_grant = copy.deepcopy(grant)
work_order_grant["jti"] = "grant_work_order_01J0000000000000000"
work_order_grant["nonce"] = "nonce-work-order-0123456789"
work_order_grant["request_contract_id"] = "urn:agent-platform:work-order-request:v1"
work_order_grant["request_digest"] = digest_without(read("examples/contracts/work-order.json"), "execution_grant")
write("examples/contracts/execution-grant-work-order-claims.json", work_order_grant)

control_request_path = "examples/contracts/work-order-control-request.json"
control_request = read(control_request_path)
control_input = read("examples/contracts/work-order-control-input.json")
control_input["content_digest"] = digest(control_input["content"])
write("examples/contracts/work-order-control-input.json", control_input)
control_request.pop("expected_message_head_sequence", None)
control_request["expected_message_head_version"] = conversation_branch["message_head_version"]
control_request["content"] = copy.deepcopy(control_input)
write(control_request_path, control_request)
control_grant = copy.deepcopy(grant)
control_grant["jti"] = "grant_control_01J00000000000000000"
control_grant["nonce"] = "nonce-work-control-0123456789"
control_grant["request_contract_id"] = "urn:agent-platform:work-order-control-request:v1"
control_grant["work_order_id"] = control_request["work_order_id"]
control_grant["control_request_id"] = control_request["control_request_id"]
for field in (
    "turn_id", "client_message_id", "scenario_id", "scenario_version",
    "scenario_definition_digest",
):
    control_grant.pop(field, None)
control_grant["request_digest"] = digest_without(control_request, "execution_grant")
write("examples/contracts/execution-grant-control-claims.json", control_grant)

cancel_control_request = copy.deepcopy(control_request)
cancel_control_request.update({
    "control_request_id": "ctl_cancel_01J0000000000000000000",
    "action": "cancel",
    "reason": "User requested cancellation of the active WorkOrder.",
})
for field in ("content", "expected_message_head_version"):
    cancel_control_request.pop(field, None)
write("examples/contracts/work-order-cancel-request.json", cancel_control_request)
cancel_control_grant = copy.deepcopy(control_grant)
cancel_control_grant.update({
    "jti": "grant_cancel_01J000000000000000000",
    "nonce": "nonce-work-cancel-0123456789",
    "control_request_id": cancel_control_request["control_request_id"],
    "request_digest": digest_without(cancel_control_request, "execution_grant"),
})
write("examples/contracts/execution-grant-cancel-claims.json", cancel_control_grant)

commercial_revocation_path = "examples/contracts/commercial-authorization-revocation.json"
commercial_revocation = read(commercial_revocation_path)
commercial_revocation.update({
    "external_tenant_id": grant["external_tenant_id"],
    "commercial_authorization_id": commercial["commercial_authorization_id"],
    "commercial_authorization_digest": commercial["commercial_authorization_digest"],
})
commercial_revocation["revocation_digest"] = digest_without(
    commercial_revocation, "revocation_digest"
)
write(commercial_revocation_path, commercial_revocation)
commercial_revocation_accepted = {
    "revocation_id": commercial_revocation["revocation_id"],
    "revocation_receipt_id": "carcp_01J0000000000000000000000",
    "revocation_receipt_digest": "sha256:" + "0" * 64,
    "revocation_digest": commercial_revocation["revocation_digest"],
    "tenant_id": manifest["tenant_id"],
    "client_app_id": grant["client_app_id"],
    "commercial_authorization_id": commercial["commercial_authorization_id"],
    "commercial_authorization_digest": commercial["commercial_authorization_digest"],
    "status": "accepted",
    "deny_effective_at": "2026-07-16T09:10:02Z",
    "work_session_revocations": [{
        "work_session_id": work_session_claims["jti"],
        "expected_session_version": work_session_claims["session_version"],
        "revocation_intent_id": "wsri_01J0000000000000000000000",
        "outbox_message_id": "out_wsri_01J0000000000000000000",
        "status": "enqueued",
    }],
    "execution_cancellation_targets": [
        {
            "execution_scope": {"kind": "work_order", "work_order_id": manifest["work_order_id"]},
            "expected_owner_state_version": 1,
            "action": "cancel",
            "cancellation_intent_id": "cani_work_01J000000000000000000",
            "outbox_message_id": "out_cani_work_01J00000000000000",
            "status": "enqueued",
        },
        {
            "execution_scope": {
                "kind": "artifact_operation",
                "artifact_operation_id": preview_operation["artifact_operation_id"],
            },
            "expected_owner_state_version": 4,
            "action": "cancel",
            "cancellation_intent_id": "cani_aop_01J0000000000000000000",
            "outbox_message_id": "out_cani_aop_01J000000000000000",
            "status": "enqueued",
        },
        {
            "execution_scope": {
                "kind": "artifact_ingest",
                "artifact_ingest_session_id": ingest_session["ingest_session_id"],
            },
            "expected_owner_state_version": 4,
            "action": "cancel",
            "cancellation_intent_id": "cani_ing_01J0000000000000000000",
            "outbox_message_id": "out_cani_ing_01J000000000000000",
            "status": "enqueued",
        },
    ],
    "fanout_status": "in_progress",
    "accepted_at": "2026-07-16T09:10:02Z",
}
commercial_revocation_accepted["revocation_receipt_digest"] = digest_without(
    commercial_revocation_accepted, "revocation_receipt_digest"
)
write(
    "examples/contracts/commercial-authorization-revocation-accepted.json",
    commercial_revocation_accepted,
)
artifact_operation_cancel_target = next(
    target
    for target in commercial_revocation_accepted["execution_cancellation_targets"]
    if target["execution_scope"] == {
        "kind": "artifact_operation",
        "artifact_operation_id": preview_operation["artifact_operation_id"],
    }
)
artifact_operation_cancel_requested = copy.deepcopy(preview_operation)
for field in (
    "result_reference", "terminal_evidence_digest", "terminal_stage", "completed_at",
):
    artifact_operation_cancel_requested.pop(field, None)
artifact_operation_cancel_requested.update({
    "status": "cancel_requested",
    "state_version": artifact_operation_cancel_target["expected_owner_state_version"] + 1,
    "cancellation_intent_id": artifact_operation_cancel_target["cancellation_intent_id"],
    "cancellation_source_kind": "commercial_authorization_revocation_receipt",
    "cancellation_source_id": commercial_revocation_accepted["revocation_receipt_id"],
    "cancellation_source_digest": commercial_revocation_accepted["revocation_receipt_digest"],
    "cancellation_outbox_message_id": artifact_operation_cancel_target["outbox_message_id"],
    "cancellation_requested_at": commercial_revocation_accepted["accepted_at"],
    "updated_at": commercial_revocation_accepted["accepted_at"],
})
write(
    "examples/contracts/artifact-operation-cancel-requested.json",
    artifact_operation_cancel_requested,
)
artifact_operation_cancel_invocation = copy.deepcopy(preview_invocation)
artifact_operation_cancel_invocation.update({
    "status": "executing",
    "updated_at": commercial_revocation_accepted["accepted_at"],
})
for field in ("result_reference", "completed_at"):
    artifact_operation_cancel_invocation.pop(field, None)
write(
    "examples/contracts/artifact-operation-cancel-requested-invocation.json",
    artifact_operation_cancel_invocation,
)
artifact_operation_cancellation_reconciling = copy.deepcopy(
    artifact_operation_cancel_requested
)
artifact_operation_cancellation_reconciling.update({
    "status": "cancellation_reconciling",
    "state_version": artifact_operation_cancel_requested["state_version"] + 2,
    "cancellation_reconciliation_case_id": "irc_aop_cancel_01J000000000000000000",
    "updated_at": "2026-07-16T09:10:04Z",
})
write(
    "examples/contracts/artifact-operation-cancellation-reconciling.json",
    artifact_operation_cancellation_reconciling,
)
artifact_operation_cancellation_reconciling_invocation = copy.deepcopy(
    artifact_operation_cancel_invocation
)
artifact_operation_cancellation_reconciling_invocation.update({
    "status": "reconciling",
    "reconciliation_case_id": artifact_operation_cancellation_reconciling[
        "cancellation_reconciliation_case_id"
    ],
    "reconciliation_deadline_at": "2026-07-16T10:10:04Z",
    "updated_at": artifact_operation_cancellation_reconciling["updated_at"],
})
write(
    "examples/contracts/artifact-operation-cancellation-reconciling-invocation.json",
    artifact_operation_cancellation_reconciling_invocation,
)
artifact_operation_cancel_event = platform_core_event(
    "artifact-operation-cancel-requested", "artifact.operation.state.changed",
    "artifact_operation", artifact_operation_cancel_requested["artifact_operation_id"],
    {
        "artifact_operation_id": artifact_operation_cancel_requested["artifact_operation_id"],
        "operation_kind": artifact_operation_cancel_requested["operation_kind"],
        "state": artifact_operation_cancel_requested["status"],
        "state_version": artifact_operation_cancel_requested["state_version"],
        "provider_resolution_id": artifact_operation_cancel_requested["provider_resolution_id"],
        "invocation_id": artifact_operation_cancel_requested["invocation_id"],
        "request_digest": artifact_operation_cancel_requested["request_digest"],
        "invocation_request_digest": artifact_operation_cancel_requested["invocation_request_digest"],
        "cancellation_intent_id": artifact_operation_cancel_requested["cancellation_intent_id"],
        "cancellation_source_kind": artifact_operation_cancel_requested["cancellation_source_kind"],
        "cancellation_source_id": artifact_operation_cancel_requested["cancellation_source_id"],
        "cancellation_source_digest": artifact_operation_cancel_requested["cancellation_source_digest"],
        "cancellation_outbox_message_id": artifact_operation_cancel_requested["cancellation_outbox_message_id"],
        "cancellation_requested_at": artifact_operation_cancel_requested["cancellation_requested_at"],
    },
    execution_scope={
        "kind": "artifact_operation",
        "artifact_operation_id": artifact_operation_cancel_requested["artifact_operation_id"],
    },
)
artifact_operation_cancel_event["aggregate"]["sequence"] = (
    artifact_operation_cancel_requested["state_version"]
)
artifact_operation_cancel_event["source_event_id"] = (
    f"artifact.operation.state.changed/{artifact_operation_cancel_requested['state_version']}"
)
artifact_operation_cancel_event["source_cursor"] = str(
    artifact_operation_cancel_requested["state_version"]
)
artifact_operation_cancel_event["occurred_at"] = (
    artifact_operation_cancel_requested["cancellation_requested_at"]
)
artifact_operation_cancel_event["recorded_at"] = "2026-07-16T09:10:02.100Z"
artifact_operation_cancel_event["dedupe_key"] = digest({
    "tenant_id": artifact_operation_cancel_event["tenant_id"],
    "producer_id": artifact_operation_cancel_event["producer_id"],
    "source_stream_id": artifact_operation_cancel_event["source_stream_id"],
    "source_event_id": artifact_operation_cancel_event["source_event_id"],
})
write(
    "examples/contracts/canonical-event-artifact-operation-cancel-requested.json",
    artifact_operation_cancel_event,
)
artifact_operation_cancel_missing_source = copy.deepcopy(
    artifact_operation_cancel_requested
)
artifact_operation_cancel_missing_source.pop("cancellation_source_digest")
write(
    "tests/invalid/artifact-operation-cancel-requested-missing-source.json",
    artifact_operation_cancel_missing_source,
)
write("tests/semantic-invalid/artifact-operation-cancellation-cases.json", {
    "cancel_requested_operation": copy.deepcopy(artifact_operation_cancel_requested),
    "cancel_requested_invocation": copy.deepcopy(artifact_operation_cancel_invocation),
    "cancellation_reconciling_operation": copy.deepcopy(
        artifact_operation_cancellation_reconciling
    ),
    "cancellation_reconciling_invocation": copy.deepcopy(
        artifact_operation_cancellation_reconciling_invocation
    ),
    "receipt": copy.deepcopy(commercial_revocation_accepted),
    "state_machine_cases": [
        {
            "id": "running-missing-cancel-intent-path",
            "mutation": "remove_active_cancel_path",
            "state": "running",
        },
        {
            "id": "running-directly-cancelled",
            "mutation": "direct_active_cancelled",
            "state": "running",
        },
        {"id": "cancellation-reconciliation-retry", "mutation": "cancellation_retry"},
        {
            "id": "cancellation-ambiguous-success",
            "mutation": "ambiguous_cancellation_success",
        },
        {
            "id": "cancel-unknown-without-reconciliation",
            "mutation": "remove_unknown_reconciliation",
        },
    ],
    "binding_cases": [
        {
            "id": "cancellation-source-receipt-digest-mismatch",
            "mutation": "source_receipt_digest_mismatch",
        },
        {"id": "cancellation-intent-id-mismatch", "mutation": "intent_id_mismatch"},
        {"id": "cancellation-outbox-mismatch", "mutation": "outbox_message_mismatch"},
        {"id": "cancellation-before-receipt", "mutation": "requested_before_receipt"},
        {"id": "cancellation-stale-owner-cas", "mutation": "stale_owner_cas"},
        {
            "id": "cancellation-invocation-already-terminal",
            "mutation": "invocation_status_terminal",
        },
        {
            "id": "cancellation-invocation-binding-mismatch",
            "mutation": "invocation_binding_mismatch",
        },
        {
            "id": "cancellation-reconciliation-case-mismatch",
            "mutation": "reconciliation_case_mismatch",
            "owner": "cancellation_reconciling",
        },
    ],
})
invalid_commercial_revocation = copy.deepcopy(commercial_revocation)
invalid_commercial_revocation["work_order_id"] = manifest["work_order_id"]
write(
    "tests/invalid/commercial-authorization-revocation-with-platform-command.json",
    invalid_commercial_revocation,
)
write("tests/semantic-invalid/commercial-revocation-fanout-cases.json", {
    "notice": copy.deepcopy(commercial_revocation),
    "receipt": copy.deepcopy(commercial_revocation_accepted),
    "expected_execution_scopes": [
        copy.deepcopy(item["execution_scope"])
        for item in commercial_revocation_accepted["execution_cancellation_targets"]
    ],
    "cases": [
        {"id": "revocation-receipt-digest-mismatch", "mutation": "digest_mismatch"},
        {"id": "revocation-missing-active-target", "mutation": "missing_target"},
        {"id": "revocation-duplicate-outbox", "mutation": "duplicate_outbox"},
        {"id": "revocation-completed-with-pending-target", "mutation": "premature_completed"},
        {"id": "revocation-receipt-authorization-mismatch", "mutation": "authorization_mismatch"},
    ],
})

recording_path = "examples/contracts/runtime-recording.json"
recording = read(recording_path)
recording_chunk = read("examples/contracts/runtime-recording-chunk.json")
recording["channels"] = [recording_chunk["channel"]]
recording["chunk_count"] = 1
recording_manifest_path = "examples/contracts/runtime-recording-manifest.json"
recording_manifest = read(recording_manifest_path)
recording_manifest["recording"] = copy.deepcopy(recording)
recording_manifest["chunks"] = [recording_chunk]
unsigned_recording_manifest = copy.deepcopy(recording_manifest)
unsigned_recording_manifest.pop("manifest_digest", None)
unsigned_recording_manifest["recording"].pop("manifest_digest", None)
recording_manifest_digest = digest(unsigned_recording_manifest)
recording_manifest["recording"]["manifest_digest"] = recording_manifest_digest
recording_manifest["manifest_digest"] = recording_manifest_digest
write(recording_manifest_path, recording_manifest)
recording = recording_manifest["recording"]
write(recording_path, recording)
recording_page = read("examples/contracts/runtime-recording-page.json")
recording_page["recordings"] = [recording]
write("examples/contracts/runtime-recording-page.json", recording_page)

runtime_start = read("examples/contracts/agent-runtime-start-request.json")
runtime_start["tenant_id"] = manifest["tenant_id"]
runtime_start["workflow_run_id"] = manifest["workflow_run_id"]
runtime_start["run_manifest_digest"] = manifest["run_manifest_digest"]
runtime_start["agent_run_id"] = manifest["agent_run_id"]
runtime_start["workspace_revision_id"] = workspace_revision["workspace_revision_id"]
runtime_start["workspace_revision_digest"] = workspace_revision["revision_digest"]
runtime_start["deadline_at"] = "2026-07-16T09:15:00Z"
artifact_grant["execution_scope"] = {
    "kind": "work_order",
    "work_order_id": manifest["work_order_id"],
}
artifact_grant["expires_at"] = "2026-07-16T09:15:00Z"
artifact_grant["grant_digest"] = digest_without(artifact_grant, "grant_digest")
write("examples/contracts/artifact-grant.json", artifact_grant)


def make_runtime_authorization(
    manifest_value: dict[str, Any], start_value: dict[str, Any], authorization_id: str,
) -> dict[str, Any]:
    value = read("examples/contracts/runtime-authorization.json")
    value.update({
        "authorization_id": authorization_id,
        "authorization_sequence": 1,
        "predecessor_authorization_digest": None,
        "renewal_reason": "initial_dispatch",
        "tenant_id": manifest_value["tenant_id"],
        "work_order_id": manifest_value["work_order_id"],
        "runtime_run_id": start_value["runtime_run_id"],
        "run_manifest_digest": manifest_value["run_manifest_digest"],
        "commercial_authorization": copy.deepcopy(manifest_value["commercial_authorization"]),
        "execution_budget": copy.deepcopy(manifest_value["execution_budget"]),
        "agent_run_budget_allocation": copy.deepcopy(
            manifest_value["agent_run_budget_allocation"]
        ),
        "policy_decision": copy.deepcopy(manifest_value["policy_decision"]),
        "effective_permissions": copy.deepcopy(manifest_value["effective_permissions"]),
        "artifact_grants": [copy.deepcopy(artifact_grant)],
        "issued_at": "2026-07-16T09:01:00Z",
        "expires_at": "2026-07-16T09:15:00Z",
    })
    value["artifact_grants"][0]["grant_id"] = f"artg_{authorization_id}"
    value["artifact_grants"][0].update({
        "runtime_run_id": start_value["runtime_run_id"],
        "invocation_id": start_value["invocation_id"],
        "invocation_attempt_id": start_value["invocation_attempt_id"],
    })
    value["artifact_grants"][0]["grant_digest"] = digest_without(
        value["artifact_grants"][0], "grant_digest"
    )
    value["authorization_digest"] = digest_without(value, "authorization_digest")
    return value


runtime_authorization = make_runtime_authorization(
    manifest, runtime_start, "rauth_01J000000000000000000000"
)
write("examples/contracts/runtime-authorization.json", runtime_authorization)
renewed_authorization = copy.deepcopy(runtime_authorization)
renewed_authorization.update({
    "authorization_id": "rauth_01J000000000000000000001",
    "authorization_sequence": 2,
    "predecessor_authorization_digest": runtime_authorization["authorization_digest"],
    "renewal_reason": "adapter_restart",
    "issued_at": "2026-07-16T09:05:00Z",
})
renewed_authorization["artifact_grants"][0]["grant_id"] = "artg_01J0000000000000000000001"
renewed_authorization["artifact_grants"][0]["issued_at"] = "2026-07-16T09:05:00Z"
renewed_authorization["artifact_grants"][0]["invocation_attempt_id"] = (
    "iat_runtime_01J0000000000000001"
)
renewed_authorization["artifact_grants"][0]["grant_digest"] = digest_without(
    renewed_authorization["artifact_grants"][0], "grant_digest"
)
renewed_authorization["authorization_digest"] = digest_without(
    renewed_authorization, "authorization_digest"
)
write("examples/contracts/runtime-authorization-renewed.json", renewed_authorization)
for legacy_field in ("artifact_grants", "execution_budget", "policy_decision", "effective_permissions"):
    runtime_start.pop(legacy_field, None)
for field in (
    "input", "context_package", "gateway_bindings", "admission_limits", "run_topology",
    "workspace_binding",
):
    runtime_start[field] = copy.deepcopy(manifest[field])
runtime_start["runtime_authorization"] = copy.deepcopy(runtime_authorization)
runtime_start["request_digest"] = digest_without(runtime_start, "request_digest")
write("examples/contracts/agent-runtime-start-request.json", runtime_start)

no_sandbox_runtime_start = copy.deepcopy(runtime_start)
no_sandbox_runtime_start["run_manifest_digest"] = no_sandbox_manifest["run_manifest_digest"]
no_sandbox_runtime_start["sandbox_bindings"] = []
for field in (
    "input", "context_package", "gateway_bindings", "admission_limits", "run_topology",
    "workspace_binding",
):
    no_sandbox_runtime_start[field] = copy.deepcopy(no_sandbox_manifest[field])
no_sandbox_runtime_start["runtime_authorization"] = make_runtime_authorization(
    no_sandbox_manifest,
    no_sandbox_runtime_start,
    "rauth_no_sandbox_01J000000000000000",
)
no_sandbox_runtime_start["request_digest"] = digest_without(no_sandbox_runtime_start, "request_digest")
write("examples/contracts/agent-runtime-start-no-sandbox.json", no_sandbox_runtime_start)

child_budget_limits = {
    name: budget["limits"][name] for name in AGENT_RUN_RESOURCE_LIMIT_NAMES
}
child_budget_limits.update({
    "max_input_tokens": 20000,
    "max_output_tokens": 5000,
    "max_model_requests": 40,
    "max_sandbox_seconds": 600,
    "max_network_bytes": 20971520,
    "max_storage_bytes": 20971520,
    "max_artifact_count": 5,
    "max_conversion_count": 1,
})
child_budget_allocation = {
    "allocation_id": "abal_child_01J00000000000000000000",
    "allocation_digest": "sha256:" + "0" * 64,
    "tenant_id": budget["tenant_id"],
    "work_order_id": work_order_id,
    "agent_run_id": "agr_child_01J0000000000000000000",
    "parent_allocation_id": root_budget_allocation["allocation_id"],
    "parent_allocation_digest": root_budget_allocation["allocation_digest"],
    "work_order_budget_id": budget["budget_id"],
    "work_order_budget_digest": budget["budget_digest"],
    "limits": child_budget_limits,
    "issued_at": "2026-07-16T09:02:01Z",
    "expires_at": budget["expires_at"],
}
child_budget_allocation["allocation_digest"] = digest_without(
    child_budget_allocation, "allocation_digest"
)
write("examples/contracts/child-agent-run-budget-allocation.json", child_budget_allocation)

child_manifest = copy.deepcopy(manifest)
child_manifest["agent_run_id"] = child_budget_allocation["agent_run_id"]
child_manifest["run_topology"] = {
    "run_kind": "subagent",
    "root_agent_run_id": manifest["agent_run_id"],
    "parent_agent_run_id": manifest["agent_run_id"],
    "spawn_request_id": child_spawn_request["spawn_request_id"],
    "run_depth": 1,
    "required_for_work_order_completion": True,
}
child_manifest["input"] = copy.deepcopy(child_spawn_request["delegated_input"])
child_manifest["workspace_binding"] = {
    "workspace_mode": child_spawn_request["workspace_mode"],
    "base_workspace_revision_id": manifest["conversation"]["workspace_revision_id"],
    "base_workspace_revision_digest": manifest["conversation"]["workspace_revision_digest"],
    "mount_access": "copy_on_write",
    "commit_mode": "isolated_revision_merge_cas",
    "expected_workspace_head_version": manifest["workspace_binding"][
        "expected_workspace_head_version"
    ],
}
child_sandbox_spec = copy.deepcopy(sandbox_spec)
child_sandbox_spec.update({
    "sandbox_id": "sbx_child_01J0000000000000000000",
    "sandbox_slot_key": "subagent/researcher",
})
child_sandbox_spec["workspace"].update({
    "base_revision_id": child_manifest["workspace_binding"]["base_workspace_revision_id"],
    "base_revision_digest": child_manifest["workspace_binding"][
        "base_workspace_revision_digest"
    ],
    "base_workspace_head_version": child_manifest["workspace_binding"][
        "expected_workspace_head_version"
    ],
    "commit_mode": "cas_new_revision",
})
write("examples/contracts/child-sandbox-spec.json", child_sandbox_spec)
child_manifest["agent_run_budget_allocation"] = copy.deepcopy(child_budget_allocation)
child_manifest["sandboxes"][0]["sandbox_slot_key"] = "subagent/researcher"
child_manifest["sandboxes"][0]["sandbox_id"] = "sbx_child_01J0000000000000000000"
child_manifest["sandboxes"][0]["sandbox_spec_digest"] = digest(child_sandbox_spec)
child_manifest["primary_sandbox_slot_key"] = "subagent/researcher"
child_manifest["effective_permissions"]["permissions_id"] = (
    "perm_child_01J0000000000000000000"
)
child_manifest["effective_permissions"]["sandbox_slots"][0]["sandbox_slot_key"] = (
    "subagent/researcher"
)
child_manifest["effective_permissions"]["permissions_digest"] = digest_without(
    child_manifest["effective_permissions"], "permissions_digest"
)
child_manifest["policy_decision"]["effective_permissions_digest"] = child_manifest[
    "effective_permissions"
]["permissions_digest"]
child_manifest["policy_decision"]["decision_id"] = "pol_child_01J00000000000000000000"
child_manifest["policy_decision"]["decision_digest"] = digest_without(
    child_manifest["policy_decision"], "decision_digest"
)
child_manifest["run_manifest_digest"] = digest_without(
    child_manifest, "run_manifest_digest"
)
write("examples/contracts/child-run-manifest-v2.json", child_manifest)

child_runtime_start = copy.deepcopy(runtime_start)
child_runtime_start.update({
    "runtime_run_id": "rtr_child_01J0000000000000000000",
    "agent_run_id": child_manifest["agent_run_id"],
    "invocation_id": "inv_runtime_child_01J0000000000000",
    "invocation_attempt_id": "iat_runtime_child_01J00000000000",
    "idempotency_key": "runtime-child-start-key-0001",
    "run_manifest_digest": child_manifest["run_manifest_digest"],
    "run_topology": copy.deepcopy(child_manifest["run_topology"]),
    "workspace_binding": copy.deepcopy(child_manifest["workspace_binding"]),
    "input": copy.deepcopy(child_manifest["input"]),
    "sandbox_bindings": [{
        "sandbox_slot_key": "subagent/researcher",
        "sandbox_id": "sbx_child_01J0000000000000000000",
    }],
})
child_runtime_start.pop("input_message_id", None)
child_runtime_start["runtime_authorization"] = make_runtime_authorization(
    child_manifest, child_runtime_start, "rauth_child_01J000000000000000000"
)
child_runtime_start["request_digest"] = digest_without(
    child_runtime_start, "request_digest"
)
write("examples/contracts/child-agent-runtime-start-request.json", child_runtime_start)

child_agent_run = {
    "agent_run_id": child_manifest["agent_run_id"],
    "tenant_id": child_manifest["tenant_id"],
    "runtime_run_id": child_runtime_start["runtime_run_id"],
    "workflow_run_id": child_manifest["workflow_run_id"],
    "work_order_id": child_manifest["work_order_id"],
    "root_agent_run_id": manifest["agent_run_id"],
    "parent_agent_run_id": manifest["agent_run_id"],
    "spawn_request_id": child_spawn_request["spawn_request_id"],
    "run_kind": "subagent",
    "run_depth": 1,
    "required_for_work_order_completion": True,
    "agent_role": child_spawn_request["requested_agent_role"],
    "runtime_provider_resolution_id": child_manifest["agent_runtime"]["resolution_id"],
    "run_manifest_digest": child_manifest["run_manifest_digest"],
    "created_at": "2026-07-16T09:02:01Z",
}
write("examples/contracts/child-agent-run.json", child_agent_run)

child_admission_decision = {
    "decision_id": "cadm_01J0000000000000000000000",
    "decision_digest": "sha256:" + "0" * 64,
    "spawn_request_id": child_spawn_request["spawn_request_id"],
    "spawn_request_digest": child_spawn_request["request_digest"],
    "tenant_id": child_manifest["tenant_id"],
    "work_order_id": child_manifest["work_order_id"],
    "workflow_run_id": child_manifest["workflow_run_id"],
    "parent_agent_run_id": manifest["agent_run_id"],
    "outcome": "accepted",
    "reason_codes": ["admitted"],
    "child_agent_run_id": child_manifest["agent_run_id"],
    "runtime_run_id": child_runtime_start["runtime_run_id"],
    "runtime_provider_resolution_id": child_manifest["agent_runtime"]["resolution_id"],
    "run_manifest_digest": child_manifest["run_manifest_digest"],
    "budget_allocation": copy.deepcopy(child_budget_allocation),
    "workspace_binding": copy.deepcopy(child_manifest["workspace_binding"]),
    "decided_at": "2026-07-16T09:02:01Z",
}
child_admission_decision["decision_digest"] = digest_without(
    child_admission_decision, "decision_digest"
)
write(
    "examples/contracts/child-agent-run-admission-decision.json",
    child_admission_decision,
)

runtime_status = read("examples/contracts/agent-runtime-run-status.json")
runtime_status["tenant_id"] = manifest["tenant_id"]
runtime_status["workflow_run_id"] = manifest["workflow_run_id"]
runtime_status["agent_run_id"] = manifest["agent_run_id"]
runtime_status["checkpoint"] = copy.deepcopy(runtime_checkpoint)
write("examples/contracts/agent-runtime-run-status.json", runtime_status)

runtime_command = read("examples/contracts/agent-runtime-command.json")
runtime_command["authorized_control_request_id"] = control_request["control_request_id"]
runtime_command["invocation_id"] = "inv_runtime_command_01J0000000000000"
runtime_command["deadline_at"] = "2026-07-16T09:14:00Z"
control_runtime_input = read("examples/contracts/work-order-control-runtime-input.json")
control_runtime_input["content"] = copy.deepcopy(control_request["content"]["content"])
control_runtime_input["content_digest"] = control_request["content"]["content_digest"]
write("examples/contracts/work-order-control-runtime-input.json", control_runtime_input)
runtime_command["input_id"] = control_runtime_input["input_id"]
runtime_command["input_content_digest"] = control_runtime_input["content_digest"]
runtime_command["command_digest"] = digest_without(runtime_command, "command_digest")
write("examples/contracts/agent-runtime-command.json", runtime_command)

spawn_decision_command = {
    "command_id": "cmd_spawn_decision_01J00000000000000",
    "command_digest": "sha256:" + "0" * 64,
    "runtime_run_id": runtime_start["runtime_run_id"],
    "command_sequence": 2,
    "type": "subagent_spawn_decision",
    "spawn_request_id": child_spawn_request["spawn_request_id"],
    "child_agent_run_admission_decision_id": child_admission_decision["decision_id"],
    "child_agent_run_admission_decision_digest": child_admission_decision["decision_digest"],
    "spawn_outcome": "accepted",
    "spawn_reason_codes": copy.deepcopy(child_admission_decision["reason_codes"]),
    "child_agent_run_id": child_agent_run["agent_run_id"],
    "invocation_id": "inv_spawn_decision_01J000000000000",
    "invocation_attempt_id": "iat_spawn_decision_01J0000000000",
    "fencing_token": 2,
    "idempotency_key": "spawn-decision-command-key-0001",
    "deadline_at": "2026-07-16T09:04:00Z",
}
spawn_decision_command["command_digest"] = digest_without(
    spawn_decision_command, "command_digest"
)
write("examples/contracts/agent-runtime-subagent-spawn-decision-command.json", spawn_decision_command)

runtime_task_started = {
    "task_id": "task_subagent_01J0000000000000000",
    "task_kind": "subagent",
    "status": "running",
    "title": "Research cited sources",
    "updated_at": "2026-07-16T09:02:02Z",
    "child_agent_run_id": child_agent_run["agent_run_id"],
    "spawn_request_id": child_spawn_request["spawn_request_id"],
}
write("examples/contracts/agent-runtime-task-started-event-data.json", runtime_task_started)

system_safety_control_path = "examples/contracts/system-safety-control.json"
system_safety_control = read(system_safety_control_path)
system_safety_control.update({
    "tenant_id": manifest["tenant_id"],
    "work_order_id": manifest["work_order_id"],
    "runtime_run_id": runtime_start["runtime_run_id"],
    "action": "cancel",
    "reason": "commercial_authorization_expired",
    "trigger_evidence": {
        "evidence_id": runtime_authorization["authorization_id"],
        "evidence_contract_id": "urn:agent-platform:runtime-authorization:v1",
        "evidence_digest": runtime_authorization["authorization_digest"],
        "observed_at": "2026-07-16T09:15:01Z",
    },
    "issued_by": "platform_safety_controller",
    "issuer_subject_id": "spn_agent_safety_controller",
    "issued_at": "2026-07-16T09:16:00Z",
})
system_safety_control["control_digest"] = digest_without(
    system_safety_control, "control_digest"
)
write(system_safety_control_path, system_safety_control)

system_safety_command_path = "examples/contracts/agent-runtime-system-safety-command.json"
system_safety_command = read(system_safety_command_path)
system_safety_command.update({
    "runtime_run_id": runtime_start["runtime_run_id"],
    "type": system_safety_control["action"],
    "system_safety_control_id": system_safety_control["safety_control_id"],
    "system_safety_control_digest": system_safety_control["control_digest"],
    "deadline_at": "2026-07-16T09:21:00Z",
})
system_safety_command["command_digest"] = digest_without(
    system_safety_command, "command_digest"
)
write(system_safety_command_path, system_safety_command)

write("examples/contracts/platform-system-safety-control-event-data.json", {
    "safety_control_id": system_safety_control["safety_control_id"],
    "runtime_run_id": system_safety_control["runtime_run_id"],
    "action": system_safety_control["action"],
    "reason": system_safety_control["reason"],
    "trigger_evidence_digest": system_safety_control["trigger_evidence"]["evidence_digest"],
    "control_digest": system_safety_control["control_digest"],
    "issued_at": system_safety_control["issued_at"],
})

runtime_capabilities = read("examples/contracts/agent-runtime-capabilities.json")
runtime_capabilities.pop("event_schema_versions", None)
runtime_capabilities["event_registries"] = [{
    "registry_id": event_registry["registry_id"],
    "registry_version": event_registry["registry_version"],
    "registry_digest": event_registry["registry_digest"],
}]
runtime_capabilities["checkpoint_profiles"] = [{
    "profile_id": "runtime-checkpoint-compatibility-v1",
    "suite_id": HISTORICAL_RUNTIME_SUITE["suite_id"],
    "suite_version": HISTORICAL_RUNTIME_SUITE["suite_version"],
    "suite_digest": HISTORICAL_RUNTIME_SUITE["suite_digest"],
}]
write("examples/contracts/agent-runtime-capabilities.json", runtime_capabilities)

runtime_token_base = read("examples/contracts/agent-runtime-invocation-token-claims.json")
runtime_resolution = next(
    item for item in manifest["capability_resolutions"]
    if item["resolution_id"] == manifest["agent_runtime"]["resolution_id"]
)
runtime_token_base.pop("request_digest", None)
runtime_token_base.update({
    "iss": "agent-platform",
    "iat": 1784192460,
    "nbf": 1784192460,
    "exp": 1784192760,
    "aud": runtime_resolution["selected_provider_audience"],
    "tenant_id": manifest["tenant_id"],
    "provider_revision_id": revisions["apr_01J00000000000000000000000"]["provider_revision_id"],
    "runtime_run_id": runtime_start["runtime_run_id"],
    "agent_run_id": manifest["agent_run_id"],
    "workflow_run_id": manifest["workflow_run_id"],
    "work_order_id": manifest["work_order_id"],
    "run_manifest_digest": manifest["run_manifest_digest"],
    "runtime_authorization_digest": runtime_authorization["authorization_digest"],
    "policy_decision_digest": runtime_authorization["policy_decision"]["decision_digest"],
    "execution_budget_digest": runtime_authorization["execution_budget"]["budget_digest"],
    "effective_permissions_digest": runtime_authorization["effective_permissions"]["permissions_digest"],
})
runtime_status_descriptor = {
    "operation": "read_status",
    "runtime_run_id": runtime_start["runtime_run_id"],
    "invocation_id": runtime_start["invocation_id"],
    "invocation_attempt_id": runtime_start["invocation_attempt_id"],
    "fencing_token": runtime_start["fencing_token"],
}
write("examples/contracts/agent-runtime-status-operation-descriptor.json", runtime_status_descriptor)
runtime_event_descriptor = {
    "operation": "read_events",
    "runtime_run_id": runtime_start["runtime_run_id"],
    "invocation_id": runtime_start["invocation_id"],
    "invocation_attempt_id": runtime_start["invocation_attempt_id"],
    "fencing_token": runtime_start["fencing_token"],
    "after_event_sequence": 0,
    "limit": 1000,
}
write("examples/contracts/agent-runtime-event-read-operation-descriptor.json", runtime_event_descriptor)
runtime_operations = {
    "start": (
        "examples/contracts/agent-runtime-invocation-token-claims.json",
        "urn:agent-platform:agent-runtime-start-request:v1",
        "rfc8785-request-excluding-request-digest-v1",
        runtime_start["request_digest"],
        runtime_start,
    ),
    "submit_command": (
        "examples/contracts/agent-runtime-command-token-claims.json",
        "urn:agent-platform:agent-runtime-command:v1",
        "rfc8785-command-excluding-command-digest-v1",
        runtime_command["command_digest"],
        runtime_command,
    ),
    "read_status": (
        "examples/contracts/agent-runtime-status-token-claims.json",
        "urn:agent-platform:agent-runtime-status-operation-descriptor:v1",
        "rfc8785-full-document-v1",
        digest(runtime_status_descriptor),
        runtime_status_descriptor,
    ),
    "read_events": (
        "examples/contracts/agent-runtime-events-token-claims.json",
        "urn:agent-platform:agent-runtime-event-read-operation-descriptor:v1",
        "rfc8785-full-document-v1",
        digest(runtime_event_descriptor),
        runtime_event_descriptor,
    ),
}
runtime_tokens: dict[str, dict[str, Any]] = {}
for index, (operation, (path, contract_id, profile, operation_digest, document)) in enumerate(
    runtime_operations.items(), start=1
):
    runtime_token = copy.deepcopy(runtime_token_base)
    runtime_token.update({
        "jti": f"rit_{index:02d}_01J00000000000000000000000",
        "authority_mode": (
            "safety_control" if operation in {"read_status", "read_events"} else "execution"
        ),
        "operation": operation,
        "operation_contract_id": contract_id,
        "operation_digest_profile": profile,
        "operation_request_digest": operation_digest,
        "runtime_run_id": document["runtime_run_id"],
        "invocation_id": document["invocation_id"],
        "invocation_attempt_id": document["invocation_attempt_id"],
        "fencing_token": document["fencing_token"],
    })
    if runtime_token["authority_mode"] == "safety_control":
        runtime_token.update({"iat": 1784193360, "nbf": 1784193360, "exp": 1784193660})
    runtime_tokens[operation] = runtime_token
    write(path, runtime_token)
system_safety_token = copy.deepcopy(runtime_token_base)
system_safety_token.update({
    "jti": "rit_safety_01J00000000000000000000",
    "iat": 1784193360,
    "nbf": 1784193360,
    "exp": 1784193660,
    "authority_mode": "safety_control",
    "operation": "submit_command",
    "operation_contract_id": "urn:agent-platform:agent-runtime-command:v1",
    "operation_digest_profile": "rfc8785-command-excluding-command-digest-v1",
    "operation_request_digest": system_safety_command["command_digest"],
    "runtime_run_id": system_safety_command["runtime_run_id"],
    "invocation_id": system_safety_command["invocation_id"],
    "invocation_attempt_id": system_safety_command["invocation_attempt_id"],
    "fencing_token": system_safety_command["fencing_token"],
    "system_safety_control_id": system_safety_control["safety_control_id"],
    "system_safety_control_digest": system_safety_control["control_digest"],
})
write(
    "examples/contracts/agent-runtime-system-safety-command-token-claims.json",
    system_safety_token,
)
runtime_token_missing_contract = copy.deepcopy(runtime_tokens["start"])
runtime_token_missing_contract.pop("operation_contract_id")
write(
    "tests/invalid/agent-runtime-token-missing-operation-contract.json",
    runtime_token_missing_contract,
)
runtime_token_contract_replay = copy.deepcopy(runtime_tokens["read_events"])
runtime_token_contract_replay["operation_contract_id"] = (
    "urn:agent-platform:agent-runtime-status-operation-descriptor:v1"
)
write(
    "tests/invalid/agent-runtime-token-operation-contract-replay.json",
    runtime_token_contract_replay,
)
runtime_safety_start = copy.deepcopy(runtime_tokens["start"])
runtime_safety_start["authority_mode"] = "safety_control"
write(
    "tests/invalid/agent-runtime-safety-token-authorizes-start.json",
    runtime_safety_start,
)
system_safety_token_missing_digest = copy.deepcopy(system_safety_token)
system_safety_token_missing_digest.pop("system_safety_control_digest")
write(
    "tests/invalid/agent-runtime-system-safety-token-missing-digest.json",
    system_safety_token_missing_digest,
)

mixed_control_authorities = copy.deepcopy(system_safety_command)
mixed_control_authorities["authorized_control_request_id"] = control_request[
    "control_request_id"
]
write(
    "tests/invalid/agent-runtime-command-mixed-control-authorities.json",
    mixed_control_authorities,
)

system_safety_resume = copy.deepcopy(system_safety_command)
system_safety_resume["type"] = "resume"
system_safety_resume["command_digest"] = digest_without(
    system_safety_resume, "command_digest"
)
write(
    "tests/invalid/agent-runtime-system-safety-resume.json",
    system_safety_resume,
)

invalid_system_safety_action = copy.deepcopy(system_safety_control)
invalid_system_safety_action["action"] = "resume"
invalid_system_safety_action["control_digest"] = digest_without(
    invalid_system_safety_action, "control_digest"
)
write(
    "tests/invalid/system-safety-control-resume.json",
    invalid_system_safety_action,
)
hard_revocation_pause = copy.deepcopy(system_safety_control)
hard_revocation_pause["action"] = "pause"
hard_revocation_pause["control_digest"] = digest_without(
    hard_revocation_pause, "control_digest"
)
write(
    "tests/invalid/system-safety-control-hard-revocation-pause.json",
    hard_revocation_pause,
)

sandbox_resolution = next(
    item for item in manifest["capability_resolutions"]
    if item["resolution_id"] == sandbox_spec["provider_resolution_id"]
)
sandbox_contracts = {
    "create": "urn:agent-platform:sandbox-create-request:v1",
    "restore": "urn:agent-platform:sandbox-restore-request:v1",
    "set_desired_state": "urn:agent-platform:sandbox-desired-state-request:v1",
    "extend_lease": "urn:agent-platform:sandbox-lease-request:v1",
    "exec": "urn:agent-platform:sandbox-exec-request:v1",
    "cancel_exec": "urn:agent-platform:sandbox-cancel-exec-request:v1",
    "open_runtime_session": "urn:agent-platform:sandbox-runtime-session-open-request:v1",
    "snapshot": "urn:agent-platform:sandbox-snapshot-request:v1",
    "terminate": "urn:agent-platform:sandbox-terminate-request:v1",
    "read_sandbox": "urn:agent-platform:sandbox-status-operation-descriptor:v1",
    "read_operation": "urn:agent-platform:sandbox-operation-read-operation-descriptor:v1",
    "read_result": "urn:agent-platform:sandbox-exec-result-operation-descriptor:v1",
    "read_snapshot_manifest": "urn:agent-platform:sandbox-snapshot-manifest-operation-descriptor:v1",
    "read_events": "urn:agent-platform:sandbox-event-read-operation-descriptor:v1",
}
sandbox_read_descriptors = {
    "read_sandbox": (
        "examples/contracts/sandbox-status-operation-descriptor.json",
        {
            "operation": "read_sandbox",
            "sandbox_id": sandbox_spec["sandbox_id"],
            "operation_id": sandbox_create["operation_id"],
            "attempt_id": sandbox_create["attempt_id"],
            "fencing_token": sandbox_create["fencing_token"],
        },
        sandbox_create["deadline_at"],
    ),
    "read_operation": (
        "examples/contracts/sandbox-operation-read-operation-descriptor.json",
        {
            "operation": "read_operation",
            "sandbox_id": sandbox_spec["sandbox_id"],
            "operation_id": sandbox_requests["exec"][1]["operation_id"],
            "attempt_id": sandbox_requests["exec"][1]["attempt_id"],
            "fencing_token": sandbox_requests["exec"][1]["fencing_token"],
        },
        sandbox_requests["exec"][1]["deadline_at"],
    ),
    "read_result": (
        "examples/contracts/sandbox-exec-result-operation-descriptor.json",
        {
            "operation": "read_result",
            "sandbox_id": sandbox_spec["sandbox_id"],
            "operation_id": sandbox_requests["exec"][1]["operation_id"],
            "attempt_id": sandbox_requests["exec"][1]["attempt_id"],
            "fencing_token": sandbox_requests["exec"][1]["fencing_token"],
        },
        sandbox_requests["exec"][1]["deadline_at"],
    ),
    "read_snapshot_manifest": (
        "examples/contracts/sandbox-snapshot-manifest-operation-descriptor.json",
        {
            "operation": "read_snapshot_manifest",
            "sandbox_id": sandbox_spec["sandbox_id"],
            "operation_id": sandbox_requests["snapshot"][1]["operation_id"],
            "attempt_id": sandbox_requests["snapshot"][1]["attempt_id"],
            "fencing_token": sandbox_requests["snapshot"][1]["fencing_token"],
        },
        sandbox_requests["snapshot"][1]["deadline_at"],
    ),
    "read_events": (
        "examples/contracts/sandbox-event-read-operation-descriptor.json",
        {
            "operation": "read_events",
            "sandbox_id": sandbox_spec["sandbox_id"],
            "operation_id": sandbox_requests["exec"][1]["operation_id"],
            "attempt_id": sandbox_requests["exec"][1]["attempt_id"],
            "fencing_token": sandbox_requests["exec"][1]["fencing_token"],
            "after_sequence": 0,
        },
        sandbox_requests["exec"][1]["deadline_at"],
    ),
}
for descriptor_path, descriptor, _deadline in sandbox_read_descriptors.values():
    write(descriptor_path, descriptor)

sandbox_token_paths = {
    "create": "examples/contracts/sandbox-operation-token-claims.json",
    "restore": "examples/contracts/sandbox-restore-operation-token-claims.json",
    "set_desired_state": "examples/contracts/sandbox-desired-state-operation-token-claims.json",
    "extend_lease": "examples/contracts/sandbox-lease-operation-token-claims.json",
    "exec": "examples/contracts/sandbox-exec-operation-token-claims.json",
    "cancel_exec": "examples/contracts/sandbox-cancel-exec-operation-token-claims.json",
    "open_runtime_session": "examples/contracts/sandbox-runtime-session-operation-token-claims.json",
    "snapshot": "examples/contracts/sandbox-snapshot-operation-token-claims.json",
    "terminate": "examples/contracts/sandbox-terminate-operation-token-claims.json",
    "read_sandbox": "examples/contracts/sandbox-status-operation-token-claims.json",
    "read_operation": "examples/contracts/sandbox-operation-read-token-claims.json",
    "read_result": "examples/contracts/sandbox-exec-result-operation-token-claims.json",
    "read_snapshot_manifest": "examples/contracts/sandbox-snapshot-manifest-operation-token-claims.json",
    "read_events": "examples/contracts/sandbox-event-read-operation-token-claims.json",
}
sandbox_operation_documents: dict[str, tuple[dict[str, Any], str, str]] = {}
for operation, (_path, request, sandbox_id) in sandbox_requests.items():
    sandbox_operation_documents[operation] = (request, sandbox_id, request["deadline_at"])
for operation, (_path, descriptor, deadline_at) in sandbox_read_descriptors.items():
    sandbox_operation_documents[operation] = (descriptor, descriptor["sandbox_id"], deadline_at)

for index, operation in enumerate(sandbox_token_paths, start=1):
    operation_document, sandbox_id, deadline_at = sandbox_operation_documents[operation]
    is_mutation = operation in sandbox_requests
    request_digest = (
        operation_document["request_digest"] if is_mutation else digest(operation_document)
    )
    sandbox_token = {
        "jti": f"sot_{index:02d}_01J00000000000000000000000",
        "iss": "agent-platform",
        "sub": "spn_agent_sandbox_controller",
        "aud": sandbox_resolution["selected_provider_audience"],
        "iat": 1784192460,
        "nbf": 1784192460,
        "exp": 1784192700,
        "operation": operation,
        "provider_revision_id": sandbox_resolution["selected_provider_revision"]["provider_revision_id"],
        "sandbox_id": sandbox_id,
        "operation_id": operation_document["operation_id"],
        "attempt_id": operation_document["attempt_id"],
        "fencing_token": operation_document["fencing_token"],
        "tenant_id": sandbox_spec["tenant_id"],
        "work_order_id": sandbox_spec["work_order_id"],
        "policy_digest": manifest["policy_decision"]["decision_digest"],
        "request_contract_id": sandbox_contracts[operation],
        "request_digest_profile": (
            "rfc8785-request-excluding-request-digest-v1"
            if is_mutation else "rfc8785-full-document-v1"
        ),
        "request_digest": request_digest,
        "deadline_at": deadline_at,
    }
    write(sandbox_token_paths[operation], sandbox_token)

capability_request = read("examples/contracts/capability-invocation-request.json")
capability_resolution = next(
    item for item in manifest["capability_resolutions"]
    if item["capability"]["id"] == capability_request["capability"]["id"]
)
capability_policy = copy.deepcopy(policy)
capability_policy["decision_id"] = "pol_cap_01J000000000000000000000"
capability_policy["decision_point"] = "invocation"
capability_policy["decision_digest"] = digest_without(capability_policy, "decision_digest")
capability_request.update({
    "tenant_id": manifest["tenant_id"],
    "client_app_id": grant["client_app_id"],
    "principal_context_digest": grant["principal_context_digest"],
    "execution_scope": {"kind": "work_order", "work_order_id": manifest["work_order_id"]},
    "execution_owner_request_digest": manifest["request_binding"]["request_digest"],
    "provider_resolution_id": capability_resolution["resolution_id"],
    "provider_instance_id": capability_resolution["selected_provider_instance_id"],
    "provider_revision_id": capability_resolution["selected_provider_revision"]["provider_revision_id"],
    "deadline_at": "2026-07-16T09:20:00Z",
    "commercial_authorization": copy.deepcopy(commercial_binding),
    "execution_budget": copy.deepcopy(budget),
    "policy_decision": capability_policy,
    "effective_permissions": copy.deepcopy(permissions),
})
capability_request.pop("work_order_id", None)
for legacy_field in (
    "output_staging_session_id", "policy_decision_digest",
    "execution_budget_digest", "permissions_digest",
):
    capability_request.pop(legacy_field, None)
capability_artifact_grant = copy.deepcopy(artifact_grant)
capability_artifact_grant["grant_id"] = "artg_cap_01J0000000000000000000"
capability_artifact_grant["execution_scope"] = copy.deepcopy(capability_request["execution_scope"])
capability_artifact_grant.pop("runtime_run_id", None)
capability_artifact_grant["invocation_id"] = capability_request["invocation_id"]
capability_artifact_grant["invocation_attempt_id"] = capability_request["invocation_attempt_id"]
capability_artifact_grant["expires_at"] = capability_request["deadline_at"]
capability_artifact_grant["grant_digest"] = digest_without(
    capability_artifact_grant, "grant_digest"
)
capability_request["input_artifact_grants"] = [capability_artifact_grant]
staging_grant = {
    "staging_grant_id": "stgg_01J0000000000000000000000",
    "tenant_id": capability_request["tenant_id"],
    "execution_scope": copy.deepcopy(capability_request["execution_scope"]),
    "invocation_id": capability_request["invocation_id"],
    "invocation_attempt_id": capability_request["invocation_attempt_id"],
    "staging_session_id": "stg_01J00000000000000000000000",
    "gateway_binding": copy.deepcopy(gateway_bindings["artifact"]["port"]),
    "allowed_media_types": ["text/html"],
    "max_object_count": 20,
    "max_object_bytes": 4194304,
    "max_total_bytes": 8388608,
    "issued_at": "2026-07-16T09:01:00Z",
    "expires_at": capability_request["deadline_at"],
    "grant_digest": "sha256:" + "0" * 64,
}
staging_grant["grant_digest"] = digest_without(staging_grant, "grant_digest")
capability_request["output_staging_grant"] = staging_grant
write("examples/contracts/artifact-staging-grant.json", staging_grant)
capability_request["request_digest"] = digest_without(capability_request, "request_digest")
write("examples/contracts/capability-invocation-request.json", capability_request)

capability_result = read("examples/contracts/capability-invocation-result.json")
capability_result["usage"] = [copy.deepcopy(usage_observation)]
capability_result["invocation_request_digest"] = capability_request["request_digest"]
write("examples/contracts/capability-invocation-result.json", capability_result)

capability_token = {
    "jti": "cit_01J00000000000000000000000",
    "iss": "agent-platform",
    "sub": "spn_agent_capability_dispatcher",
    "aud": capability_resolution["selected_provider_audience"],
    "iat": 1784192470,
    "nbf": 1784192470,
    "exp": 1784192770,
    "authority_mode": "execution",
    "operation": "invoke",
    "authorization_sequence": 1,
    "predecessor_jti": None,
    "renewal_reason": "initial_dispatch",
    "tenant_id": capability_request["tenant_id"],
    "client_app_id": capability_request["client_app_id"],
    "principal_context_digest": capability_request["principal_context_digest"],
    "execution_scope": copy.deepcopy(capability_request["execution_scope"]),
    "provider_resolution_id": capability_request["provider_resolution_id"],
    "provider_instance_id": capability_request["provider_instance_id"],
    "provider_revision_id": capability_request["provider_revision_id"],
    "capability_id": capability_request["capability"]["id"],
    "capability_version": capability_request["capability"]["version"],
    "invocation_id": capability_request["invocation_id"],
    "invocation_attempt_id": capability_request["invocation_attempt_id"],
    "fencing_token": capability_request["fencing_token"],
    "invocation_request_digest": capability_request["request_digest"],
    "operation_contract_id": "urn:agent-platform:capability-invocation-request:v1",
    "operation_digest_profile": "rfc8785-request-excluding-request-digest-v1",
    "operation_request_digest": capability_request["request_digest"],
    "policy_decision_digest": capability_request["policy_decision"]["decision_digest"],
    "execution_budget_digest": capability_request["execution_budget"]["budget_digest"],
    "permissions_digest": permissions["permissions_digest"],
    "staging_grant_digest": staging_grant["grant_digest"],
}
write("examples/contracts/capability-invocation-token-claims.json", capability_token)
capability_safety_invoke = copy.deepcopy(capability_token)
capability_safety_invoke["authority_mode"] = "safety_control"
write(
    "tests/invalid/capability-safety-token-authorizes-invoke.json",
    capability_safety_invoke,
)

capability_cancel = read("examples/contracts/capability-cancellation-request.json")
capability_cancel["invocation_id"] = capability_request["invocation_id"]
capability_cancel["invocation_attempt_id"] = capability_request["invocation_attempt_id"]
capability_cancel["fencing_token"] = capability_request["fencing_token"]
capability_cancel["request_digest"] = digest_without(capability_cancel, "request_digest")
write("examples/contracts/capability-cancellation-request.json", capability_cancel)

status_operation = {
    "operation": "status",
    "invocation_id": capability_request["invocation_id"],
    "invocation_attempt_id": capability_request["invocation_attempt_id"],
    "fencing_token": capability_request["fencing_token"],
    "provider_operation_id": "provider-op-html-0001",
}
write("examples/contracts/capability-status-operation-descriptor.json", status_operation)
capability_status_token = copy.deepcopy(capability_token)
capability_status_token.update({
    "jti": "cit_01J00000000000000000000001",
    "iat": 1784193660,
    "nbf": 1784193660,
    "exp": 1784193960,
    "authority_mode": "safety_control",
    "operation": "status",
    "authorization_sequence": 2,
    "predecessor_jti": capability_token["jti"],
    "renewal_reason": "status_query",
    "provider_operation_id": status_operation["provider_operation_id"],
    "operation_contract_id": "urn:agent-platform:capability-status-operation-descriptor:v1",
    "operation_digest_profile": "rfc8785-full-document-v1",
    "operation_request_digest": digest(status_operation),
})
write("examples/contracts/capability-invocation-status-token-claims.json", capability_status_token)

capability_cancel_token = copy.deepcopy(capability_status_token)
capability_cancel_token.update({
    "jti": "cit_01J00000000000000000000002",
    "iat": 1784193720,
    "nbf": 1784193720,
    "exp": 1784194020,
    "authority_mode": "safety_control",
    "operation": "cancel",
    "authorization_sequence": 3,
    "predecessor_jti": capability_status_token["jti"],
    "renewal_reason": "cancellation",
    "operation_contract_id": "urn:agent-platform:capability-cancellation-request:v1",
    "operation_digest_profile": "rfc8785-request-excluding-request-digest-v1",
    "operation_request_digest": capability_cancel["request_digest"],
})
write("examples/contracts/capability-cancellation-token-claims.json", capability_cancel_token)

event_read_operation = {
    "operation": "read_events",
    "invocation_id": capability_request["invocation_id"],
    "invocation_attempt_id": capability_request["invocation_attempt_id"],
    "fencing_token": capability_request["fencing_token"],
    "provider_operation_id": status_operation["provider_operation_id"],
    "after_sequence": 0,
    "limit": 1000,
}
write("examples/contracts/capability-event-read-operation-descriptor.json", event_read_operation)
capability_event_token = copy.deepcopy(capability_cancel_token)
capability_event_token.update({
    "jti": "cit_01J00000000000000000000003",
    "iat": 1784193780,
    "nbf": 1784193780,
    "exp": 1784194080,
    "authority_mode": "safety_control",
    "operation": "read_events",
    "authorization_sequence": 4,
    "predecessor_jti": capability_cancel_token["jti"],
    "renewal_reason": "event_resume",
    "operation_contract_id": "urn:agent-platform:capability-event-read-operation-descriptor:v1",
    "operation_digest_profile": "rfc8785-full-document-v1",
    "operation_request_digest": digest(event_read_operation),
})
write("examples/contracts/capability-invocation-events-token-claims.json", capability_event_token)

for relative in (
    "examples/contracts/capability-invocation-accepted.json",
    "examples/contracts/capability-invocation-status.json",
    "examples/contracts/capability-invocation-event.json",
):
    capability_output = read(relative)
    capability_output["invocation_request_digest"] = capability_request["request_digest"]
    write(relative, capability_output)

staging_content = b"<h1>Hello</h1>"
staging_object = {
    "staging_session_id": staging_grant["staging_session_id"],
    "invocation_id": capability_request["invocation_id"],
    "invocation_attempt_id": capability_request["invocation_attempt_id"],
    "fencing_token": capability_request["fencing_token"],
    "object_key": "outputs/index.html",
    "media_type": "text/html",
    "content_encoding": "base64",
    "content_base64": "PGgxPkhlbGxvPC9oMT4=",
    "size_bytes": len(staging_content),
    "digest": bytes_digest(staging_content),
    "request_digest": "sha256:" + "0" * 64,
}
staging_descriptor = copy.deepcopy(staging_object)
staging_descriptor.pop("request_digest")
staging_descriptor.pop("content_base64")
staging_object["request_digest"] = digest(staging_descriptor)
write("examples/contracts/artifact-staging-object-request.json", staging_object)

artifact_stage_token = {
    "jti": "agt_01J00000000000000000000000",
    "iss": "agent-platform",
    "sub": capability_resolution["selected_provider_audience"],
    "aud": staging_grant["gateway_binding"]["audience"],
    "iat": 1784192470,
    "nbf": 1784192470,
    "exp": 1784192770,
    "operation": "stage_object",
    "tenant_id": capability_request["tenant_id"],
    "execution_scope": copy.deepcopy(capability_request["execution_scope"]),
    "invocation_id": capability_request["invocation_id"],
    "invocation_attempt_id": capability_request["invocation_attempt_id"],
    "fencing_token": capability_request["fencing_token"],
    "gateway_binding_digest": staging_grant["gateway_binding"]["binding_digest"],
    "operation_contract_id": "urn:agent-platform:artifact-staging-object-request:v1",
    "operation_digest_profile": "rfc8785-artifact-stage-metadata-excluding-content-and-request-digest-v1",
    "request_digest": staging_object["request_digest"],
    "staging_grant_digest": staging_grant["grant_digest"],
}
write("examples/contracts/artifact-gateway-stage-token-claims.json", artifact_stage_token)

artifact_read_descriptor = {
    "operation": "read_content",
    "tenant_id": capability_request["tenant_id"],
    "execution_scope": copy.deepcopy(capability_request["execution_scope"]),
    "invocation_id": capability_request["invocation_id"],
    "invocation_attempt_id": capability_request["invocation_attempt_id"],
    "fencing_token": capability_request["fencing_token"],
    "artifact_id": capability_artifact_grant["artifact_id"],
    "version_id": capability_artifact_grant["version_id"],
}
write("examples/contracts/artifact-read-operation-descriptor.json", artifact_read_descriptor)
artifact_read_token = {
    "jti": "agt_01J00000000000000000000002",
    "iss": "agent-platform",
    "sub": capability_resolution["selected_provider_audience"],
    "aud": capability_artifact_grant["gateway_binding"]["audience"],
    "iat": 1784193070,
    "nbf": 1784193070,
    "exp": 1784193370,
    "operation": "read_content",
    "tenant_id": capability_request["tenant_id"],
    "execution_scope": copy.deepcopy(capability_request["execution_scope"]),
    "invocation_id": capability_request["invocation_id"],
    "invocation_attempt_id": capability_request["invocation_attempt_id"],
    "fencing_token": capability_request["fencing_token"],
    "gateway_binding_digest": capability_artifact_grant["gateway_binding"]["binding_digest"],
    "operation_contract_id": "urn:agent-platform:artifact-read-operation-descriptor:v1",
    "operation_digest_profile": "rfc8785-full-document-v1",
    "request_digest": digest(artifact_read_descriptor),
    "artifact_grant_digest": capability_artifact_grant["grant_digest"],
}
write("examples/contracts/artifact-gateway-read-token-claims.json", artifact_read_token)

staging_commit = {
    "staging_session_id": staging_grant["staging_session_id"],
    "invocation_id": capability_request["invocation_id"],
    "invocation_attempt_id": capability_request["invocation_attempt_id"],
    "fencing_token": capability_request["fencing_token"],
    "objects": [{
        "object_key": staging_object["object_key"],
        "name": "index.html",
        "media_type": staging_object["media_type"],
        "role": "primary",
        "size_bytes": staging_object["size_bytes"],
        "digest": staging_object["digest"],
    }],
    "request_digest": "sha256:" + "0" * 64,
}
staging_commit["request_digest"] = digest_without(staging_commit, "request_digest")
write("examples/contracts/artifact-staging-commit-request.json", staging_commit)

artifact_commit_token = copy.deepcopy(artifact_stage_token)
artifact_commit_token.update({
    "jti": "agt_01J00000000000000000000001",
    "operation": "commit_staging",
    "operation_contract_id": "urn:agent-platform:artifact-staging-commit-request:v1",
    "operation_digest_profile": "rfc8785-request-excluding-request-digest-v1",
    "request_digest": staging_commit["request_digest"],
})
write("examples/contracts/artifact-gateway-commit-token-claims.json", artifact_commit_token)

# Prove that a standalone ArtifactOperation can use the same Capability and
# Artifact Gateway protocols without inventing a WorkOrder or RunManifest.
artifact_operation_capability_request = copy.deepcopy(capability_request)
artifact_operation_capability_request.update({
    "tenant_id": preview_context["tenant_id"],
    "client_app_id": preview_context["client_app_id"],
    "principal_context_digest": preview_context["principal_context"]["principal_context_digest"],
    "execution_scope": {
        "kind": "artifact_operation",
        "artifact_operation_id": preview_operation["artifact_operation_id"],
    },
    "execution_owner_request_digest": preview_request["operation_context"]["request_digest"],
    "invocation_id": preview_invocation["invocation_id"],
    "invocation_attempt_id": preview_invocation["current_attempt_id"],
    "fencing_token": 1,
    "idempotency_key": "artifact-operation-provider-dispatch-0001",
    "provider_resolution_id": preview_resolution["resolution_id"],
    "provider_instance_id": preview_resolution["selected_provider_instance_id"],
    "provider_revision_id": preview_resolution["selected_provider_revision"]["provider_revision_id"],
    "capability": {
        "id": preview_context["capability"]["id"],
        "version": preview_context["capability"]["version"],
        "profile": preview_context["capability"]["profile"],
        "input_schema_digest": capability_request["capability"]["input_schema_digest"],
        "output_schema_digest": capability_request["capability"]["output_schema_digest"],
    },
    "deadline_at": "2026-07-16T09:20:00Z",
    "input": {
        "artifact_id": preview_context["artifact_id"],
        "source_version_id": preview_context["source_version_id"],
        "source_version_digest": preview_context["source_version_digest"],
        "options": preview_request["options"],
    },
    "commercial_authorization": copy.deepcopy(preview_context["commercial_authorization"]),
    "execution_budget": copy.deepcopy(preview_budget),
    "policy_decision": copy.deepcopy(preview_policy),
    "effective_permissions": copy.deepcopy(preview_permissions),
})
artifact_operation_input_grant = copy.deepcopy(capability_artifact_grant)
artifact_operation_input_grant.update({
    "grant_id": "artg_aop_01J0000000000000000000",
    "execution_scope": copy.deepcopy(artifact_operation_capability_request["execution_scope"]),
    "invocation_id": artifact_operation_capability_request["invocation_id"],
    "invocation_attempt_id": artifact_operation_capability_request["invocation_attempt_id"],
    "artifact_id": preview_context["artifact_id"],
    "version_id": preview_context["source_version_id"],
    "artifact_digest": preview_context["source_version_digest"],
    "permissions": ["read"],
    "gateway_binding": copy.deepcopy(gateway_bindings["artifact"]["port"]),
    "issued_at": "2026-07-16T09:06:01Z",
    "expires_at": artifact_operation_capability_request["deadline_at"],
})
artifact_operation_input_grant.pop("runtime_run_id", None)
artifact_operation_input_grant["grant_digest"] = digest_without(
    artifact_operation_input_grant, "grant_digest"
)
artifact_operation_staging_grant = copy.deepcopy(staging_grant)
artifact_operation_staging_grant.update({
    "staging_grant_id": "stgg_aop_01J0000000000000000000",
    "execution_scope": copy.deepcopy(artifact_operation_capability_request["execution_scope"]),
    "invocation_id": artifact_operation_capability_request["invocation_id"],
    "invocation_attempt_id": artifact_operation_capability_request["invocation_attempt_id"],
    "staging_session_id": "stg_aop_01J00000000000000000000",
    "gateway_binding": copy.deepcopy(gateway_bindings["artifact"]["port"]),
    "allowed_media_types": ["text/html"],
    "issued_at": "2026-07-16T09:06:01Z",
    "expires_at": artifact_operation_capability_request["deadline_at"],
})
artifact_operation_staging_grant["grant_digest"] = digest_without(
    artifact_operation_staging_grant, "grant_digest"
)
artifact_operation_capability_request["input_artifact_grants"] = [artifact_operation_input_grant]
artifact_operation_capability_request["output_staging_grant"] = artifact_operation_staging_grant

artifact_operation_secret_intent = copy.deepcopy(artifact_operation_capability_request)
for field in ("request_digest", "secret_reference_ids", "secret_grant_id", "secret_grant_digest"):
    artifact_operation_secret_intent.pop(field, None)
artifact_operation_secret_target_digest = digest(artifact_operation_secret_intent)
artifact_operation_secret_grant = {
    "secret_grant_id": "secg_aop_01J000000000000000000000",
    "secret_grant_digest": "sha256:" + "0" * 64,
    "tenant_id": artifact_operation_capability_request["tenant_id"],
    "principal_context_digest": artifact_operation_capability_request["principal_context_digest"],
    "execution_scope": copy.deepcopy(artifact_operation_capability_request["execution_scope"]),
    "provider_instance_id": artifact_operation_capability_request["provider_instance_id"],
    "provider_revision_id": artifact_operation_capability_request["provider_revision_id"],
    "provider_audience": preview_resolution["selected_provider_audience"],
    "workload_identity": "spiffe://agent-platform/provider/rpi_html_preview/workload/invoke",
    "secret_reference_ids": ["secret-ref-artifact-preview-api-01"],
    "purpose": "http_header",
    "target": {
        "target_kind": "capability_invocation",
        "target_id": artifact_operation_capability_request["invocation_id"],
        "target_digest": artifact_operation_secret_target_digest,
    },
    "operation": "credential_access",
    "target_request_contract_id": "urn:agent-platform:capability-invocation-request:v1",
    "target_request_digest_profile": "rfc8785-capability-intent-excluding-secret-grant-and-request-digest-v1",
    "target_request_digest": artifact_operation_secret_target_digest,
    "sender_constraint": {
        "method": "mtls_spiffe",
        "subject": "spiffe://agent-platform/provider/rpi_html_preview/workload/invoke",
    },
    "issued_at": "2026-07-16T09:06:02Z",
    "expires_at": "2026-07-16T09:11:02Z",
    "max_uses": 1,
    "persistence_policy": {
        "provider_cache_allowed": False,
        "provider_persistence_allowed": False,
        "platform_event_material_allowed": False,
        "temporal_history_material_allowed": False,
    },
}
artifact_operation_secret_grant["secret_grant_digest"] = digest_without(
    artifact_operation_secret_grant, "secret_grant_digest"
)
artifact_operation_capability_request["secret_reference_ids"] = copy.deepcopy(
    artifact_operation_secret_grant["secret_reference_ids"]
)
artifact_operation_capability_request["secret_grant_id"] = artifact_operation_secret_grant["secret_grant_id"]
artifact_operation_capability_request["secret_grant_digest"] = artifact_operation_secret_grant["secret_grant_digest"]
artifact_operation_capability_request["request_digest"] = digest_without(
    artifact_operation_capability_request, "request_digest"
)
preview_invocation["request_digest"] = artifact_operation_capability_request["request_digest"]
preview_operation["invocation_request_digest"] = artifact_operation_capability_request["request_digest"]
write("examples/contracts/artifact-operation-capability-invocation-request.json", artifact_operation_capability_request)
write("examples/contracts/artifact-operation-input-artifact-grant.json", artifact_operation_input_grant)
write("examples/contracts/artifact-operation-staging-grant.json", artifact_operation_staging_grant)

artifact_operation_credential_request = {
    "credential_request_id": "creq_aop_01J000000000000000000000",
    "secret_grant_id": artifact_operation_secret_grant["secret_grant_id"],
    "secret_grant_digest": artifact_operation_secret_grant["secret_grant_digest"],
    "secret_reference_ids": copy.deepcopy(artifact_operation_secret_grant["secret_reference_ids"]),
    "target": copy.deepcopy(artifact_operation_secret_grant["target"]),
    "purpose": artifact_operation_secret_grant["purpose"],
    "request_digest": "sha256:" + "0" * 64,
}
artifact_operation_credential_request["request_digest"] = digest_without(
    artifact_operation_credential_request, "request_digest"
)
artifact_operation_credential_token = {
    "iss": "agent-platform",
    "sub": artifact_operation_secret_grant["workload_identity"],
    "aud": "urn:agent-platform:credential-gateway:primary",
    "jti": "cot_aop_01J000000000000000000000",
    "iat": 1784192762,
    "nbf": 1784192762,
    "exp": 1784193062,
    "tenant_id": artifact_operation_secret_grant["tenant_id"],
    "secret_grant_id": artifact_operation_secret_grant["secret_grant_id"],
    "secret_grant_digest": artifact_operation_secret_grant["secret_grant_digest"],
    "operation": "credential_access",
    "request_contract_id": "urn:agent-platform:credential-access-request:v1",
    "request_digest_profile": "rfc8785-request-excluding-request-digest-v1",
    "request_digest": artifact_operation_credential_request["request_digest"],
}
artifact_operation_credential_delivery = {
    "credential_request_id": artifact_operation_credential_request["credential_request_id"],
    "delivery_handle": "opaque-artifact-operation-workload-bound-handle-000000000001",
    "delivery_mode": artifact_operation_secret_grant["purpose"],
    "expires_at": artifact_operation_secret_grant["expires_at"],
    "audit_event_id": "evt_credential_access_aop_01J000000000",
}
for path, value in (
    ("examples/contracts/artifact-operation-secret-grant.json", artifact_operation_secret_grant),
    ("examples/contracts/artifact-operation-credential-access-request.json", artifact_operation_credential_request),
    ("examples/contracts/artifact-operation-credential-operation-token-claims.json", artifact_operation_credential_token),
    ("examples/contracts/artifact-operation-credential-delivery.json", artifact_operation_credential_delivery),
):
    write(path, value)
write("tests/semantic-invalid/artifact-operation-credential-mediation-cases.json", {
    "secret_grant": artifact_operation_secret_grant,
    "request": artifact_operation_credential_request,
    "token": artifact_operation_credential_token,
    "delivery": artifact_operation_credential_delivery,
    "target_request": artifact_operation_capability_request,
    "cases": [
        {"id": "artifact-operation-scope-mismatch", "mutation": "execution_scope_mismatch"},
        {"id": "artifact-operation-provider-revision-mismatch", "mutation": "provider_revision_mismatch"},
        {"id": "artifact-operation-target-intent-mismatch", "mutation": "target_request_digest_mismatch"},
    ],
})
artifact_operation_core_event["data"].update({
    "provider_resolution_id": preview_operation["provider_resolution_id"],
    "invocation_id": preview_operation["invocation_id"],
    "request_digest": preview_operation["request_digest"],
    "invocation_request_digest": preview_operation["invocation_request_digest"],
    "terminal_stage": preview_operation["terminal_stage"],
    "terminal_evidence_digest": preview_operation["terminal_evidence_digest"],
})
artifact_operation_core_event["aggregate"]["sequence"] = preview_operation["state_version"]
artifact_operation_core_event["source_event_id"] = (
    f"artifact.operation.state.changed/{preview_operation['state_version']}"
)
artifact_operation_core_event["source_cursor"] = str(preview_operation["state_version"])
artifact_operation_core_event["dedupe_key"] = digest({
    "tenant_id": artifact_operation_core_event["tenant_id"],
    "producer_id": artifact_operation_core_event["producer_id"],
    "source_stream_id": artifact_operation_core_event["source_stream_id"],
    "source_event_id": artifact_operation_core_event["source_event_id"],
})
write(
    "examples/contracts/canonical-event-artifact-operation-succeeded.json",
    artifact_operation_core_event,
)
canonical_core_negative = read("tests/semantic-invalid/canonical-core-event-cases.json")
canonical_core_negative["artifact_operation"] = artifact_operation_core_event
write("tests/semantic-invalid/canonical-core-event-cases.json", canonical_core_negative)
platform_core_event(
    "artifact-operation-secret-grant-issued", "secret.grant.state.changed", "secret_grant",
    artifact_operation_secret_grant["secret_grant_id"],
    {
        "secret_grant_id": artifact_operation_secret_grant["secret_grant_id"],
        "secret_grant_digest": artifact_operation_secret_grant["secret_grant_digest"],
        "state": "issued",
        "evidence_digest": digest({
            "secret_grant_issued": artifact_operation_secret_grant["secret_grant_id"],
        }),
    },
    execution_scope=artifact_operation_secret_grant["execution_scope"],
)

artifact_operation_capability_token = copy.deepcopy(capability_token)
artifact_operation_capability_token.update({
    "jti": "cit_aop_01J0000000000000000000000",
    "iat": 1784192762,
    "nbf": 1784192762,
    "exp": 1784193062,
    "aud": preview_resolution["selected_provider_audience"],
    "tenant_id": artifact_operation_capability_request["tenant_id"],
    "client_app_id": artifact_operation_capability_request["client_app_id"],
    "principal_context_digest": artifact_operation_capability_request["principal_context_digest"],
    "execution_scope": copy.deepcopy(artifact_operation_capability_request["execution_scope"]),
    "provider_resolution_id": artifact_operation_capability_request["provider_resolution_id"],
    "provider_instance_id": artifact_operation_capability_request["provider_instance_id"],
    "provider_revision_id": artifact_operation_capability_request["provider_revision_id"],
    "capability_id": artifact_operation_capability_request["capability"]["id"],
    "capability_version": artifact_operation_capability_request["capability"]["version"],
    "invocation_id": artifact_operation_capability_request["invocation_id"],
    "invocation_attempt_id": artifact_operation_capability_request["invocation_attempt_id"],
    "fencing_token": artifact_operation_capability_request["fencing_token"],
    "invocation_request_digest": artifact_operation_capability_request["request_digest"],
    "operation_request_digest": artifact_operation_capability_request["request_digest"],
    "policy_decision_digest": preview_policy["decision_digest"],
    "execution_budget_digest": preview_budget["budget_digest"],
    "permissions_digest": preview_permissions["permissions_digest"],
    "staging_grant_digest": artifact_operation_staging_grant["grant_digest"],
})
write("examples/contracts/artifact-operation-capability-invocation-token-claims.json", artifact_operation_capability_token)

artifact_operation_staging_object = copy.deepcopy(staging_object)
artifact_operation_staging_object.update({
    "staging_session_id": artifact_operation_staging_grant["staging_session_id"],
    "invocation_id": artifact_operation_capability_request["invocation_id"],
    "invocation_attempt_id": artifact_operation_capability_request["invocation_attempt_id"],
    "fencing_token": artifact_operation_capability_request["fencing_token"],
})
artifact_operation_stage_descriptor = copy.deepcopy(artifact_operation_staging_object)
artifact_operation_stage_descriptor.pop("request_digest", None)
artifact_operation_stage_descriptor.pop("content_base64", None)
artifact_operation_staging_object["request_digest"] = digest(artifact_operation_stage_descriptor)
artifact_operation_stage_token = copy.deepcopy(artifact_stage_token)
artifact_operation_stage_token.update({
    "jti": "agt_aop_stage_01J000000000000000",
    "iat": 1784192762,
    "nbf": 1784192762,
    "exp": 1784193062,
    "sub": preview_resolution["selected_provider_audience"],
    "aud": artifact_operation_staging_grant["gateway_binding"]["audience"],
    "tenant_id": artifact_operation_capability_request["tenant_id"],
    "execution_scope": copy.deepcopy(artifact_operation_capability_request["execution_scope"]),
    "invocation_id": artifact_operation_capability_request["invocation_id"],
    "invocation_attempt_id": artifact_operation_capability_request["invocation_attempt_id"],
    "fencing_token": artifact_operation_capability_request["fencing_token"],
    "gateway_binding_digest": artifact_operation_staging_grant["gateway_binding"]["binding_digest"],
    "request_digest": artifact_operation_staging_object["request_digest"],
    "staging_grant_digest": artifact_operation_staging_grant["grant_digest"],
})

artifact_operation_read_descriptor = copy.deepcopy(artifact_read_descriptor)
artifact_operation_read_descriptor.update({
    "tenant_id": artifact_operation_capability_request["tenant_id"],
    "execution_scope": copy.deepcopy(artifact_operation_capability_request["execution_scope"]),
    "invocation_id": artifact_operation_capability_request["invocation_id"],
    "invocation_attempt_id": artifact_operation_capability_request["invocation_attempt_id"],
    "fencing_token": artifact_operation_capability_request["fencing_token"],
    "artifact_id": artifact_operation_input_grant["artifact_id"],
    "version_id": artifact_operation_input_grant["version_id"],
})
artifact_operation_read_token = copy.deepcopy(artifact_read_token)
artifact_operation_read_token.update({
    "jti": "agt_aop_read_01J0000000000000000",
    "sub": preview_resolution["selected_provider_audience"],
    "aud": artifact_operation_input_grant["gateway_binding"]["audience"],
    "tenant_id": artifact_operation_capability_request["tenant_id"],
    "execution_scope": copy.deepcopy(artifact_operation_capability_request["execution_scope"]),
    "invocation_id": artifact_operation_capability_request["invocation_id"],
    "invocation_attempt_id": artifact_operation_capability_request["invocation_attempt_id"],
    "fencing_token": artifact_operation_capability_request["fencing_token"],
    "gateway_binding_digest": artifact_operation_input_grant["gateway_binding"]["binding_digest"],
    "request_digest": digest(artifact_operation_read_descriptor),
    "artifact_grant_digest": artifact_operation_input_grant["grant_digest"],
})

artifact_operation_staging_commit = copy.deepcopy(staging_commit)
artifact_operation_staging_commit.update({
    "staging_session_id": artifact_operation_staging_grant["staging_session_id"],
    "invocation_id": artifact_operation_capability_request["invocation_id"],
    "invocation_attempt_id": artifact_operation_capability_request["invocation_attempt_id"],
    "fencing_token": artifact_operation_capability_request["fencing_token"],
})
artifact_operation_staging_commit["request_digest"] = digest_without(
    artifact_operation_staging_commit, "request_digest"
)
artifact_operation_commit_token = copy.deepcopy(artifact_operation_stage_token)
artifact_operation_commit_token.update({
    "jti": "agt_aop_commit_01J000000000000000",
    "operation": "commit_staging",
    "operation_contract_id": "urn:agent-platform:artifact-staging-commit-request:v1",
    "operation_digest_profile": "rfc8785-request-excluding-request-digest-v1",
    "request_digest": artifact_operation_staging_commit["request_digest"],
})
for path, value in (
    ("examples/contracts/artifact-operation-artifact-staging-object-request.json", artifact_operation_staging_object),
    ("examples/contracts/artifact-operation-artifact-gateway-stage-token-claims.json", artifact_operation_stage_token),
    ("examples/contracts/artifact-operation-artifact-read-operation-descriptor.json", artifact_operation_read_descriptor),
    ("examples/contracts/artifact-operation-artifact-gateway-read-token-claims.json", artifact_operation_read_token),
    ("examples/contracts/artifact-operation-artifact-staging-commit-request.json", artifact_operation_staging_commit),
    ("examples/contracts/artifact-operation-artifact-gateway-commit-token-claims.json", artifact_operation_commit_token),
):
    write(path, value)

write("examples/contracts/artifact-operation-invocation.json", preview_invocation)
write("examples/contracts/artifact-operation.json", preview_operation)
for cancellation_operation in (
    artifact_operation_cancel_requested,
    artifact_operation_cancellation_reconciling,
    artifact_operation_cancel_missing_source,
):
    cancellation_operation["invocation_request_digest"] = preview_invocation["request_digest"]
for cancellation_invocation in (
    artifact_operation_cancel_invocation,
    artifact_operation_cancellation_reconciling_invocation,
):
    cancellation_invocation["request_digest"] = preview_invocation["request_digest"]
for path, value in (
    ("examples/contracts/artifact-operation-cancel-requested.json", artifact_operation_cancel_requested),
    ("examples/contracts/artifact-operation-cancellation-reconciling.json", artifact_operation_cancellation_reconciling),
    ("examples/contracts/artifact-operation-cancel-requested-invocation.json", artifact_operation_cancel_invocation),
    ("examples/contracts/artifact-operation-cancellation-reconciling-invocation.json", artifact_operation_cancellation_reconciling_invocation),
    ("tests/invalid/artifact-operation-cancel-requested-missing-source.json", artifact_operation_cancel_missing_source),
):
    write(path, value)
artifact_operation_cancel_event["data"]["invocation_request_digest"] = (
    preview_invocation["request_digest"]
)
write(
    "examples/contracts/canonical-event-artifact-operation-cancel-requested.json",
    artifact_operation_cancel_event,
)
artifact_operation_cancellation_cases = read(
    "tests/semantic-invalid/artifact-operation-cancellation-cases.json"
)
artifact_operation_cancellation_cases.update({
    "cancel_requested_operation": copy.deepcopy(artifact_operation_cancel_requested),
    "cancel_requested_invocation": copy.deepcopy(artifact_operation_cancel_invocation),
    "cancellation_reconciling_operation": copy.deepcopy(
        artifact_operation_cancellation_reconciling
    ),
    "cancellation_reconciling_invocation": copy.deepcopy(
        artifact_operation_cancellation_reconciling_invocation
    ),
})
write(
    "tests/semantic-invalid/artifact-operation-cancellation-cases.json",
    artifact_operation_cancellation_cases,
)
write("examples/contracts/preview-session.json", {
    "preview_session_id": "prv_01J00000000000000000000000",
    "artifact_operation": preview_operation,
    "status": "ready",
    "preview_url": "https://preview.agent-platform.test/session/prv_01",
    "expires_at": "2026-07-16T09:16:05Z",
})


def build_secondary_artifact_dispatch(
    operation_kind: str,
    client_request: dict[str, Any],
    operation_budget: dict[str, Any],
    operation_policy: dict[str, Any],
    operation_permissions: dict[str, Any],
    operation_resolution: dict[str, Any],
    invocation: dict[str, Any],
    operation: dict[str, Any],
) -> dict[str, Any]:
    context = client_request["operation_context"]
    provider_request = copy.deepcopy(artifact_operation_capability_request)
    provider_request.update({
        "execution_scope": {
            "kind": "artifact_operation",
            "artifact_operation_id": operation["artifact_operation_id"],
        },
        "execution_owner_request_digest": context["request_digest"],
        "invocation_id": invocation["invocation_id"],
        "invocation_attempt_id": invocation["current_attempt_id"],
        "idempotency_key": f"artifact-{operation_kind}-provider-dispatch-0001",
        "provider_resolution_id": operation_resolution["resolution_id"],
        "provider_instance_id": operation_resolution["selected_provider_instance_id"],
        "provider_revision_id": operation_resolution["selected_provider_revision"]["provider_revision_id"],
        "capability": {
            "id": context["capability"]["id"],
            "version": context["capability"]["version"],
            "profile": context["capability"]["profile"],
            "input_schema_digest": capability_request["capability"]["input_schema_digest"],
            "output_schema_digest": capability_request["capability"]["output_schema_digest"],
        },
        "input": {
            "artifact_id": context["artifact_id"],
            "source_version_id": context["source_version_id"],
            "source_version_digest": context["source_version_digest"],
            "operation_options": {
                key: copy.deepcopy(value)
                for key, value in client_request.items()
                if key != "operation_context"
            },
        },
        "commercial_authorization": copy.deepcopy(context["commercial_authorization"]),
        "execution_budget": copy.deepcopy(operation_budget),
        "policy_decision": copy.deepcopy(operation_policy),
        "effective_permissions": copy.deepcopy(operation_permissions),
    })
    input_grant = copy.deepcopy(artifact_operation_input_grant)
    input_grant.update({
        "grant_id": f"artg_{operation_kind}_01J00000000000000000",
        "execution_scope": copy.deepcopy(provider_request["execution_scope"]),
        "invocation_id": provider_request["invocation_id"],
        "invocation_attempt_id": provider_request["invocation_attempt_id"],
        "artifact_id": context["artifact_id"],
        "version_id": context["source_version_id"],
        "artifact_digest": context["source_version_digest"],
        "gateway_binding": copy.deepcopy(gateway_bindings["artifact"]["port"]),
    })
    input_grant["grant_digest"] = digest_without(input_grant, "grant_digest")
    output_grant = copy.deepcopy(artifact_operation_staging_grant)
    output_grant.update({
        "staging_grant_id": f"stgg_{operation_kind}_01J0000000000000000",
        "execution_scope": copy.deepcopy(provider_request["execution_scope"]),
        "invocation_id": provider_request["invocation_id"],
        "invocation_attempt_id": provider_request["invocation_attempt_id"],
        "staging_session_id": f"stg_{operation_kind}_01J00000000000000000",
        "gateway_binding": copy.deepcopy(gateway_bindings["artifact"]["port"]),
    })
    output_grant["grant_digest"] = digest_without(output_grant, "grant_digest")
    provider_request["input_artifact_grants"] = [input_grant]
    provider_request["output_staging_grant"] = output_grant
    provider_request["request_digest"] = digest_without(provider_request, "request_digest")
    invocation["request_digest"] = provider_request["request_digest"]
    operation["invocation_request_digest"] = provider_request["request_digest"]
    write(
        f"examples/contracts/{operation_kind}-artifact-operation-capability-invocation-request.json",
        provider_request,
    )
    write(
        f"examples/contracts/{operation_kind}-artifact-operation-invocation.json",
        invocation,
    )
    write(
        f"examples/contracts/{operation_kind}-artifact-operation-provider-resolution.json",
        operation_resolution,
    )
    return provider_request


edit_budget, edit_policy, edit_permissions, edit_resolution = (
    artifact_operation_materials["edit"][1], artifact_operation_materials["edit"][2],
    artifact_operation_materials["edit"][3], artifact_operation_materials["edit"][4],
)
edit_provider_request = build_secondary_artifact_dispatch(
    "edit", edit_request, edit_budget, edit_policy, edit_permissions, edit_resolution,
    edit_invocation, edit_operation,
)
write("examples/contracts/edit-session.json", {
    "edit_session_id": "edt_01J00000000000000000000000",
    "artifact_operation": edit_operation,
    "status": "active",
    "mode": "source",
    "draft_reference": "artifact-draft://edt_01",
    "created_at": "2026-07-16T09:06:05Z",
    "expires_at": "2026-07-16T09:26:05Z",
    "draft_revision": 0,
})

conversion_budget, conversion_policy, conversion_permissions, conversion_resolution = (
    artifact_operation_materials["conversion"][1], artifact_operation_materials["conversion"][2],
    artifact_operation_materials["conversion"][3], artifact_operation_materials["conversion"][4],
)
conversion_provider_request = build_secondary_artifact_dispatch(
    "conversion", conversion_request, conversion_budget, conversion_policy,
    conversion_permissions, conversion_resolution, conversion_invocation,
    conversion_operation,
)
write("examples/contracts/conversion-job.json", {
    "conversion_job_id": "cnv_01J00000000000000000000000",
    "artifact_operation": conversion_operation,
    "target_media_type": conversion_request["target_media_type"],
    "result_artifact_id": "art_derived_01J0000000000000000000",
    "result_version_id": "ver_derived_01J0000000000000000000",
})

artifact_operation_negative = read(
    "tests/semantic-invalid/artifact-operation-cases.json"
)
artifact_operation_negative.update({
    "operation": copy.deepcopy(preview_operation),
    "request": copy.deepcopy(preview_request),
    "budget": copy.deepcopy(preview_budget),
    "policy": copy.deepcopy(preview_policy),
    "permissions": copy.deepcopy(preview_permissions),
    "resolution": copy.deepcopy(preview_resolution),
    "invocation": copy.deepcopy(preview_invocation),
    "provider_request": copy.deepcopy(artifact_operation_capability_request),
})
write("tests/semantic-invalid/artifact-operation-cases.json", artifact_operation_negative)

artifact_operation_usage_entry = copy.deepcopy(usage_entry)
artifact_operation_usage_entry.update({
    "entry_id": "use_aop_01J000000000000000000000",
    "execution_scope": {
        "kind": "artifact_operation",
        "artifact_operation_id": preview_operation["artifact_operation_id"],
    },
    "invocation_id": preview_invocation["invocation_id"],
    "producer": {
        "type": "provider",
        "id": preview_resolution["selected_provider_instance_id"],
        "provider_revision_id": preview_resolution["selected_provider_revision"]["provider_revision_id"],
        "provider_revision_digest": preview_resolution["selected_provider_revision"]["provider_revision_digest"],
    },
    "provider_operation_id": "provider-op-artifact-preview-001",
    "source_observation_id": "uobs_aop_01J0000000000000000000",
    "idempotency_key": "usage-artifact-preview-0001",
    "evidence_reference": "https://evidence.agent.internal/provider-usage/uobs_aop_01",
    "occurred_at": "2026-07-16T09:06:03Z",
    "recorded_at": "2026-07-16T09:06:06Z",
})
artifact_operation_usage_entry.pop("agent_run_id", None)
artifact_operation_usage_entry.pop("runtime_run_id", None)
artifact_operation_usage_entry.pop("sandbox_operation_id", None)
artifact_operation_usage_entry["evidence_digest"] = digest({
    "evidence_reference": artifact_operation_usage_entry["evidence_reference"]
})
write("examples/contracts/artifact-operation-technical-usage-entry.json", artifact_operation_usage_entry)

artifact_operation_usage_report = copy.deepcopy(usage_report)
artifact_operation_usage_report.update({
    "usage_report_id": "usr_aop_01J000000000000000000000",
    "execution_scope": copy.deepcopy(artifact_operation_usage_entry["execution_scope"]),
    "idempotency_key": "usage-report-artifact-preview-final-0001",
    "entries": [copy.deepcopy(artifact_operation_usage_entry)],
    "created_at": "2026-07-16T09:06:07Z",
})
artifact_operation_usage_report["usage_report_digest"] = digest_without(
    artifact_operation_usage_report, "usage_report_digest"
)
write("examples/contracts/artifact-operation-usage-report.json", artifact_operation_usage_report)

artifact_operation_settlement = copy.deepcopy(settlement)
artifact_operation_settlement.update({
    "settlement_envelope_id": "set_aop_01J000000000000000000000",
    "execution_scope": copy.deepcopy(artifact_operation_usage_entry["execution_scope"]),
    "terminal_status": "succeeded",
    "idempotency_key": "settlement-artifact-preview-0001",
    "usage_report": copy.deepcopy(artifact_operation_usage_report),
    "created_at": "2026-07-16T09:06:08Z",
})
artifact_operation_settlement["settlement_envelope_digest"] = digest_without(
    artifact_operation_settlement, "settlement_envelope_digest"
)
write(
    "examples/contracts/artifact-operation-business-settlement-envelope.json",
    artifact_operation_settlement,
)
write("tests/semantic-invalid/artifact-operation-usage-cases.json", {
    "meter": copy.deepcopy(meter),
    "entry": copy.deepcopy(artifact_operation_usage_entry),
    "report": copy.deepcopy(artifact_operation_usage_report),
    "settlement": copy.deepcopy(artifact_operation_settlement),
    "operation": copy.deepcopy(preview_operation),
    "invocation": copy.deepcopy(preview_invocation),
    "resolution": copy.deepcopy(preview_resolution),
    "cases": [
        {"id": "artifact-usage-wrong-invocation", "mutation": "wrong_invocation"},
        {"id": "artifact-usage-wrong-provider-revision", "mutation": "wrong_provider_revision"},
        {"id": "artifact-report-cross-scope-entry", "mutation": "cross_scope_entry"},
        {"id": "artifact-settlement-cross-scope", "mutation": "settlement_cross_scope"},
    ],
})

egress_destination = {
    "destination_id": "public-docs-origin",
    "destination_revision_id": "edr_01J00000000000000000000000",
    "destination_revision_digest": "sha256:" + "0" * 64,
    "owner": {
        "scope": "client_application",
        "tenant_id": manifest["tenant_id"],
        "client_app_id": capability_request["client_app_id"],
    },
    "destination_class": "public_documentation",
    "origin": {"scheme": "https", "host": "docs.example.com", "port": 443},
    "allowed_methods": ["GET", "HEAD"],
    "allowed_path_prefixes": ["/reference/"],
    "allowed_query_names": [],
    "allowed_request_headers": ["accept"],
    "redirect_policy": {"mode": "deny", "max_redirects": 0},
    "dns_policy": {
        "resolve_on_every_request": True,
        "reject_private_networks": True,
        "pin_connected_ip": True,
        "max_addresses": 8,
    },
    "created_at": "2026-07-16T09:00:00Z",
}
egress_destination["destination_revision_digest"] = digest_without(
    egress_destination, "destination_revision_digest"
)
write("examples/contracts/egress-destination-revision.json", egress_destination)

egress_request = {
    "tenant_id": manifest["tenant_id"],
    "client_app_id": capability_request["client_app_id"],
    "work_order_id": manifest["work_order_id"],
    "runtime_run_id": runtime_start["runtime_run_id"],
    "invocation_id": "inv_egress_01J0000000000000000000",
    "invocation_attempt_id": "iat_egress_01J000000000000000000",
    "fencing_token": 1,
    "destination_id": egress_destination["destination_id"],
    "destination_revision_id": egress_destination["destination_revision_id"],
    "destination_revision_digest": egress_destination["destination_revision_digest"],
    "destination_class": egress_destination["destination_class"],
    "method": "GET",
    "path": "/reference/index.json",
    "headers": [],
    "request_digest": "sha256:" + "0" * 64,
}
egress_request["request_digest"] = digest_without(egress_request, "request_digest")
write("examples/contracts/egress-http-request.json", egress_request)
egress_response = {
    "invocation_id": egress_request["invocation_id"],
    "invocation_attempt_id": egress_request["invocation_attempt_id"],
    "fencing_token": egress_request["fencing_token"],
    "request_digest": egress_request["request_digest"],
    "status_code": 200,
    "headers": [],
    "body": {
        "media_type": "application/json",
        "encoding": "base64",
        "data": "e30=",
        "size_bytes": 2,
        "digest": bytes_digest(b"{}"),
        "truncated": False,
    },
    "observed_at": "2026-07-16T09:02:00Z",
}
write("examples/contracts/egress-http-response.json", egress_response)
egress_token = {
    "jti": "egt_01J00000000000000000000000",
    "iss": "agent-platform",
    "sub": runtime_resolution["selected_provider_audience"],
    "aud": gateway_bindings["egress"]["port"]["audience"],
    "iat": 1784192470,
    "nbf": 1784192470,
    "exp": 1784192770,
    "tenant_id": egress_request["tenant_id"],
    "client_app_id": egress_request["client_app_id"],
    "work_order_id": egress_request["work_order_id"],
    "runtime_run_id": egress_request["runtime_run_id"],
    "invocation_id": egress_request["invocation_id"],
    "invocation_attempt_id": egress_request["invocation_attempt_id"],
    "fencing_token": egress_request["fencing_token"],
    "destination_id": egress_request["destination_id"],
    "destination_revision_id": egress_request["destination_revision_id"],
    "destination_revision_digest": egress_request["destination_revision_digest"],
    "destination_class": egress_request["destination_class"],
    "gateway_binding_digest": gateway_bindings["egress"]["port"]["binding_digest"],
    "operation": "http_exchange",
    "operation_contract_id": "urn:agent-platform:egress-http-request:v1",
    "operation_digest_profile": "rfc8785-request-excluding-request-digest-v1",
    "request_digest": egress_request["request_digest"],
    "runtime_authorization_digest": runtime_authorization["authorization_digest"],
    "policy_decision_digest": runtime_authorization["policy_decision"]["decision_digest"],
    "execution_budget_digest": runtime_authorization["execution_budget"]["budget_digest"],
    "permissions_digest": runtime_authorization["effective_permissions"]["permissions_digest"],
}
write("examples/contracts/egress-invocation-token-claims.json", egress_token)
egress_token_missing_contract = copy.deepcopy(egress_token)
egress_token_missing_contract.pop("operation_contract_id")
write(
    "tests/invalid/egress-token-missing-operation-contract.json",
    egress_token_missing_contract,
)
egress_token_wrong_profile = copy.deepcopy(egress_token)
egress_token_wrong_profile["operation_digest_profile"] = "rfc8785-full-document-v1"
write(
    "tests/invalid/egress-token-wrong-operation-profile.json",
    egress_token_wrong_profile,
)

missing_runtime_input = copy.deepcopy(runtime_start)
missing_runtime_input.pop("input")
write("tests/invalid/runtime-start-missing-executable-input.json", missing_runtime_input)

missing_control_grant = copy.deepcopy(control_request)
missing_control_grant.pop("execution_grant")
write("tests/invalid/work-order-control-missing-grant.json", missing_control_grant)

pause_with_message_cas = copy.deepcopy(control_request)
pause_with_message_cas["action"] = "pause"
pause_with_message_cas.pop("content", None)
write("tests/invalid/work-order-control-pause-with-message-cas.json", pause_with_message_cas)

control_grant_with_turn = copy.deepcopy(control_grant)
control_grant_with_turn["turn_id"] = "turn_forbidden_on_control"
write("tests/invalid/execution-grant-control-with-turn-binding.json", control_grant_with_turn)

artifact_finalize_grant = copy.deepcopy(artifact_grant)
artifact_finalize_grant["permissions"] = ["read", "finalize"]
write("tests/invalid/artifact-grant-provider-finalize.json", artifact_finalize_grant)

authorization_with_first_predecessor = copy.deepcopy(runtime_authorization)
authorization_with_first_predecessor["predecessor_authorization_digest"] = "sha256:" + "f" * 64
write(
    "tests/invalid/runtime-authorization-first-with-predecessor.json",
    authorization_with_first_predecessor,
)

disabled_gateway_with_route = copy.deepcopy(gateway_bindings)
disabled_gateway_with_route["egress"]["mode"] = "disabled"
disabled_gateway_with_route["egress"]["reason"] = "policy_denied"
write("tests/invalid/runtime-gateway-disabled-with-route.json", disabled_gateway_with_route)

missing_capability_digest = copy.deepcopy(capability_token)
missing_capability_digest.pop("invocation_request_digest")
write("tests/invalid/capability-token-missing-request-digest.json", missing_capability_digest)

missing_capability_budget = copy.deepcopy(capability_request)
missing_capability_budget.pop("execution_budget")
write("tests/invalid/capability-request-missing-execution-budget.json", missing_capability_budget)

first_token_for_status = copy.deepcopy(capability_token)
first_token_for_status["operation"] = "status"
first_token_for_status["provider_operation_id"] = "provider-op-html-0001"
write("tests/invalid/capability-token-first-authorizes-status.json", first_token_for_status)

renewed_token_without_predecessor = copy.deepcopy(capability_status_token)
renewed_token_without_predecessor["predecessor_jti"] = None
write("tests/invalid/capability-token-renewed-without-predecessor.json", renewed_token_without_predecessor)

manifest_without_request_binding = copy.deepcopy(manifest)
manifest_without_request_binding.pop("request_binding")
write("tests/invalid/run-manifest-missing-request-binding.json", manifest_without_request_binding)

artifact_read_with_staging_grant = copy.deepcopy(artifact_stage_token)
artifact_read_with_staging_grant["operation"] = "read_content"
write("tests/invalid/artifact-gateway-read-with-staging-grant.json", artifact_read_with_staging_grant)

egress_with_raw_origin = copy.deepcopy(egress_request)
egress_with_raw_origin["origin"] = "https://unregistered.example"
write("tests/invalid/egress-request-with-raw-origin.json", egress_with_raw_origin)

unsafe_workspace_manifest = copy.deepcopy(workspace_manifest)
unsafe_workspace_manifest["entries"][1]["path"] = "../escape.txt"
write("tests/invalid/workspace-manifest-unsafe-path.json", unsafe_workspace_manifest)

open_event_metadata = copy.deepcopy(canonical_event)
open_event_metadata["metadata"]["provider_private"] = "forbidden"
write("tests/invalid/canonical-event-open-metadata.json", open_event_metadata)

gateway_frame = read("examples/contracts/runtime-gateway-frame.json")
gateway_frame.pop("resume_after_sequence", None)
gateway_frame["resume_cursors"] = [
    {"channel": "terminal", "sequence": 41},
    {"channel": "file_delta", "sequence": 7},
]
write("examples/contracts/runtime-gateway-frame.json", gateway_frame)

gateway_control = read("examples/contracts/runtime-gateway-control-frame.json")
control_payload = {
    field: gateway_control[field]
    for field in ("command", "columns", "rows", "text", "key", "url")
    if field in gateway_control
}
gateway_control["control_digest"] = digest(control_payload)
write("examples/contracts/runtime-gateway-control-frame.json", gateway_control)

gateway_control_extra = copy.deepcopy(gateway_control)
gateway_control_extra["text"] = "unexpected for terminal.resize"
write("tests/invalid/runtime-gateway-control-extra-fields.json", gateway_control_extra)

runtime_session_response = read("examples/contracts/runtime-session-response.json")
runtime_session_response["expires_at"] = "2026-07-16T09:20:00Z"
write("examples/contracts/runtime-session-response.json", runtime_session_response)
runtime_session_route = {
    "runtime_session_id": runtime_session_response["runtime_session_id"],
    "tenant_id": manifest["tenant_id"],
    "client_app_id": grant["client_app_id"],
    "principal_id": grant["sub"],
    "work_order_id": manifest["work_order_id"],
    "sandbox_id": manifest["sandboxes"][0]["sandbox_id"],
    "sandbox_slot_key": runtime_session_response["sandbox_slot_key"],
    "runtime_type": runtime_session_response["runtime_type"],
    "gateway_route_id": "rgr_01J00000000000000000000000",
    "provider_route_reference": "prr_AQIDBAUGBwgJCgsMDQ4PEA",
    "provider_route_digest": "sha256:" + "0" * 64,
    "expires_at": runtime_session_response["expires_at"],
    "scopes": ["terminal:connect"],
    "connection_generation": runtime_session_response["connection_generation"],
}
runtime_session_route["provider_route_digest"] = digest({
    field: runtime_session_route[field]
    for field in (
        "runtime_session_id", "sandbox_id", "runtime_type", "provider_route_reference"
    )
})
write("examples/contracts/runtime-session-route.json", runtime_session_route)
runtime_session_route_with_endpoint = copy.deepcopy(runtime_session_route)
runtime_session_route_with_endpoint["runtime_endpoint"] = "https://provider.internal/session"
write(
    "tests/invalid/runtime-session-route-with-raw-endpoint.json",
    runtime_session_route_with_endpoint,
)

port_forward_recording = read("examples/contracts/runtime-session-request.json")
port_forward_recording["runtime_type"] = "port_forward"
write("tests/invalid/runtime-session-port-forward-recording.json", port_forward_recording)

runtime_event = read("examples/contracts/agent-runtime-event.json")
runtime_event_page = read("examples/contracts/agent-runtime-event-page.json")
runtime_event_page["events"] = [runtime_event]
runtime_event_page["next_event_sequence"] = runtime_event["event_sequence"]
write("examples/contracts/agent-runtime-event-page.json", runtime_event_page)
runtime_resolution = next(
    item for item in manifest["capability_resolutions"]
    if item["resolution_id"] == manifest["agent_runtime"]["resolution_id"]
)
canonical_runtime_event = {
    "event_id": "evt_runtime_01J000000000000000000",
    "schema_version": 2,
    "tenant_id": manifest["tenant_id"],
    "producer_kind": "provider",
    "producer_id": "agent-runtime-adapter",
    "provider_revision_id": runtime_resolution["selected_provider_revision"]["provider_revision_id"],
    "source_stream_id": f"agent-runtime/{runtime_event['runtime_run_id']}",
    "source_event_id": runtime_event["event_id"],
    "source_cursor": runtime_event["source_cursor"],
    "dedupe_key": "sha256:" + "0" * 64,
    "event_registry": {
        "registry_id": event_registry["registry_id"],
        "registry_version": event_registry["registry_version"],
        "registry_digest": event_registry["registry_digest"],
    },
    "conversation_id": manifest["conversation"]["conversation_id"],
    "work_order_id": manifest["work_order_id"],
    "turn_id": manifest["conversation"]["turn_id"],
    "branch_id": manifest["conversation"]["branch_id"],
    "input_message_id": manifest["conversation"]["input_message_id"],
    "work_sequence": 153,
    "aggregate": {
        "type": "agent_run",
        "id": manifest["agent_run_id"],
        "sequence": runtime_event["event_sequence"],
    },
    "references": {
        "workflow_run_id": manifest["workflow_run_id"],
        "agent_run_id": manifest["agent_run_id"],
        "message_id": runtime_event["data"]["message_id"],
    },
    "type": runtime_event["type"],
    "occurred_at": runtime_event["occurred_at"],
    "actor": {"type": "provider", "id": "agent-runtime-adapter"},
    "data": runtime_event["data"],
    "metadata": {
        "trace_id": "trace-runtime-001",
        "correlation_id": manifest["work_order_id"],
        "provider_instance_id": runtime_resolution["selected_provider_instance_id"],
    },
    "data_version": runtime_event["data_version"],
    "recorded_at": "2026-07-15T10:10:00.100Z",
}
canonical_runtime_event["dedupe_key"] = digest({
    field: canonical_runtime_event[field]
    for field in ("tenant_id", "producer_id", "source_stream_id", "source_event_id")
})
write("examples/contracts/canonical-runtime-event-v2.json", canonical_runtime_event)

workflow_run = {
    "workflow_run_id": manifest["workflow_run_id"],
    "tenant_id": manifest["tenant_id"],
    "work_order_id": manifest["work_order_id"],
    "workflow": manifest["workflow"],
    "orchestration_binding": manifest["orchestration_binding"],
    "created_at": "2026-07-16T09:01:00Z",
}
write("examples/contracts/workflow-run.json", workflow_run)

root_binding = {
    "binding_id": "wrb_01J00000000000000000000000",
    "tenant_id": manifest["tenant_id"],
    "work_order_id": manifest["work_order_id"],
    "workflow_run_id": manifest["workflow_run_id"],
    "root_agent_run_id": manifest["agent_run_id"],
    "run_manifest_digest": manifest["run_manifest_digest"],
    "bound_at": "2026-07-16T09:01:00Z",
    "binding_digest": "sha256:" + "0" * 64,
}
root_binding["binding_digest"] = digest_without(root_binding, "binding_digest")
write("examples/contracts/workflow-run-root-binding.json", root_binding)

agent_run = {
    "agent_run_id": manifest["agent_run_id"],
    "tenant_id": manifest["tenant_id"],
    "runtime_run_id": runtime_start["runtime_run_id"],
    "workflow_run_id": manifest["workflow_run_id"],
    "work_order_id": manifest["work_order_id"],
    "root_agent_run_id": manifest["agent_run_id"],
    "run_kind": "root",
    "run_depth": 0,
    "required_for_work_order_completion": True,
    "agent_role": "general",
    "runtime_provider_resolution_id": manifest["agent_runtime"]["resolution_id"],
    "run_manifest_digest": manifest["run_manifest_digest"],
    "created_at": "2026-07-16T09:01:00Z",
}
write("examples/contracts/agent-run.json", agent_run)

control_fanout = {
    "fanout_id": "fan_01J00000000000000000000000",
    "fanout_version": 1,
    "previous_fanout_digest": None,
    "fanout_digest": "sha256:" + "0" * 64,
    "tenant_id": manifest["tenant_id"],
    "work_order_id": manifest["work_order_id"],
    "action": "cancel",
    "authority_kind": "work_order_control_request",
    "authority_id": cancel_control_request["control_request_id"],
    "authority_digest": cancel_control_grant["request_digest"],
    "targets": [
        {
            "agent_run_id": agent_run["agent_run_id"],
            "runtime_run_id": agent_run["runtime_run_id"],
            "target_fencing_token": 3,
            "control_state": "pending",
        },
        {
            "agent_run_id": child_agent_run["agent_run_id"],
            "runtime_run_id": child_agent_run["runtime_run_id"],
            "target_fencing_token": 2,
            "control_state": "pending",
        },
    ],
    "created_at": "2026-07-16T09:03:00Z",
    "updated_at": "2026-07-16T09:03:00Z",
}
control_fanout["fanout_digest"] = digest_without(control_fanout, "fanout_digest")
write("examples/contracts/agent-run-control-fanout.json", control_fanout)

progressed_control_fanout = copy.deepcopy(control_fanout)
progressed_control_fanout.update({
    "fanout_version": 2,
    "previous_fanout_digest": control_fanout["fanout_digest"],
    "updated_at": "2026-07-16T09:03:02Z",
})
progressed_control_fanout["targets"][0]["control_state"] = "confirmed"
progressed_control_fanout["targets"][1]["control_state"] = "outcome_unknown"
progressed_control_fanout["fanout_digest"] = digest_without(
    progressed_control_fanout, "fanout_digest"
)
write(
    "examples/contracts/agent-run-control-fanout-progressed.json",
    progressed_control_fanout,
)

invalid_child_input = copy.deepcopy(child_spawn_request)
invalid_child_input["delegated_input"]["child_agent_spawn_request_id"] = "spawn_other"
invalid_child_input["request_digest"] = digest_without(invalid_child_input, "request_digest")
write("tests/semantic-invalid/child-spawn-input-mismatch.json", invalid_child_input)

invalid_child_allocation = copy.deepcopy(child_budget_allocation)
invalid_child_allocation["limits"]["max_model_requests"] = budget["limits"]["max_model_requests"] + 1
invalid_child_allocation["allocation_digest"] = digest_without(
    invalid_child_allocation, "allocation_digest"
)
write("tests/semantic-invalid/child-budget-allocation-wider.json", invalid_child_allocation)

invalid_child_parent = copy.deepcopy(child_agent_run)
invalid_child_parent["parent_agent_run_id"] = "agr_other"
write("tests/semantic-invalid/child-agent-run-parent-mismatch.json", invalid_child_parent)

invalid_rejected_decision = copy.deepcopy(child_admission_decision)
invalid_rejected_decision["outcome"] = "rejected"
invalid_rejected_decision["reason_codes"] = ["policy_denied"]
invalid_rejected_decision["decision_digest"] = digest_without(
    invalid_rejected_decision, "decision_digest"
)
write(
    "tests/invalid/child-agent-run-rejected-with-resources.json",
    invalid_rejected_decision,
)

invalid_accepted_reasons = copy.deepcopy(child_admission_decision)
invalid_accepted_reasons["reason_codes"] = ["admitted", "policy_denied"]
invalid_accepted_reasons["decision_digest"] = digest_without(
    invalid_accepted_reasons, "decision_digest"
)
write(
    "tests/invalid/child-agent-run-accepted-with-rejection-reason.json",
    invalid_accepted_reasons,
)

invalid_rejected_admitted = copy.deepcopy(child_admission_decision)
invalid_rejected_admitted["outcome"] = "rejected"
invalid_rejected_admitted["reason_codes"] = ["admitted"]
for field in (
    "child_agent_run_id", "runtime_run_id", "runtime_provider_resolution_id",
    "run_manifest_digest", "budget_allocation", "workspace_binding",
):
    invalid_rejected_admitted.pop(field, None)
invalid_rejected_admitted["decision_digest"] = digest_without(
    invalid_rejected_admitted, "decision_digest"
)
write(
    "tests/invalid/child-agent-run-rejected-as-admitted.json",
    invalid_rejected_admitted,
)

invalid_child_start_message = copy.deepcopy(child_runtime_start)
invalid_child_start_message["input_message_id"] = manifest["conversation"]["input_message_id"]
invalid_child_start_message["request_digest"] = digest_without(
    invalid_child_start_message, "request_digest"
)
write(
    "tests/invalid/child-runtime-start-with-input-message.json",
    invalid_child_start_message,
)

invalid_child_start_topology = copy.deepcopy(child_runtime_start)
invalid_child_start_topology["run_topology"].pop("spawn_request_id")
invalid_child_start_topology["request_digest"] = digest_without(
    invalid_child_start_topology, "request_digest"
)
write(
    "tests/invalid/child-runtime-start-missing-spawn-binding.json",
    invalid_child_start_topology,
)

invalid_child_admission_provider = copy.deepcopy(child_admission_decision)
invalid_child_admission_provider["runtime_provider_resolution_id"] = "res_other"
invalid_child_admission_provider["decision_digest"] = digest_without(
    invalid_child_admission_provider, "decision_digest"
)
write(
    "tests/semantic-invalid/child-admission-provider-mismatch.json",
    invalid_child_admission_provider,
)

invalid_child_admission_workspace = copy.deepcopy(child_admission_decision)
invalid_child_admission_workspace["workspace_binding"] = copy.deepcopy(
    manifest["workspace_binding"]
)
invalid_child_admission_workspace["decision_digest"] = digest_without(
    invalid_child_admission_workspace, "decision_digest"
)
write(
    "tests/semantic-invalid/child-admission-workspace-mismatch.json",
    invalid_child_admission_workspace,
)

invalid_control_fanout = copy.deepcopy(control_fanout)
invalid_control_fanout["targets"][0].update({
    "system_safety_control_id": "ssc_mixed_authority",
    "system_safety_control_digest": "sha256:" + "f" * 64,
})
invalid_control_fanout["fanout_digest"] = digest_without(
    invalid_control_fanout, "fanout_digest"
)
write(
    "tests/invalid/agent-run-control-fanout-mixed-authority.json",
    invalid_control_fanout,
)

invalid_control_fanout_authority = copy.deepcopy(control_fanout)
invalid_control_fanout_authority["authority_digest"] = control_grant["request_digest"]
invalid_control_fanout_authority["fanout_digest"] = digest_without(
    invalid_control_fanout_authority, "fanout_digest"
)
write(
    "tests/semantic-invalid/agent-run-control-fanout-authority-mismatch.json",
    invalid_control_fanout_authority,
)

invalid_control_fanout_regression = copy.deepcopy(progressed_control_fanout)
invalid_control_fanout_regression.update({
    "fanout_version": 3,
    "previous_fanout_digest": progressed_control_fanout["fanout_digest"],
    "updated_at": "2026-07-16T09:03:03Z",
})
invalid_control_fanout_regression["targets"][0]["control_state"] = "pending"
invalid_control_fanout_regression["fanout_digest"] = digest_without(
    invalid_control_fanout_regression, "fanout_digest"
)
write(
    "tests/semantic-invalid/agent-run-control-fanout-state-regression.json",
    invalid_control_fanout_regression,
)

ui_extension_path = "examples/contracts/ui-extension-manifest.json"
ui_extension = read(ui_extension_path)
ui_provider = ui_extension["provider_revision"]
if "conformance_report_digest" in ui_provider:
    ui_provider["conformance_set_digest"] = ui_provider.pop("conformance_report_digest")
if "implementation" not in ui_provider:
    implementation_id = ui_provider.pop("plugin_id")
    implementation_version = ui_provider.pop("plugin_version")
    manifest_digest = ui_provider.pop("manifest_digest")
    distribution_digest = ui_provider.pop("package_digest")
    binding_digest = ui_provider.pop("runtime_binding_digest")
    ui_provider["implementation"] = {
        "implementation_id": implementation_id,
        "implementation_version": implementation_version,
        "distribution_type": "package",
        "distribution_digest": distribution_digest,
        "manifest_digest": manifest_digest,
        "provenance": {
            "source_revision": hashlib.sha256(ui_extension["extension_id"].encode()).hexdigest(),
            "source_tree_digest": digest({"source_tree": ui_extension["extension_id"]}),
            "build_artifact_digest": distribution_digest,
            "sbom_digest": digest({"sbom": ui_extension["extension_id"]}),
            "provenance_statement_digest": digest({"provenance": ui_extension["extension_id"]}),
            "build_system": "contract-fixture-build-v1",
        },
    }
    ui_provider["port"] = {
        "protocol": "capability-provider",
        "protocol_version": "v1",
        "contract_digest": file_digest("openapi/capability-provider-v1.yaml"),
        "binding_digest": binding_digest,
    }
ui_extension["manifest_digest"] = digest_without(ui_extension, "manifest_digest")
write(ui_extension_path, ui_extension)

case_decision_pairs = [
    ("examples/contracts/sandbox-reconciliation-case.json", "examples/contracts/sandbox-manual-review-decision.json"),
    ("examples/contracts/invocation-reconciliation-case.json", "examples/contracts/invocation-manual-review-decision.json"),
    ("examples/contracts/invocation-retry-reconciliation-case.json", "examples/contracts/invocation-retry-manual-review-decision.json"),
]
for case_path, manual_path in case_decision_pairs:
    case = read(case_path)
    case["case_digest"] = digest_without(case, "case_digest")
    write(case_path, case)
    manual = read(manual_path)
    manual["case_id"] = case["case_id"]
    manual["case_version"] = case["case_version"]
    manual["case_digest"] = case["case_digest"]
    manual["decision_digest"] = digest_without(manual, "decision_digest")
    write(manual_path, manual)

def contract_check(check_id: str) -> list[tuple[str, str, str, str]]:
    return [("semantic_validator", "urn:agent-platform:contract-validation:semantic-validator", check_id, "contract_gate")]


def implementation_check(
    kind: str, artifact: str, check_id: str,
) -> list[tuple[str, str, str, str]]:
    return [(kind, artifact, check_id, "phase0_implementation_required")]


traceability_profiles = {
    "run-manifest-v2.schema.json": [
        contract_check("run_manifest.admission"),
        contract_check("run_manifest.admission"),
        contract_check("run_manifest.admission"),
        contract_check("run_manifest.sandbox_resolution"),
        contract_check("run_manifest.admission"),
        contract_check("run_manifest.digest"),
        contract_check("run_manifest.request_binding"),
        contract_check("run_manifest.runtime_resolution"),
        contract_check("run_manifest.runtime_resolution"),
        contract_check("run_manifest.admission"),
        contract_check("run_manifest.sandbox_resolution"),
        contract_check("run_manifest.sandbox_resolution"),
        contract_check("run_manifest.sandbox_resolution"),
        contract_check("run_manifest.experience_binding"),
        contract_check("run_manifest.experience_binding"),
        contract_check("run_manifest.conversation_binding"),
        contract_check("run_manifest.conversation_binding"),
        contract_check("runtime_start.execution_topology"),
        contract_check("run_manifest.execution_inputs"),
        contract_check("run_manifest.authorization_ceiling"),
        contract_check("run_manifest.workspace_binding"),
        contract_check("run_manifest.gateway_binding"),
        contract_check("run_manifest.commercial_event_binding"),
        contract_check("run_manifest.orchestration_binding"),
        contract_check("run_manifest.admission"),
    ],
    "workflow-run.schema.json": [
        contract_check("workflow_run.lifecycle") + implementation_check(
            "ddl_responsibility", "urn:agent-platform:blueprint:docs/26_DATA_MODEL_INVARIANTS",
            "workflow_run_optional_unique_binding",
        ),
        contract_check("workflow_run.lifecycle"),
    ],
    "workflow-run-root-binding.schema.json": [
        contract_check("workflow_root_binding.digest"),
        contract_check("workflow_root_binding.scope") + implementation_check(
            "ddl_responsibility", "urn:agent-platform:blueprint:docs/26_DATA_MODEL_INVARIANTS",
            "workflow_root_binding_unique_fk",
        ),
        contract_check("workflow_root_binding.atomic_creation") + implementation_check(
            "ddl_responsibility", "urn:agent-platform:blueprint:docs/26_DATA_MODEL_INVARIANTS",
            "workflow_root_binding_deferred_atomic_insert",
        ),
    ],
    "agent-run.schema.json": [
        contract_check("agent_run.topology"),
        contract_check("agent_run.topology") + implementation_check(
            "ddl_responsibility", "urn:agent-platform:blueprint:docs/26_DATA_MODEL_INVARIANTS",
            "agent_run_parent_root_depth_fk",
        ),
        contract_check("agent_run.spawn_binding") + implementation_check(
            "ddl_responsibility", "urn:agent-platform:blueprint:docs/26_DATA_MODEL_INVARIANTS",
            "agent_run_spawn_admission_unique_fk",
        ),
        contract_check("runtime_start.execution_topology"),
    ],
    "agent-run-budget-allocation.schema.json": [
        contract_check("agent_budget.digest"),
        contract_check("agent_budget.scope"),
        contract_check("agent_budget.shared_ledger") + implementation_check(
            "ddl_responsibility", "urn:agent-platform:blueprint:docs/26_DATA_MODEL_INVARIANTS",
            "work_order_shared_budget_ledger",
        ),
        contract_check("agent_budget.shared_ledger") + implementation_check(
            "ddl_responsibility", "urn:agent-platform:blueprint:docs/26_DATA_MODEL_INVARIANTS",
            "child_admission_topology_limits",
        ),
    ],
    "child-agent-run-spawn-request.schema.json": [
        contract_check("child_spawn.digest"),
        contract_check("child_spawn.scope"),
        contract_check("child_spawn.scope"),
        contract_check("child_spawn.provider_boundary"),
        contract_check("child_spawn.idempotency") + implementation_check(
            "ddl_responsibility", "urn:agent-platform:blueprint:docs/26_DATA_MODEL_INVARIANTS",
            "child_spawn_idempotency_unique",
        ),
    ],
    "child-agent-run-admission-decision.schema.json": [
        contract_check("child_admission.digest"),
        contract_check("child_admission.outcome") + implementation_check(
            "ddl_responsibility", "urn:agent-platform:blueprint:docs/26_DATA_MODEL_INVARIANTS",
            "child_admission_single_decision",
        ),
        contract_check("child_admission.atomic_creation") + implementation_check(
            "ddl_responsibility", "urn:agent-platform:blueprint:docs/26_DATA_MODEL_INVARIANTS",
            "child_admission_atomic_insert",
        ),
        contract_check("child_admission.outcome"),
        contract_check("child_admission.atomic_creation") + implementation_check(
            "ddl_responsibility", "urn:agent-platform:blueprint:docs/26_DATA_MODEL_INVARIANTS",
            "child_admission_active_authorization_guard",
        ),
    ],
    "agent-run-control-fanout.schema.json": [
        contract_check("control_fanout.digest"),
        contract_check("control_fanout.authority") + implementation_check(
            "ddl_responsibility", "urn:agent-platform:blueprint:docs/26_DATA_MODEL_INVARIANTS",
            "agent_run_control_fanout_authority_fk",
        ),
        contract_check("control_fanout.coverage") + implementation_check(
            "ddl_responsibility", "urn:agent-platform:blueprint:docs/26_DATA_MODEL_INVARIANTS",
            "agent_run_control_fanout_target_snapshot",
        ),
        contract_check("control_fanout.fencing"),
        contract_check("control_fanout.recovery") + implementation_check(
            "conformance_test", "conformance/runtime/v1/suite.json",
            "multi-agent-control-and-terminal",
        ),
    ],
    "runtime-input-envelope.schema.json": [
        contract_check("runtime_start.input_binding"),
        contract_check("runtime_start.input_binding"),
        contract_check("agent_run.spawn_binding"),
    ],
    "agent-runtime-start-request.schema.json": [
        contract_check("runtime_start.execution_topology"),
        contract_check("runtime_start.workspace_binding"),
        contract_check("runtime_start.sandbox_binding"),
        contract_check("runtime_start.request_digest"),
        contract_check("runtime_start.input_binding"),
        contract_check("runtime_start.immutable_context_binding") + contract_check("runtime_authorization.ceiling"),
        contract_check("runtime_authorization.scope") + contract_check("runtime_authorization.expiry") + contract_check("runtime_authorization.artifact_coverage"),
        implementation_check("conformance_test", "conformance/runtime/v1/suite.json", "start-encoded-body-limit"),
        contract_check("runtime_token.binding"),
    ],
    "agent-runtime-invocation-token-claims.schema.json": [
        contract_check("runtime_token.lifetime"),
        contract_check("runtime_token.audience"),
        contract_check("runtime_token.binding"),
        contract_check("runtime_token.binding"),
        contract_check("runtime_token.binding") + implementation_check(
            "conformance_test", "conformance/runtime/v1/suite.json",
            "runtime-token-replay-and-expiry",
        ),
    ],
    "agent-runtime-command.schema.json": [
        contract_check("runtime_command.digest"),
        contract_check("runtime_command.sequence"),
        contract_check("runtime_command.idempotency") + implementation_check(
            "ddl_responsibility", "urn:agent-platform:blueprint:docs/26_DATA_MODEL_INVARIANTS",
            "runtime_command_append_only_idempotency",
        ),
        contract_check("runtime_command.fencing"),
        contract_check("runtime_command.user_control_binding") + implementation_check(
            "ddl_responsibility", "urn:agent-platform:blueprint:docs/26_DATA_MODEL_INVARIANTS",
            "runtime_command_user_control_fk",
        ),
        contract_check("runtime_command.system_safety_binding") + implementation_check(
            "ddl_responsibility", "urn:agent-platform:blueprint:docs/26_DATA_MODEL_INVARIANTS",
            "runtime_command_system_safety_fk",
        ),
        contract_check("runtime_command.child_admission_binding") + implementation_check(
            "ddl_responsibility", "urn:agent-platform:blueprint:docs/26_DATA_MODEL_INVARIANTS",
            "runtime_command_child_admission_fk",
        ),
        contract_check("runtime_token.binding"),
    ],
    "system-safety-control.schema.json": [
        contract_check("system_safety_control.digest"),
        contract_check("system_safety_control.scope"),
        contract_check("system_safety_control.evidence") + implementation_check(
            "ddl_responsibility", "urn:agent-platform:blueprint:docs/26_DATA_MODEL_INVARIANTS",
            "system_safety_control_trigger_evidence_fk",
        ),
        implementation_check(
            "ddl_responsibility", "urn:agent-platform:blueprint:docs/26_DATA_MODEL_INVARIANTS",
            "system_safety_control_append_only_idempotency",
        ),
        contract_check("system_safety_control.reduction_only") + implementation_check(
            "conformance_test", "conformance/runtime/v1/suite.json",
            "system-safety-control",
        ),
    ],
    "commercial-authorization-revocation.schema.json": [
        contract_check("commercial_revocation.digest"),
        contract_check("commercial_revocation.time_order"),
        contract_check("commercial_revocation.sender_binding"),
        contract_check("commercial_revocation.authorization_binding"),
        implementation_check(
            "ddl_responsibility", "urn:agent-platform:blueprint:docs/26_DATA_MODEL_INVARIANTS",
            "commercial_authorization_revocation_fanout",
        ) + implementation_check(
            "conformance_test", "conformance/agent-access/v1/suite.json",
            "commercial-authorization-revocation-ingest",
        ) + implementation_check(
            "conformance_test", "conformance/runtime/v1/suite.json",
            "system-safety-control",
        ),
        implementation_check(
            "conformance_test", "conformance/agent-access/v1/suite.json",
            "resource-path-request-binding",
        ),
    ],
    "commercial-authorization-revocation-accepted.schema.json": [
        contract_check("commercial_revocation.fanout"),
        contract_check("commercial_revocation.fanout"),
        contract_check("commercial_revocation.fanout") + implementation_check(
            "ddl_responsibility", "urn:agent-platform:blueprint:docs/26_DATA_MODEL_INVARIANTS",
            "commercial_authorization_revocation_fanout",
        ),
        contract_check("commercial_revocation.fanout") + implementation_check(
            "ddl_responsibility", "urn:agent-platform:blueprint:docs/26_DATA_MODEL_INVARIANTS",
            "commercial_authorization_revocation_fanout",
        ),
        contract_check("commercial_revocation.fanout") + implementation_check(
            "conformance_test", "conformance/agent-access/v1/suite.json",
            "commercial-authorization-revocation-ingest",
        ),
    ],
    "sandbox-operation-token-claims.schema.json": [
        contract_check("sandbox_token.lifetime"),
        contract_check("sandbox_token.binding"),
        contract_check("sandbox_token.binding"),
        contract_check("sandbox_token.binding") + implementation_check(
            "conformance_test", "conformance/sandbox/v1/suite.json",
            "operation-token-binding",
        ),
    ],
    "sandbox-spec.schema.json": [
        contract_check("sandbox_spec.execution_ceiling"),
        contract_check("sandbox_spec.execution_ceiling"),
        contract_check("sandbox_spec.execution_ceiling"),
        contract_check("sandbox_spec.workspace_binding"),
        contract_check("sandbox_spec.workspace_binding") + implementation_check(
            "ddl_responsibility", "urn:agent-platform:blueprint:docs/26_DATA_MODEL_INVARIANTS",
            "branch_workspace_revision_fk",
        ),
    ],
    "work-order-control-request.schema.json": [
        contract_check("work_order_control.grant_binding"),
        contract_check("work_order_control.conditional_cas"),
        implementation_check("ddl_responsibility", "urn:agent-platform:blueprint:docs/26_DATA_MODEL_INVARIANTS", "work_order_control_input_allocation_and_outbox"),
        contract_check("work_order_control.authority_exclusive"),
        implementation_check(
            "conformance_test", "conformance/agent-access/v1/suite.json",
            "resource-path-request-binding",
        ),
    ],
    "conversation-branch.schema.json": [
        contract_check("conversation_branch.head_consistency"),
        implementation_check("ddl_responsibility", "urn:agent-platform:blueprint:docs/26_DATA_MODEL_INVARIANTS", "branch_fork_prior_message_fk"),
        implementation_check("ddl_responsibility", "urn:agent-platform:blueprint:docs/26_DATA_MODEL_INVARIANTS", "branch_one_active_work_order"),
        implementation_check("ddl_responsibility", "urn:agent-platform:blueprint:docs/26_DATA_MODEL_INVARIANTS", "message_workspace_active_work_split_cas"),
        implementation_check("ddl_responsibility", "urn:agent-platform:blueprint:docs/26_DATA_MODEL_INVARIANTS", "branch_etag_not_write_cas"),
        contract_check("conversation_branch.workspace_binding") + implementation_check("ddl_responsibility", "urn:agent-platform:blueprint:docs/26_DATA_MODEL_INVARIANTS", "branch_workspace_revision_fk"),
    ],
    "provider-resolution.schema.json": [
        contract_check("provider_resolution.decision_digest"),
        implementation_check("ddl_responsibility", "urn:agent-platform:blueprint:docs/26_DATA_MODEL_INVARIANTS", "provider_resolution_complete_input_evidence"),
        contract_check("provider_resolution.execution_scope") + implementation_check("ddl_responsibility", "urn:agent-platform:blueprint:docs/26_DATA_MODEL_INVARIANTS", "tenant_client_work_order_provider_resolution"),
        contract_check("provider_resolution.identity_dependency"),
        contract_check("provider_resolution.selected_candidate"),
        implementation_check("ddl_responsibility", "urn:agent-platform:blueprint:docs/26_DATA_MODEL_INVARIANTS", "provider_resolution_immutable_evidence_lookup"),
    ],
    "capability-invocation-request.schema.json": [
        contract_check("capability_invocation.request_digest"),
        contract_check("capability_invocation.owner_request_binding"),
        implementation_check("conformance_test", "conformance/capability/v1/suite.json", "request-schema-boundaries"),
        contract_check("capability_invocation.resolution_binding") + implementation_check("conformance_test", "conformance/capability/v1/suite.json", "token-binding"),
        contract_check("capability_invocation.execution_context") + implementation_check("conformance_test", "conformance/capability/v1/suite.json", "budget-policy-enforced"),
        contract_check("capability_invocation.token_binding") + implementation_check("conformance_test", "conformance/capability/v1/suite.json", "token-binding"),
        contract_check("capability_invocation.artifact_grant_expiry") + contract_check("capability_invocation.staging_grant") + implementation_check("conformance_test", "conformance/capability/v1/suite.json", "artifact-contract"),
        contract_check("secret_mediation.binding") + implementation_check(
            "conformance_test", "conformance/credential/v1/suite.json", "grant-token-request-binding"
        ),
    ],
    "capability-invocation-token-claims.schema.json": [
        contract_check("capability_invocation.token_lifetime"),
        contract_check("capability_invocation.token_lineage"),
        contract_check("capability_invocation.operation_binding"),
        contract_check("capability_invocation.token_binding"),
    ],
    "capability-status-operation-descriptor.schema.json": [
        contract_check("capability_invocation.operation_binding"),
        contract_check("capability_invocation.operation_binding"),
    ],
    "capability-event-read-operation-descriptor.schema.json": [
        contract_check("capability_invocation.operation_binding"),
        contract_check("capability_invocation.operation_binding") + implementation_check(
            "conformance_test", "conformance/capability/v1/suite.json",
            "event-cursor-resume",
        ),
    ],
    "capability-cancellation-request.schema.json": [
        contract_check("capability_invocation.operation_binding"),
        contract_check("capability_invocation.operation_binding"),
        implementation_check("conformance_test", "conformance/capability/v1/suite.json", "timeout-cancel-status"),
    ],
    "workspace-content-manifest.schema.json": [
        contract_check("workspace_manifest.digest"),
        contract_check("workspace_manifest.path_policy"),
        contract_check("workspace_manifest.counts"),
        contract_check("workspace_manifest.symlink_policy"),
    ],
    "runtime-session-request.schema.json": [
        contract_check("runtime_session.requested_scope_subset") + implementation_check("conformance_test", "conformance/runtime-gateway/v1/suite.json", "session-scope-enforced"),
        contract_check("runtime_session.sandbox_slot_binding") + implementation_check("conformance_test", "conformance/runtime-gateway/v1/suite.json", "slot-scoped-runtime-session"),
        contract_check("runtime_session.scope_class"),
        implementation_check("conformance_test", "conformance/runtime-gateway/v1/suite.json", "platform-managed-recording-authority"),
        contract_check("runtime_session.channel_policy"),
    ],
    "runtime-session-route.schema.json": [
        contract_check("runtime_session.route_digest"),
        contract_check("runtime_session.route_scope") + implementation_check(
            "conformance_test", "conformance/runtime-gateway/v1/suite.json",
            "slot-scoped-runtime-session",
        ),
        contract_check("runtime_session.route_opaque"),
        contract_check("runtime_session.route_scope") + implementation_check(
            "conformance_test", "conformance/runtime-gateway/v1/suite.json",
            "session-scope-enforced",
        ),
    ],
    "canonical-event-v2.schema.json": [
        implementation_check("ddl_responsibility", "urn:agent-platform:blueprint:docs/26_DATA_MODEL_INVARIANTS", "conversation_event_omits_work_scope"),
        contract_check("canonical_event.work_binding"),
        contract_check("canonical_event.execution_scope"),
        implementation_check("ddl_responsibility", "urn:agent-platform:blueprint:docs/26_DATA_MODEL_INVARIANTS", "aggregate_and_work_sequence_ledgers"),
        contract_check("canonical_event.source_dedupe"),
        implementation_check("ddl_responsibility", "urn:agent-platform:blueprint:docs/26_DATA_MODEL_INVARIANTS", "canonical_event_inbox_source_uniqueness"),
        contract_check("canonical_event.producer_binding"),
        contract_check("canonical_event.registry_binding"),
    ],
    "idempotency-record.schema.json": [
        implementation_check("ddl_responsibility", "urn:agent-platform:blueprint:docs/26_DATA_MODEL_INVARIANTS", "idempotency_scope_unique_index"),
        implementation_check("ddl_responsibility", "urn:agent-platform:blueprint:docs/26_DATA_MODEL_INVARIANTS", "idempotency_digest_conflict"),
    ],
    "execution-grant-claims.schema.json": [
        contract_check("execution_grant.clock_skew"),
        contract_check("execution_grant.expiration_order"),
        contract_check("execution_grant.max_ttl"),
        contract_check("execution_grant.request_digest"),
        contract_check("execution_grant.principal_context"),
        contract_check("execution_grant.request_identity"),
        contract_check("execution_grant.commercial_limits"),
        contract_check("execution_grant.snapshot_validity"),
    ],
    "service-access-token-claims.schema.json": [
        contract_check("service_token.lifetime"),
        contract_check("service_token.binding"),
        contract_check("service_token.scope"),
        contract_check("service_token.binding") + implementation_check(
            "conformance_test", "urn:agent-platform:blueprint:docs/17_IDENTITY_AND_AUTHORIZATION",
            "token_profile_signature_and_type_isolation",
        ),
        contract_check("service_token.binding") + implementation_check(
            "conformance_test", "urn:agent-platform:blueprint:docs/17_IDENTITY_AND_AUTHORIZATION",
            "service_token_sender_constraint_and_replay",
        ),
    ],
    "work-session-claims.schema.json": [
        contract_check("work_session.lifetime"),
        contract_check("work_session.binding"),
        contract_check("work_session.scope"),
        contract_check("work_session.binding") + implementation_check(
            "conformance_test", "urn:agent-platform:blueprint:docs/17_IDENTITY_AND_AUTHORIZATION",
            "token_profile_signature_and_type_isolation",
        ),
        contract_check("work_session.binding"),
        contract_check("work_session.lifetime") + implementation_check(
            "ddl_responsibility", "urn:agent-platform:blueprint:docs/26_DATA_MODEL_INVARIANTS",
            "work_session_revocation_version",
        ),
    ],
    "plugin-invocation-request.schema.json": [
        contract_check("plugin_token.binding"),
        contract_check("plugin_token.binding"),
        contract_check("plugin_token.binding") + implementation_check(
            "conformance_test", "conformance/capability/v1/suite.json",
            "legacy-plugin-bridge-token-binding",
        ),
    ],
    "plugin-invocation-token-claims.schema.json": [
        contract_check("plugin_token.lifetime"),
        contract_check("plugin_token.binding"),
        contract_check("plugin_token.binding"),
        contract_check("plugin_token.binding") + implementation_check(
            "conformance_test", "conformance/capability/v1/suite.json",
            "legacy-plugin-bridge-token-binding",
        ),
    ],
    "runtime-authorization.schema.json": [
        contract_check("runtime_authorization.digest"),
        contract_check("runtime_authorization.lineage"),
        contract_check("runtime_authorization.ceiling"),
        contract_check("runtime_authorization.internal_binding"),
        contract_check("runtime_authorization.scope"),
        contract_check("runtime_authorization.expiry"),
        contract_check("runtime_authorization.artifact_coverage") + implementation_check("conformance_test", "conformance/runtime/v1/suite.json", "authorization-renewal"),
    ],
    "artifact-grant.schema.json": [
        contract_check("artifact_grant.digest"),
        contract_check("artifact_grant.expiry"),
        contract_check("artifact_grant.scope"),
        contract_check("artifact_grant.provider_permissions"),
    ],
    "artifact-staging-grant.schema.json": [
        contract_check("artifact_staging_grant.digest"),
        contract_check("artifact_staging_grant.scope"),
        contract_check("artifact_staging_grant.expiry"),
        contract_check("artifact_staging_grant.permissions") + implementation_check("conformance_test", "conformance/execution-gateway/v1/suite.json", "artifact-no-provider-finalize"),
    ],
    "artifact-gateway-token-claims.schema.json": [
        contract_check("artifact_gateway.token_binding"),
        contract_check("artifact_gateway.operation_binding"),
        contract_check("artifact_gateway.token_binding") + implementation_check("conformance_test", "conformance/execution-gateway/v1/suite.json", "artifact-operation-token-binding"),
    ],
    "artifact-read-operation-descriptor.schema.json": [
        contract_check("artifact_gateway.operation_binding"),
        contract_check("artifact_gateway.operation_binding"),
    ],
    "artifact-staging-object-request.schema.json": [
        contract_check("artifact_gateway.operation_binding"),
        contract_check("artifact_gateway.operation_binding") + implementation_check("conformance_test", "conformance/execution-gateway/v1/suite.json", "artifact-staging-byte-digest"),
    ],
    "artifact-staging-commit-request.schema.json": [
        contract_check("artifact_gateway.operation_binding"),
        contract_check("artifact_gateway.operation_binding") + implementation_check("conformance_test", "conformance/execution-gateway/v1/suite.json", "artifact-staging-limits"),
        contract_check("artifact_staging_grant.permissions") + implementation_check("conformance_test", "conformance/execution-gateway/v1/suite.json", "artifact-no-provider-finalize"),
    ],
    "principal-context-snapshot.schema.json": [
        contract_check("principal_context.digest"),
        contract_check("principal_context.time_window"),
        contract_check("principal_context.closed_attributes"),
    ],
    "runtime-gateway-bindings.schema.json": [
        contract_check("gateway_binding.closed_modes"),
        contract_check("gateway_binding.port_contract"),
        contract_check("gateway_binding.policy_alignment"),
    ],
    "gateway-port-binding.schema.json": [
        contract_check("gateway_port.contract_mapping"),
        contract_check("gateway_port.audience_binding"),
    ],
    "egress-http-request.schema.json": [
        contract_check("egress_gateway.request_binding"),
        implementation_check("conformance_test", "conformance/execution-gateway/v1/suite.json", "egress-address-revalidation"),
        implementation_check("conformance_test", "conformance/execution-gateway/v1/suite.json", "egress-header-and-body-limits"),
    ],
    "egress-destination-revision.schema.json": [
        contract_check("egress_destination.digest") + implementation_check(
            "ddl_responsibility", "urn:agent-platform:blueprint:docs/26_DATA_MODEL_INVARIANTS",
            "egress_destination_revision_immutable",
        ),
        contract_check("egress_destination.owner_scope"),
        contract_check("egress_destination.request_policy"),
        contract_check("egress_destination.request_policy") + implementation_check(
            "conformance_test", "conformance/execution-gateway/v1/suite.json",
            "egress-address-revalidation",
        ),
    ],
    "egress-invocation-token-claims.schema.json": [
        contract_check("egress_gateway.token_binding"),
        contract_check("egress_gateway.token_binding") + implementation_check("conformance_test", "conformance/execution-gateway/v1/suite.json", "egress-operation-token-binding"),
        contract_check("egress_gateway.request_binding") + implementation_check("conformance_test", "conformance/execution-gateway/v1/suite.json", "egress-registered-destination-only"),
    ],
    "capability-invocation-result.schema.json": [
        implementation_check("conformance_test", "conformance/capability/v1/suite.json", "request-schema-boundaries"),
        implementation_check("conformance_test", "conformance/capability/v1/suite.json", "artifact-contract"),
        contract_check("usage_observation.provider_boundary"),
    ],
    "usage-observation.schema.json": [
        contract_check("usage_observation.observation_identity"),
        contract_check("usage_observation.meter_and_evidence"),
        contract_check("usage_observation.incomplete_status"),
    ],
}

traceability_profiles.update({
    "provider-revision.schema.json": [
        contract_check("provider_revision.integrity"),
        contract_check("provider_revision.integrity"),
        implementation_check("ddl_responsibility", "urn:agent-platform:blueprint:docs/26_DATA_MODEL_INVARIANTS", "provider_revision_immutable"),
        contract_check("provider_revision.integrity"),
        contract_check("provider_revision.integrity") + implementation_check(
            "conformance_test", "urn:agent-platform:blueprint:tasks/PHASE0", "provider_revision_conformance_evidence"
        ),
    ],
    "policy-decision.schema.json": [
        contract_check("policy_decision.outcome_time"),
        contract_check("policy_decision.outcome_time"),
        contract_check("policy_decision.outcome_time"),
        implementation_check("conformance_test", "urn:agent-platform:blueprint:tasks/PHASE0", "policy_complete_requirement_evaluation"),
        contract_check("policy_decision.outcome_time"),
        implementation_check("conformance_test", "urn:agent-platform:blueprint:tasks/PHASE0", "policy_defense_in_depth_enforcement"),
    ],
    "technical-usage-entry.schema.json": [
        implementation_check("ddl_responsibility", "urn:agent-platform:blueprint:docs/26_DATA_MODEL_INVARIANTS", "technical_usage_identity_uniqueness"),
        contract_check("technical_usage.binding"),
        implementation_check("ddl_responsibility", "urn:agent-platform:blueprint:docs/26_DATA_MODEL_INVARIANTS", "technical_usage_correction_chain"),
        contract_check("technical_usage.binding") + implementation_check(
            "conformance_test", "urn:agent-platform:blueprint:tasks/PHASE0", "technical_usage_unknown_not_zero"
        ),
        implementation_check("conformance_test", "urn:agent-platform:blueprint:tasks/PHASE0", "technical_usage_evidence_resolution"),
        contract_check("technical_usage.binding"),
        contract_check("technical_usage.binding") + implementation_check(
            "conformance_test", "urn:agent-platform:blueprint:tasks/PHASE0", "technical_usage_platform_ownership"
        ),
        implementation_check("ddl_responsibility", "urn:agent-platform:blueprint:docs/26_DATA_MODEL_INVARIANTS", "technical_usage_multi_agent_attribution"),
    ],
    "usage-report.schema.json": [
        contract_check("usage_report.finality"),
        contract_check("usage_report.finality"),
        contract_check("usage_report.finality"),
        implementation_check("ddl_responsibility", "urn:agent-platform:blueprint:docs/26_DATA_MODEL_INVARIANTS", "usage_report_sequence_and_predecessor"),
        contract_check("usage_report.finality") + implementation_check(
            "ddl_responsibility", "urn:agent-platform:blueprint:docs/26_DATA_MODEL_INVARIANTS", "usage_report_append_only_correction"
        ),
    ],
    "business-settlement-envelope.schema.json": [
        contract_check("settlement.accounting"),
        contract_check("settlement.accounting"),
        contract_check("settlement.accounting"),
        contract_check("settlement.accounting"),
        implementation_check("ddl_responsibility", "urn:agent-platform:blueprint:docs/26_DATA_MODEL_INVARIANTS", "settlement_envelope_sequence"),
        implementation_check("conformance_test", "urn:agent-platform:blueprint:tasks/PHASE0", "business_settlement_dedupe_and_evidence_immutability"),
        implementation_check("conformance_test", "urn:agent-platform:blueprint:tasks/PHASE0", "business_settlement_technical_facts_only"),
    ],
    "runtime-gateway-frame.schema.json": [
        implementation_check("conformance_test", "conformance/runtime-gateway/v1/suite.json", "stale-generation-rejected"),
        contract_check("runtime_gateway.frame_integrity") + implementation_check(
            "conformance_test", "conformance/runtime-gateway/v1/suite.json", "stale-generation-rejected"
        ),
        implementation_check("conformance_test", "conformance/runtime-gateway/v1/suite.json", "ack-backpressure"),
        contract_check("runtime_gateway.frame_integrity"),
        implementation_check("conformance_test", "conformance/runtime-gateway/v1/suite.json", "resume-expired-explicit"),
        contract_check("runtime_gateway.frame_integrity") + implementation_check(
            "conformance_test", "conformance/runtime-gateway/v1/suite.json", "control-idempotent"
        ),
        implementation_check("conformance_test", "conformance/runtime-gateway/v1/suite.json", "recording-alignment"),
        implementation_check("conformance_test", "conformance/runtime-gateway/v1/suite.json", "port-forward-live-only"),
    ],
    "workspace-revision.schema.json": [
        contract_check("workspace_revision.chain"),
        implementation_check("ddl_responsibility", "urn:agent-platform:blueprint:docs/26_DATA_MODEL_INVARIANTS", "workspace_revision_contiguous"),
        contract_check("workspace_revision.chain") + implementation_check(
            "ddl_responsibility", "urn:agent-platform:blueprint:docs/26_DATA_MODEL_INVARIANTS", "workspace_revision_immediate_predecessor"
        ),
        implementation_check("ddl_responsibility", "urn:agent-platform:blueprint:docs/26_DATA_MODEL_INVARIANTS", "workspace_revision_fork_origin"),
        implementation_check("conformance_test", "urn:agent-platform:blueprint:tasks/PHASE0", "workspace_manifest_admission"),
    ],
    "work-order-state.schema.json": [
        contract_check("work_order_state.machine"),
        implementation_check("ddl_responsibility", "urn:agent-platform:blueprint:docs/26_DATA_MODEL_INVARIANTS", "work_order_sequence_and_outbox"),
        implementation_check("ddl_responsibility", "urn:agent-platform:blueprint:docs/26_DATA_MODEL_INVARIANTS", "workflow_root_binding_authority"),
        implementation_check("ddl_responsibility", "urn:agent-platform:blueprint:docs/26_DATA_MODEL_INVARIANTS", "work_order_terminal_usage_accounting"),
    ],
    "artifact-operation-context.schema.json": [
        contract_check("artifact_operation.binding"),
        contract_check("artifact_operation.binding"),
        contract_check("artifact_operation.binding"),
        implementation_check("ddl_responsibility", "urn:agent-platform:blueprint:docs/26_DATA_MODEL_INVARIANTS", "artifact_operation_idempotency_scope"),
        implementation_check(
            "conformance_test", "conformance/agent-access/v1/suite.json",
            "resource-path-request-binding",
        ),
    ],
    "artifact-operation.schema.json": [
        contract_check("artifact_operation.binding"),
        contract_check("artifact_operation.binding"),
        contract_check("artifact_operation.binding"),
        contract_check("artifact_operation.binding") + implementation_check(
            "ddl_responsibility", "urn:agent-platform:blueprint:docs/26_DATA_MODEL_INVARIANTS", "artifact_operation_state_and_terminal_evidence"
        ),
        contract_check("artifact_operation.cancellation") + implementation_check(
            "ddl_responsibility", "urn:agent-platform:blueprint:docs/26_DATA_MODEL_INVARIANTS", "artifact_operation_cancellation_outbox"
        ),
        contract_check("artifact_operation.cancellation") + implementation_check(
            "conformance_test", "urn:agent-platform:blueprint:tasks/PHASE0", "artifact_operation_cancellation_reconciliation"
        ),
        implementation_check("conformance_test", "urn:agent-platform:blueprint:tasks/PHASE0", "artifact_operation_platform_finalization"),
    ],
    "conversation-branch-create-request.schema.json": [
        contract_check("conversation_branch.create"),
        implementation_check("ddl_responsibility", "urn:agent-platform:blueprint:docs/26_DATA_MODEL_INVARIANTS", "conversation_branch_create_idempotency"),
        contract_check("conversation_branch.create"),
        contract_check("conversation_branch.create"),
        implementation_check("ddl_responsibility", "urn:agent-platform:blueprint:docs/26_DATA_MODEL_INVARIANTS", "conversation_branch_create_atomic_outbox"),
        implementation_check(
            "conformance_test", "conformance/agent-access/v1/suite.json",
            "resource-path-request-binding",
        ),
    ],
    "conversation-branch-created.schema.json": [
        contract_check("conversation_branch.created_workspace") + implementation_check(
            "ddl_responsibility", "urn:agent-platform:blueprint:docs/26_DATA_MODEL_INVARIANTS",
            "conversation_branch_create_atomic_outbox",
        ),
    ],
    "no-usage-attestation.schema.json": [
        contract_check("no_usage.accounting"),
        contract_check("no_usage.accounting") + implementation_check(
            "ddl_responsibility", "urn:agent-platform:blueprint:docs/26_DATA_MODEL_INVARIANTS", "no_usage_absence_proof"
        ),
        contract_check("no_usage.accounting") + implementation_check(
            "conformance_test", "urn:agent-platform:blueprint:tasks/PHASE0", "unknown_usage_never_zero"
        ),
        implementation_check("ddl_responsibility", "urn:agent-platform:blueprint:docs/26_DATA_MODEL_INVARIANTS", "no_usage_attestation_append_only"),
    ],
    "delivery-package.schema.json": [
        contract_check("no_usage.accounting") + implementation_check(
            "ddl_responsibility", "urn:agent-platform:blueprint:docs/26_DATA_MODEL_INVARIANTS", "delivery_usage_accounting_required"
        ),
        contract_check("no_usage.accounting"),
    ],
    "compatibility-evidence.schema.json": [
        contract_check("compatibility.fail_closed"),
        contract_check("compatibility.fail_closed") + implementation_check(
            "conformance_test", "urn:agent-platform:blueprint:tasks/PHASE0", "compatibility_suite_evidence_authenticity"
        ),
        contract_check("compatibility.fail_closed"),
    ],
    "compatibility-decision.schema.json": [
        contract_check("compatibility.fail_closed"),
        contract_check("compatibility.fail_closed"),
        contract_check("compatibility.fail_closed") + implementation_check(
            "conformance_test", "urn:agent-platform:blueprint:tasks/PHASE0", "compatibility_restore_dispatch_guard"
        ),
        implementation_check("ddl_responsibility", "urn:agent-platform:blueprint:docs/26_DATA_MODEL_INVARIANTS", "compatibility_decision_platform_ownership"),
    ],
    "agent-runtime-checkpoint-manifest.schema.json": [
        contract_check("compatibility.fail_closed"),
        contract_check("compatibility.fail_closed"),
        implementation_check("conformance_test", "conformance/runtime/v1/suite.json", "checkpoint-restore-fail-closed"),
    ],
    "sandbox-snapshot-manifest.schema.json": [
        contract_check("compatibility.fail_closed"),
        contract_check("compatibility.fail_closed"),
        implementation_check("conformance_test", "conformance/sandbox/v1/suite.json", "workspace-restore-fail-closed"),
    ],
    "sandbox-restore-request.schema.json": [
        contract_check("compatibility.fail_closed"),
        implementation_check("conformance_test", "conformance/sandbox/v1/suite.json", "workspace-restore-fail-closed"),
    ],
    "secret-grant.schema.json": [
        contract_check("secret_mediation.binding"),
        contract_check("secret_mediation.binding"),
        contract_check("secret_mediation.binding"),
        contract_check("secret_mediation.binding") + implementation_check(
            "conformance_test", "conformance/credential/v1/suite.json", "single-use-and-revocation"
        ),
        contract_check("secret_mediation.binding") + implementation_check(
            "conformance_test", "conformance/credential/v1/suite.json", "no-secret-persistence"
        ),
        implementation_check("conformance_test", "conformance/credential/v1/suite.json", "audit-before-delivery"),
    ],
    "secret-grant-revocation.schema.json": [
        contract_check("secret_mediation.binding"),
        implementation_check("ddl_responsibility", "urn:agent-platform:blueprint:docs/26_DATA_MODEL_INVARIANTS", "secret_grant_revocation_synchronous_deny"),
    ],
    "credential-access-request.schema.json": [
        contract_check("secret_mediation.binding"),
        contract_check("secret_mediation.binding"),
    ],
    "credential-operation-token-claims.schema.json": [
        contract_check("secret_mediation.binding"),
        contract_check("secret_mediation.binding"),
        contract_check("secret_mediation.binding") + implementation_check(
            "conformance_test", "conformance/credential/v1/suite.json", "single-use-and-revocation"
        ),
    ],
    "artifact-ingest-request.schema.json": [
        contract_check("artifact_ingest.lifecycle"),
        implementation_check(
            "conformance_test", "urn:agent-platform:blueprint:tasks/PHASE0", "artifact_ingest_authorization"
        ),
        contract_check("artifact_ingest.lifecycle") + implementation_check(
            "conformance_test", "urn:agent-platform:blueprint:tasks/PHASE0", "artifact_ingest_authorization"
        ),
        implementation_check("ddl_responsibility", "urn:agent-platform:blueprint:docs/26_DATA_MODEL_INVARIANTS", "artifact_ingest_idempotency_scope"),
    ],
    "artifact-ingest-confirm-request.schema.json": [
        implementation_check(
            "ddl_responsibility", "urn:agent-platform:blueprint:docs/26_DATA_MODEL_INVARIANTS",
            "artifact_ingest_digest_idempotency",
        ),
        implementation_check(
            "conformance_test", "urn:agent-platform:blueprint:tasks/PHASE0", "artifact_ingest_authorization",
        ),
        implementation_check(
            "conformance_test", "conformance/agent-access/v1/suite.json",
            "resource-path-request-binding",
        ),
    ],
    "artifact-ingest-session.schema.json": [
        contract_check("artifact_ingest.lifecycle") + implementation_check(
            "ddl_responsibility", "urn:agent-platform:blueprint:docs/26_DATA_MODEL_INVARIANTS", "artifact_ingest_state_version"
        ),
        implementation_check("conformance_test", "urn:agent-platform:blueprint:tasks/PHASE0", "artifact_ingest_authorized_status"),
        contract_check("artifact_ingest.lifecycle"),
        contract_check("artifact_ingest.lifecycle") + implementation_check(
            "ddl_responsibility", "urn:agent-platform:blueprint:docs/26_DATA_MODEL_INVARIANTS", "artifact_ingest_platform_finalize_transaction"
        ),
        implementation_check("ddl_responsibility", "urn:agent-platform:blueprint:docs/26_DATA_MODEL_INVARIANTS", "artifact_ingest_digest_idempotency"),
    ],
    "artifact-ingest-scan-result.schema.json": [
        contract_check("artifact_ingest.lifecycle"),
        contract_check("artifact_ingest.lifecycle") + implementation_check(
            "conformance_test", "urn:agent-platform:blueprint:tasks/PHASE0", "artifact_ingest_scan_evidence"
        ),
        contract_check("artifact_ingest.lifecycle"),
    ],
    "artifact-ingest-finalize-command.schema.json": [
        contract_check("artifact_ingest.lifecycle"),
        contract_check("artifact_ingest.lifecycle") + implementation_check(
            "ddl_responsibility", "urn:agent-platform:blueprint:docs/26_DATA_MODEL_INVARIANTS", "artifact_ingest_platform_finalize_transaction"
        ),
        contract_check("artifact_ingest.lifecycle"),
    ],
})

for schema_path in sorted((CONTRACT_ROOT / "schemas").glob("*.json")):
    schema = read(str(schema_path))
    statements = schema.get("x-semantic-constraints", [])
    if statements and schema_path.name not in traceability_profiles:
        traceability_profiles[schema_path.name] = [
            implementation_check(
                "conformance_test", "urn:agent-platform:blueprint:tasks/PHASE0",
                "stable_semantic_constraint_implementation_evidence",
            )
            for _statement in statements
        ]

traceability_constraints = []
for schema_filename, constraint_enforcements in traceability_profiles.items():
    schema = read(f"schemas/{schema_filename}")
    statements = schema.get("x-semantic-constraints", [])
    if len(statements) != len(constraint_enforcements):
        raise AssertionError(
            f"Traceability profile length differs from {schema_filename} semantic constraints"
        )
    for index, statement in enumerate(statements):
        enforcements = constraint_enforcements[index]
        identifier_material = f"{schema['$id']}\n{index}\n{statement}".encode()
        traceability_constraints.append({
            "constraint_id": "sem-" + hashlib.sha256(identifier_material).hexdigest()[:16],
            "schema_id": schema["$id"],
            "constraint_index": index,
            "statement": statement,
            "enforcements": [
                {"kind": kind, "artifact": artifact, "check_id": check_id, "status": status}
                for kind, artifact, check_id, status in enforcements
            ],
        })
traceability = {
    "traceability_id": "phase0-critical-semantic-constraints",
    "version": 1,
    "generated_at": "2026-07-20T00:00:00Z",
    "critical_schema_ids": [
        read(f"schemas/{filename}")["$id"] for filename in traceability_profiles
    ],
    "constraints": traceability_constraints + copy.deepcopy(C01_SUPPLEMENTAL_TRACEABILITY),
}
write("semantic-constraints-v1.json", traceability)
print("Refreshed Provider, Scenario, Experience, execution, Recording and reconciliation digests.")
