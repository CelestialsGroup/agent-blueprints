#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import yaml
from jsonschema import Draft202012Validator
from referencing import Registry, Resource

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_DIRS = [ROOT / "contracts" / "schemas", ROOT / "examples" / "schemas"]

schemas: dict[str, dict[str, Any]] = {}
schema_by_id: dict[str, dict[str, Any]] = {}
registry = Registry()

for directory in SCHEMA_DIRS:
    for path in sorted(directory.glob("*.json")):
        schema = json.loads(path.read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
        schema_id = schema.get("$id")
        if not isinstance(schema_id, str) or not schema_id:
            raise AssertionError(f"Schema is missing absolute $id: {path}")
        if not urlparse(schema_id).scheme:
            raise AssertionError(f"Schema $id is not absolute: {path}: {schema_id}")
        if schema_id in schema_by_id:
            raise AssertionError(f"Duplicate schema $id: {schema_id}")
        schemas[path.name] = schema
        schema_by_id[schema_id] = schema
        registry = registry.with_resource(schema_id, Resource.from_contents(schema))


def walk_refs(value: Any, source: Path) -> None:
    if isinstance(value, dict):
        ref = value.get("$ref")
        if isinstance(ref, str):
            parsed = urlparse(ref)
            if not parsed.scheme and not ref.startswith("#"):
                raise AssertionError(f"Relative $ref is forbidden: {source}: {ref}")
            base = ref.split("#", 1)[0]
            if parsed.scheme and base and base not in schema_by_id:
                raise AssertionError(f"Unregistered absolute $ref: {source}: {ref}")
        for child in value.values():
            walk_refs(child, source)
    elif isinstance(value, list):
        for child in value:
            walk_refs(child, source)


for directory in SCHEMA_DIRS:
    for path in sorted(directory.glob("*.json")):
        walk_refs(json.loads(path.read_text(encoding="utf-8")), path)


def load_data(path: Path) -> Any:
    if path.suffix == ".json":
        return json.loads(path.read_text(encoding="utf-8"))
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def validate(schema_name: str, relative_path: str) -> None:
    path = ROOT / relative_path
    validator = Draft202012Validator(schemas[schema_name], registry=registry)
    errors = sorted(validator.iter_errors(load_data(path)), key=lambda e: list(e.path))
    if errors:
        raise AssertionError("\n".join(f"{relative_path}: {error.message}" for error in errors))


def canonical_digest(schema: dict[str, Any]) -> str:
    raw = json.dumps(schema, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def walk_schema_references(value: Any, source: Path) -> None:
    if isinstance(value, dict):
        if set(["uri", "digest", "dialect"]).issubset(value.keys()):
            uri = value["uri"]
            if uri not in schema_by_id:
                raise AssertionError(f"Unknown SchemaReference URI: {source}: {uri}")
            expected = canonical_digest(schema_by_id[uri])
            if value["digest"] != expected:
                raise AssertionError(
                    f"SchemaReference digest mismatch: {source}: {uri}: "
                    f"expected {expected}, got {value['digest']}"
                )
            if value["dialect"] != "https://json-schema.org/draft/2020-12/schema":
                raise AssertionError(f"Unsupported SchemaReference dialect: {source}")
        for child in value.values():
            walk_schema_references(child, source)
    elif isinstance(value, list):
        for child in value:
            walk_schema_references(child, source)


valid_cases = [
    ("work-order-request.schema.json", "examples/contracts/work-order.json"),
    ("execution-grant-jws-header.schema.json", "examples/contracts/execution-grant-header.json"),
    ("execution-grant-claims.schema.json", "examples/contracts/execution-grant-claims.json"),
    ("canonical-event-v2.schema.json", "examples/contracts/canonical-event-v2.json"),
    ("event-type-definition.schema.json", "examples/contracts/event-type-artifact-version-created.json"),
    ("capability-definition.schema.json", "examples/capabilities/html.generate.yaml"),
    ("capability-definition.schema.json", "examples/capabilities/converter.html-to-pptx.yaml"),
    ("scenario-definition.schema.json", "examples/scenarios/html-generation.yaml"),
    ("plugin-manifest-v2.schema.json", "examples/plugins/html-anything/plugin.yaml"),
    ("plugin-manifest-v2.schema.json", "examples/plugins/html-to-pptx/plugin.yaml"),
    ("plugin-invocation-request.schema.json", "examples/contracts/plugin-invocation-request.json"),
    ("plugin-invocation-result.schema.json", "examples/contracts/plugin-invocation-result.json"),
    ("work-session-request.schema.json", "examples/contracts/work-session-request.json"),
    ("sandbox-capabilities.schema.json", "examples/contracts/sandbox-capabilities.json"),
    ("sandbox-spec.schema.json", "examples/contracts/sandbox-spec.json"),
    ("sandbox-create-request.schema.json", "examples/contracts/sandbox-create-request.json"),
    ("sandbox-conformance-report.schema.json", "examples/contracts/sandbox-conformance-report.json"),
    ("provider-revision.schema.json", "examples/contracts/sandbox-provider-revision.json"),
    ("run-manifest-v2.schema.json", "examples/contracts/run-manifest-v2.json"),
]

for schema_name, example in valid_cases:
    validate(schema_name, example)
    walk_schema_references(load_data(ROOT / example), ROOT / example)

invalid_cases = [
    ("plugin-manifest-v2.schema.json", "contracts/tests/invalid/plugin-self-declared-trust.json"),
    ("canonical-event-v2.schema.json", "contracts/tests/invalid/event-missing-work-sequence.json"),
    ("execution-grant-claims.schema.json", "contracts/tests/invalid/grant-not-single-use.json"),
    ("work-order-request.schema.json", "contracts/tests/invalid/work-order-arbitrary-callback-url.json"),
    ("plugin-invocation-result.schema.json", "contracts/tests/invalid/plugin-result-missing-fencing.json"),
    ("work-session-request.schema.json", "contracts/tests/invalid/work-session-delegated-without-reason.json"),
    ("sandbox-spec.schema.json", "contracts/tests/invalid/sandbox-spec-missing-image-digest.json"),
    ("run-manifest-v2.schema.json", "contracts/tests/invalid/run-manifest-missing-sandbox-revision.json"),
]

for schema_name, example in invalid_cases:
    path = ROOT / example
    validator = Draft202012Validator(schemas[schema_name], registry=registry)
    if not list(validator.iter_errors(load_data(path))):
        raise AssertionError(f"Expected invalid fixture to fail: {example}")

semantic_invalid = ROOT / "contracts/tests/invalid/capability-wrong-schema-digest.yaml"
try:
    walk_schema_references(load_data(semantic_invalid), semantic_invalid)
except AssertionError:
    pass
else:
    raise AssertionError("Expected wrong SchemaReference digest to fail")

grant = load_data(ROOT / "examples/contracts/execution-grant-claims.json")
assert grant["nbf"] <= grant["iat"] + 30
assert grant["iat"] < grant["exp"]
assert grant["exp"] - grant["iat"] <= 300
assert grant["usage"] == "single"

work = load_data(ROOT / "examples/contracts/work-order.json")
work_for_digest = dict(work)
work_for_digest.pop("execution_grant", None)
work_digest = "sha256:" + hashlib.sha256(
    json.dumps(work_for_digest, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
).hexdigest()
assert grant["request_digest"] == work_digest
assert grant["scenario_version"] == work["work"]["scenario_version"]
assert grant["scenario_definition_digest"] == work["work"]["scenario_definition_digest"]
assert grant["idempotency_key_digest"] == "sha256:" + hashlib.sha256(b"work-order-example-0001").hexdigest()


delivery = work["delivery"]
assert "callback_url" not in delivery
assert "callback_registration_id" in delivery
assert "delivery_target_id" in delivery

sandbox_spec = load_data(ROOT / "examples/contracts/sandbox-spec.json")
assert sandbox_spec["image"]["digest"].startswith("sha256:")
assert sandbox_spec["network"]["mode"] != "restricted" or (
    sandbox_spec["network"]["policy_reference"]
    and sandbox_spec["network"]["egress_gateway_required"] is True
)
sandbox_caps = load_data(ROOT / "examples/contracts/sandbox-capabilities.json")
declared = {item["id"] for item in sandbox_caps["capabilities"]}
required = {item["id"] for item in sandbox_spec["required_capabilities"]}
assert required.issubset(declared)

sandbox_bad_network = load_data(ROOT / "contracts/tests/invalid/sandbox-restricted-without-policy.json")
if (
    sandbox_bad_network["network"]["mode"] == "restricted"
    and (
        not sandbox_bad_network["network"].get("policy_reference")
        or sandbox_bad_network["network"].get("egress_gateway_required") is not True
    )
):
    pass
else:
    raise AssertionError("Expected restricted Sandbox without enforced policy to fail")

sandbox_bad_cap = load_data(ROOT / "contracts/tests/invalid/sandbox-unsupported-required-capability.json")
bad_required = {item["id"] for item in sandbox_bad_cap["required_capabilities"]}
if bad_required.issubset(declared):
    raise AssertionError("Expected unsupported Sandbox capability to fail negotiation")

for plugin_path in [
    ROOT / "examples/plugins/html-anything/plugin.yaml",
    ROOT / "examples/plugins/html-to-pptx/plugin.yaml",
]:
    plugin = load_data(plugin_path)
    assert "trust" not in plugin.get("metadata", {})
    assert plugin["runtime"]["mode"] in {"service", "job", "sandbox_cli", "mcp", "remote_service"}

print(
    f"Validated {len(schema_by_id)} portable schemas, "
    f"{len(valid_cases)} valid fixtures, and {len(invalid_cases)} invalid fixtures."
)
