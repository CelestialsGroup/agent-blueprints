#!/usr/bin/env python3
"""Conservative breaking-change gate against a protected frozen baseline."""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
HTTP_METHODS = {"get", "put", "post", "delete", "options", "head", "patch", "trace"}
MINIMUM_KEYWORDS = ("minLength", "minItems", "minProperties", "minimum", "exclusiveMinimum", "minContains")
MAXIMUM_KEYWORDS = ("maxLength", "maxItems", "maxProperties", "maximum", "exclusiveMaximum", "maxContains")


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def schema_breaks(old: Any, new: Any, path: str = "$") -> list[str]:
    breaks: list[str] = []
    if not isinstance(old, dict) or not isinstance(new, dict):
        return breaks
    old_required, new_required = set(old.get("required", [])), set(new.get("required", []))
    for name in sorted(new_required - old_required):
        breaks.append(f"{path}: newly required property {name!r}")
    old_properties, new_properties = old.get("properties", {}), new.get("properties", {})
    if isinstance(old_properties, dict) and isinstance(new_properties, dict):
        for name in sorted(set(old_properties) - set(new_properties)):
            breaks.append(f"{path}: removed property {name!r}")
        for name in sorted(set(old_properties) & set(new_properties)):
            breaks.extend(schema_breaks(old_properties[name], new_properties[name], f"{path}.{name}"))
    old_types, new_types = old.get("type"), new.get("type")
    if old_types is not None and new_types is not None:
        old_set = {old_types} if isinstance(old_types, str) else set(old_types)
        new_set = {new_types} if isinstance(new_types, str) else set(new_types)
        if not old_set.issubset(new_set):
            breaks.append(f"{path}: type narrowed from {sorted(old_set)} to {sorted(new_set)}")
    if "enum" in old and "enum" in new:
        old_enum = {json.dumps(item, sort_keys=True) for item in old["enum"]}
        new_enum = {json.dumps(item, sort_keys=True) for item in new["enum"]}
        if not old_enum.issubset(new_enum):
            breaks.append(f"{path}: enum values removed")
    if "const" in old and old.get("const") != new.get("const"):
        breaks.append(f"{path}: const changed")
    for keyword in MINIMUM_KEYWORDS:
        old_value, new_value = old.get(keyword), new.get(keyword)
        if _is_number(new_value) and (not _is_number(old_value) or new_value > old_value):
            breaks.append(f"{path}: {keyword} added or increased")
    for keyword in MAXIMUM_KEYWORDS:
        old_value, new_value = old.get(keyword), new.get(keyword)
        if _is_number(new_value) and (not _is_number(old_value) or new_value < old_value):
            breaks.append(f"{path}: {keyword} added or decreased")
    for keyword in ("pattern", "format", "multipleOf"):
        if keyword in new and new.get(keyword) != old.get(keyword):
            breaks.append(f"{path}: {keyword} added or changed")
    if new.get("uniqueItems") is True and old.get("uniqueItems") is not True:
        breaks.append(f"{path}: uniqueItems changed to true")
    old_additional, new_additional = old.get("additionalProperties", True), new.get("additionalProperties", True)
    if old_additional is not False and new_additional is False:
        breaks.append(f"{path}: additionalProperties changed to false")
    elif isinstance(new_additional, dict):
        if old_additional is True:
            breaks.append(f"{path}: additionalProperties changed from unrestricted to a schema")
        elif isinstance(old_additional, dict):
            breaks.extend(schema_breaks(old_additional, new_additional, f"{path}.additionalProperties"))
    if isinstance(old.get("items"), dict) and isinstance(new.get("items"), dict):
        breaks.extend(schema_breaks(old["items"], new["items"], f"{path}.items"))
    for keyword in ("allOf", "anyOf", "oneOf"):
        old_items, new_items = old.get(keyword), new.get(keyword)
        if isinstance(old_items, list) and isinstance(new_items, list):
            if keyword == "allOf" and len(new_items) > len(old_items):
                breaks.append(f"{path}: allOf constraints added")
            for index in range(min(len(old_items), len(new_items))):
                breaks.extend(schema_breaks(old_items[index], new_items[index], f"{path}.{keyword}[{index}]"))
    return breaks


def _parameters(path_item: dict[str, Any], operation: dict[str, Any]) -> dict[tuple[str, str], dict[str, Any]]:
    result: dict[tuple[str, str], dict[str, Any]] = {}
    for parameter in [*path_item.get("parameters", []), *operation.get("parameters", [])]:
        if isinstance(parameter, dict) and "$ref" not in parameter:
            result[(str(parameter.get("in")), str(parameter.get("name")))] = parameter
    return result


def openapi_breaks(old: dict[str, Any], new: dict[str, Any], path: str) -> list[str]:
    breaks: list[str] = []
    old_paths, new_paths = old.get("paths", {}), new.get("paths", {})
    for endpoint in sorted(set(old_paths) - set(new_paths)):
        breaks.append(f"{path}: removed endpoint {endpoint}")
    for endpoint in sorted(set(old_paths) & set(new_paths)):
        old_item, new_item = old_paths[endpoint], new_paths[endpoint]
        old_methods, new_methods = set(old_item) & HTTP_METHODS, set(new_item) & HTTP_METHODS
        for method in sorted(old_methods - new_methods):
            breaks.append(f"{path}: removed operation {method.upper()} {endpoint}")
        for method in sorted(old_methods & new_methods):
            label = f"{method.upper()} {endpoint}"
            old_op, new_op = old_item[method], new_item[method]
            old_params, new_params = _parameters(old_item, old_op), _parameters(new_item, new_op)
            for key, parameter in new_params.items():
                previous = old_params.get(key)
                if parameter.get("required") is True and (previous is None or previous.get("required") is not True):
                    breaks.append(f"{path}: {label} newly requires parameter {key}")
            old_responses, new_responses = old_op.get("responses", {}), new_op.get("responses", {})
            for status in sorted(set(old_responses) - set(new_responses)):
                breaks.append(f"{path}: {label} removed response {status}")
            if new_op.get("requestBody", {}).get("required") is True and old_op.get("requestBody", {}).get("required") is not True:
                breaks.append(f"{path}: {label} request body became required")
            if not old_op.get("security") and new_op.get("security"):
                breaks.append(f"{path}: {label} added a security requirement")
    return breaks


def transition_breaks(old: dict[str, Any], new: dict[str, Any], path: str) -> list[str]:
    key = lambda item: (item["from"], item["event"], item["to"])
    removed = {key(item) for item in old.get("transitions", [])} - {key(item) for item in new.get("transitions", [])}
    return [f"{path}: removed transition {item}" for item in sorted(removed)]


def self_test() -> None:
    for old, new in [
        ({"type": "string"}, {"type": "string", "minLength": 1}),
        ({"type": "object"}, {"type": "object", "additionalProperties": False}),
        ({"type": "object", "properties": {"x": {"type": ["string", "null"]}}},
         {"type": "object", "required": ["x"], "properties": {"x": {"type": "string"}}}),
    ]:
        assert schema_breaks(old, new)
    old_api = {"paths": {"/v1/x": {"get": {"parameters": [], "responses": {"200": {}, "404": {}}}}}}
    new_api = {"paths": {"/v1/x": {"get": {"parameters": [{"in": "query", "name": "q", "required": True}], "responses": {"200": {}}}}}}
    findings = openapi_breaks(old_api, new_api, "api.yaml")
    assert any("requires parameter" in item for item in findings)
    assert any("removed response 404" in item for item in findings)
    assert transition_breaks({"transitions": [{"from": "a", "event": "go", "to": "b"}]}, {"transitions": []}, "machine.json")


def git_text(ref: str, relative: str, prefix: str) -> str | None:
    target = f"{prefix}/{relative}" if prefix else relative
    result = subprocess.run(["git", "show", f"{ref}:{target}"], cwd=ROOT, text=True,
                            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, check=False)
    return result.stdout if result.returncode == 0 else None


def baseline_resources(ref: str, prefix: str, manifest: dict[str, Any]) -> list[dict[str, Any]]:
    embedded = manifest.get("resources")
    if embedded:
        return embedded
    roots = ["contracts/schemas", "examples/schemas", "contracts/openapi", "contracts/state-machines"]
    targets = [f"{prefix}/{item}" if prefix else item for item in roots]
    listing = subprocess.check_output(
        ["git", "ls-tree", "-r", "--name-only", ref, "--", *targets], cwd=ROOT, text=True
    ).splitlines()
    resources: list[dict[str, Any]] = []
    for git_path in listing:
        relative = git_path[len(prefix) + 1:] if prefix else git_path
        if relative.endswith(".schema.json"):
            value = json.loads(git_text(ref, relative, prefix) or "{}")
            resources.append({"kind": "json-schema", "id": value.get("$id"), "path": relative})
        elif relative.startswith("contracts/openapi/") and relative.endswith(".yaml"):
            resources.append({"kind": "openapi", "id": relative, "path": relative})
        elif relative.startswith("contracts/state-machines/") and relative.endswith(".json"):
            resources.append({"kind": "state-machine", "id": relative, "path": relative})
    return resources


def compare(ref: str) -> list[str]:
    git_root = Path(subprocess.check_output(["git", "rev-parse", "--show-toplevel"], cwd=ROOT, text=True).strip())
    prefix = ROOT.relative_to(git_root).as_posix()
    schema_paths = [*(ROOT / "contracts/schemas").glob("*.json"), *(ROOT / "examples/schemas").glob("*.json")]
    current_schemas = {json.loads(item.read_text())["$id"]: item for item in schema_paths}
    old_manifest_text = None
    for version in ("v0.8.3", "v0.8.2", "v0.8.1"):
        old_manifest_text = git_text(ref, f"contracts/compatibility/{version}-contract-manifest.json", prefix)
        if old_manifest_text:
            break
    if old_manifest_text is None:
        raise RuntimeError(f"No admitted contract manifest exists at protected baseline {ref}")
    breaks: list[str] = []
    old_manifest = json.loads(old_manifest_text)
    for resource in baseline_resources(ref, prefix, old_manifest):
        relative = resource["path"]
        old_text = git_text(ref, relative, prefix)
        if old_text is None:
            continue
        if resource["kind"] == "json-schema":
            current = current_schemas.get(resource["id"])
            if current is None:
                breaks.append(f"{relative}: removed schema {resource['id']}")
            else:
                breaks.extend(schema_breaks(json.loads(old_text), json.loads(current.read_text()), relative))
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
ref = os.environ.get("CONTRACT_FROZEN_BASE_REF")
if not ref:
    in_ci = os.environ.get("CI", "").lower() == "true"
    first_baseline_allowed = os.environ.get("CONTRACT_ALLOW_NO_FROZEN_BASELINE", "").lower() == "true"
    if in_ci and not first_baseline_allowed:
        raise SystemExit("Contract compatibility is fail-closed in CI: configure protected AGENT_PLATFORM_FROZEN_CONTRACT_REF, or explicitly set protected AGENT_PLATFORM_ALLOW_NO_FROZEN_BASELINE=true before the first frozen baseline exists.")
    reason = "protected first-baseline exception is active" if in_ci else "local run has no explicit CONTRACT_FROZEN_BASE_REF"
    print(f"Contract compatibility: N/A — {reason}; comparator self-tests passed.")
    raise SystemExit(0)
breaking = compare(ref)
if breaking:
    raise SystemExit("Breaking contract changes detected:\n- " + "\n- ".join(breaking))
print(f"Contract compatibility passed against protected frozen baseline {ref}.")
