#!/usr/bin/env python3
"""Detect unsupported breaking changes against the latest frozen contract baseline."""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
POLICY = ROOT / "contracts/compatibility/baseline-policy.json"
HTTP_METHODS = {"get", "put", "post", "delete", "options", "head", "patch", "trace"}


def schema_breaks(old: Any, new: Any, path: str = "$") -> list[str]:
    breaks: list[str] = []
    if not isinstance(old, dict) or not isinstance(new, dict):
        return breaks
    old_required = set(old.get("required", []))
    new_required = set(new.get("required", []))
    for name in sorted(new_required - old_required):
        breaks.append(f"{path}: newly required property {name!r}")
    old_properties = old.get("properties", {})
    new_properties = new.get("properties", {})
    if isinstance(old_properties, dict) and isinstance(new_properties, dict):
        for name in sorted(set(old_properties) - set(new_properties)):
            breaks.append(f"{path}: removed property {name!r}")
        for name in sorted(set(old_properties) & set(new_properties)):
            breaks.extend(schema_breaks(old_properties[name], new_properties[name], f"{path}.{name}"))
    old_types = old.get("type")
    new_types = new.get("type")
    if old_types is not None and new_types is not None:
        old_set = {old_types} if isinstance(old_types, str) else set(old_types)
        new_set = {new_types} if isinstance(new_types, str) else set(new_types)
        if not old_set.issubset(new_set):
            breaks.append(f"{path}: type narrowed from {sorted(old_set)} to {sorted(new_set)}")
    if "enum" in old and "enum" in new:
        old_enum = {json.dumps(x, sort_keys=True) for x in old["enum"]}
        new_enum = {json.dumps(x, sort_keys=True) for x in new["enum"]}
        if not old_enum.issubset(new_enum):
            breaks.append(f"{path}: enum values removed")
    if "const" in old and old.get("const") != new.get("const"):
        breaks.append(f"{path}: const changed")
    for keyword in ("items", "additionalProperties"):
        if isinstance(old.get(keyword), dict) and isinstance(new.get(keyword), dict):
            breaks.extend(schema_breaks(old[keyword], new[keyword], f"{path}.{keyword}"))
    for keyword in ("allOf", "anyOf", "oneOf"):
        old_items, new_items = old.get(keyword), new.get(keyword)
        if isinstance(old_items, list) and isinstance(new_items, list):
            for index, old_item in enumerate(old_items[: len(new_items)]):
                breaks.extend(schema_breaks(old_item, new_items[index], f"{path}.{keyword}[{index}]"))
    return breaks


def openapi_breaks(old: dict[str, Any], new: dict[str, Any], path: str) -> list[str]:
    breaks: list[str] = []
    old_paths = old.get("paths", {})
    new_paths = new.get("paths", {})
    for endpoint in sorted(set(old_paths) - set(new_paths)):
        breaks.append(f"{path}: removed endpoint {endpoint}")
    for endpoint in sorted(set(old_paths) & set(new_paths)):
        old_methods = set(old_paths[endpoint]) & HTTP_METHODS
        new_methods = set(new_paths[endpoint]) & HTTP_METHODS
        for method in sorted(old_methods - new_methods):
            breaks.append(f"{path}: removed operation {method.upper()} {endpoint}")
    return breaks


def transition_breaks(old: dict[str, Any], new: dict[str, Any], path: str) -> list[str]:
    key = lambda item: (item["from"], item["event"], item["to"])
    old_transitions = {key(item) for item in old.get("transitions", [])}
    new_transitions = {key(item) for item in new.get("transitions", [])}
    return [f"{path}: removed transition {item}" for item in sorted(old_transitions - new_transitions)]


def self_test() -> None:
    assert schema_breaks(
        {"type": "object", "properties": {"x": {"type": ["string", "null"]}}},
        {"type": "object", "required": ["x"], "properties": {"x": {"type": "string"}}},
    )
    assert openapi_breaks(
        {"paths": {"/v1/x": {"get": {}}}}, {"paths": {}}, "api.yaml"
    )
    assert transition_breaks(
        {"transitions": [{"from": "a", "event": "go", "to": "b"}]},
        {"transitions": []},
        "machine.json",
    )


def git_text(ref: str, relative: str, prefix: str) -> str | None:
    target = f"{prefix}/{relative}" if prefix else relative
    result = subprocess.run(
        ["git", "show", f"{ref}:{target}"], cwd=ROOT, text=True,
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, check=False,
    )
    return result.stdout if result.returncode == 0 else None


def compare(ref: str) -> list[str]:
    git_root = Path(subprocess.check_output(["git", "rev-parse", "--show-toplevel"], cwd=ROOT, text=True).strip())
    prefix = ROOT.relative_to(git_root).as_posix()
    breaks: list[str] = []
    schema_paths = [
        *(ROOT / "contracts/schemas").glob("*.json"),
        *(ROOT / "examples/schemas").glob("*.json"),
    ]
    current_schemas = {json.loads(p.read_text())["$id"]: p for p in schema_paths}
    old_manifest_text = git_text(ref, "contracts/compatibility/v0.8.2-contract-manifest.json", prefix)
    if old_manifest_text is None:
        old_manifest_text = git_text(ref, "contracts/compatibility/v0.8.1-contract-manifest.json", prefix)
    if old_manifest_text is None:
        raise RuntimeError(f"No admitted contract manifest exists at {ref}")
    old_manifest = json.loads(old_manifest_text)
    resources = old_manifest.get("resources")
    if resources is None:
        roots = ["contracts/schemas", "contracts/openapi", "contracts/state-machines"]
        targets = [f"{prefix}/{item}" if prefix else item for item in roots]
        listing = subprocess.check_output(
            ["git", "ls-tree", "-r", "--name-only", ref, "--", *targets],
            cwd=ROOT,
            text=True,
        ).splitlines()
        resources = []
        for git_path in listing:
            relative = git_path[len(prefix) + 1 :] if prefix else git_path
            if relative.startswith("contracts/schemas/") and relative.endswith(".json"):
                old = json.loads(git_text(ref, relative, prefix) or "{}")
                resources.append({"kind": "json-schema", "id": old.get("$id"), "path": relative})
            elif relative.startswith("contracts/openapi/") and relative.endswith(".yaml"):
                resources.append({"kind": "openapi", "id": relative, "path": relative})
            elif relative.startswith("contracts/state-machines/") and relative.endswith(".json"):
                resources.append({"kind": "state-machine", "id": relative, "path": relative})
    for resource in resources:
        relative = resource["path"]
        old_text = git_text(ref, relative, prefix)
        if old_text is None:
            continue
        if resource["kind"] == "json-schema":
            schema_id = resource["id"]
            if schema_id not in current_schemas:
                breaks.append(f"{relative}: removed schema {schema_id}")
            else:
                breaks.extend(schema_breaks(json.loads(old_text), json.loads(current_schemas[schema_id].read_text()), relative))
        elif resource["kind"] == "openapi":
            current = ROOT / relative
            if not current.exists():
                breaks.append(f"{relative}: removed OpenAPI document")
            else:
                breaks.extend(openapi_breaks(yaml.safe_load(old_text), yaml.safe_load(current.read_text()), relative))
        elif resource["kind"] == "state-machine" or relative.startswith("contracts/state-machines/"):
            current = ROOT / relative
            if not current.exists():
                breaks.append(f"{relative}: removed state machine")
            else:
                breaks.extend(transition_breaks(json.loads(old_text), json.loads(current.read_text()), relative))
    return breaks


self_test()
policy = json.loads(POLICY.read_text(encoding="utf-8"))
ref = os.environ.get("CONTRACT_BASE_REF") or policy.get("frozen_git_ref")
if not ref:
    print("Contract compatibility: N/A — no publicly admitted frozen baseline exists; comparator self-tests passed.")
    raise SystemExit(0)
breaking = compare(ref)
if breaking:
    raise SystemExit("Breaking contract changes detected:\n- " + "\n- ".join(breaking))
print(f"Contract compatibility passed against frozen baseline {ref}.")
