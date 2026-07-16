#!/usr/bin/env python3
from __future__ import annotations

import copy
import hashlib
import json
import math
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import rfc8785
import yaml
from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_DIRS = [ROOT / "contracts" / "schemas", ROOT / "examples" / "schemas"]
FORMAT_CHECKER = FormatChecker()
SAFE_INTEGER_MAX = 9_007_199_254_740_991

schemas: dict[str, dict[str, Any]] = {}
schema_by_id: dict[str, dict[str, Any]] = {}
registry = Registry()


def reject_constant(value: str) -> None:
    raise ValueError(f"Non-I-JSON constant: {value}")


def reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate object member: {key}")
        result[key] = value
    return result


def reject_unsafe_values(value: Any, path: str = "$") -> None:
    if value is None or isinstance(value, (bool, str)):
        if isinstance(value, str):
            value.encode("utf-8", errors="strict")
            for character in value:
                code = ord(character)
                if 0xD800 <= code <= 0xDFFF:
                    raise ValueError(f"Lone Unicode surrogate at {path}")
        return
    if isinstance(value, int):
        if abs(value) > SAFE_INTEGER_MAX:
            raise ValueError(
                f"Integer outside interoperable IEEE-754 safe range at {path}; "
                "encode it as a string"
            )
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError(f"Non-finite number at {path}")
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            reject_unsafe_values(item, f"{path}[{index}]")
        return
    if isinstance(value, dict):
        for key, item in value.items():
            reject_unsafe_values(key, f"{path}.<key>")
            reject_unsafe_values(item, f"{path}.{key}")
        return
    raise TypeError(f"Unsupported JSON value at {path}: {type(value)!r}")


def strict_json_loads(raw: str) -> Any:
    value = json.loads(
        raw,
        parse_constant=reject_constant,
        object_pairs_hook=reject_duplicate_pairs,
    )
    reject_unsafe_values(value)
    # The JCS implementation is the final authoritative domain check.
    rfc8785.dumps(value)
    return value


def load_data(path: Path) -> Any:
    if path.suffix == ".json":
        return strict_json_loads(path.read_text(encoding="utf-8"))
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    reject_unsafe_values(value)
    rfc8785.dumps(value)
    return value


def canonical_bytes(value: Any) -> bytes:
    reject_unsafe_values(value)
    return rfc8785.dumps(value)


def canonical_digest(value: Any) -> str:
    return "sha256:" + hashlib.sha256(canonical_bytes(value)).hexdigest()


for directory in SCHEMA_DIRS:
    for path in sorted(directory.glob("*.json")):
        schema = strict_json_loads(path.read_text(encoding="utf-8"))
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
        walk_refs(strict_json_loads(path.read_text(encoding="utf-8")), path)


def validator_for(schema_name: str) -> Draft202012Validator:
    return Draft202012Validator(
        schemas[schema_name],
        registry=registry,
        format_checker=FORMAT_CHECKER,
    )


def validate(schema_name: str, relative_path: str) -> None:
    path = ROOT / relative_path
    errors = sorted(
        validator_for(schema_name).iter_errors(load_data(path)),
        key=lambda error: list(error.path),
    )
    if errors:
        raise AssertionError(
            "\n".join(f"{relative_path}: {error.message}" for error in errors)
        )


def walk_schema_references(value: Any, source: Path) -> None:
    if isinstance(value, dict):
        if {"uri", "digest", "dialect"}.issubset(value.keys()):
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
    ("sandbox-desired-state-request.schema.json", "examples/contracts/sandbox-desired-state-request.json"),
    ("sandbox-lease-request.schema.json", "examples/contracts/sandbox-lease-request.json"),
    ("sandbox-exec-request.schema.json", "examples/contracts/sandbox-exec-request.json"),
    ("sandbox-cancel-exec-request.schema.json", "examples/contracts/sandbox-cancel-exec-request.json"),
    ("sandbox-runtime-session-open-request.schema.json", "examples/contracts/sandbox-runtime-session-open-request.json"),
    ("sandbox-snapshot-request.schema.json", "examples/contracts/sandbox-snapshot-request.json"),
    ("sandbox-restore-request.schema.json", "examples/contracts/sandbox-restore-request.json"),
    ("sandbox-terminate-request.schema.json", "examples/contracts/sandbox-terminate-request.json"),
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
    ("run-manifest-v2.schema.json", "contracts/tests/invalid/run-manifest-empty-execution.json"),
    ("plugin-invocation-status.schema.json", "contracts/tests/invalid/plugin-status-succeeded-with-error.json"),
    ("sandbox-cancel-exec-request.schema.json", "contracts/tests/invalid/sandbox-cancel-missing-mutation-envelope.json"),
]

for schema_name, example in invalid_cases:
    path = ROOT / example
    if not list(validator_for(schema_name).iter_errors(load_data(path))):
        raise AssertionError(f"Expected invalid fixture to fail: {example}")

for path in sorted((ROOT / "contracts/tests/invalid-json").glob("*.json")):
    try:
        strict_json_loads(path.read_text(encoding="utf-8"))
    except (ValueError, TypeError, UnicodeError, rfc8785.CanonicalizationError):
        continue
    raise AssertionError(f"Expected invalid I-JSON document to fail: {path}")

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
work_for_digest = copy.deepcopy(work)
work_for_digest.pop("execution_grant", None)
assert grant["request_digest"] == canonical_digest(work_for_digest)
assert grant["scenario_version"] == work["work"]["scenario_version"]
assert grant["scenario_definition_digest"] == work["work"]["scenario_definition_digest"]
assert grant["idempotency_key_digest"] == (
    "sha256:" + hashlib.sha256(b"work-order-example-0001").hexdigest()
)

run_manifest = load_data(ROOT / "examples/contracts/run-manifest-v2.json")
manifest_without_digest = copy.deepcopy(run_manifest)
manifest_digest = manifest_without_digest.pop("run_manifest_digest")
assert manifest_digest == canonical_digest(manifest_without_digest)
assert run_manifest["capability_resolutions"]
assert run_manifest["agent_runtime"]["provider_revision_id"]
assert run_manifest["agent_runtime"]["governed_conformance_report_digest"]
assert run_manifest["sandboxes"]
assert run_manifest["primary_sandbox_slot_key"] in {item["sandbox_slot_key"] for item in run_manifest["sandboxes"]}

provider_revision = load_data(ROOT / "examples/contracts/sandbox-provider-revision.json")
assert provider_revision["certification_status"] == "certified"
assert provider_revision["conformance"]
assert all(item["status"] == "passed" for item in provider_revision["conformance"])

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


sandbox_bad_network = load_data(
    ROOT / "contracts/tests/invalid/sandbox-restricted-without-policy.json"
)
if not (
    sandbox_bad_network["network"]["mode"] == "restricted"
    and (
        not sandbox_bad_network["network"].get("policy_reference")
        or sandbox_bad_network["network"].get("egress_gateway_required") is not True
    )
):
    raise AssertionError("Expected restricted Sandbox without enforced policy to fail")

sandbox_bad_capability = load_data(
    ROOT / "contracts/tests/invalid/sandbox-unsupported-required-capability.json"
)
bad_required = {
    item["id"] for item in sandbox_bad_capability["required_capabilities"]
}
if bad_required.issubset(declared):
    raise AssertionError("Expected unsupported Sandbox capability to fail negotiation")

sandbox_create = load_data(ROOT / "examples/contracts/sandbox-create-request.json")
sandbox_payload = {
    key: value
    for key, value in sandbox_create.items()
    if key not in {
        "operation_id",
        "attempt_id",
        "fencing_token",
        "idempotency_key",
        "request_digest",
        "deadline_at",
    }
}
assert sandbox_create["request_digest"] == canonical_digest(sandbox_payload)


mutation_examples = [
    "sandbox-desired-state-request.json",
    "sandbox-lease-request.json",
    "sandbox-exec-request.json",
    "sandbox-cancel-exec-request.json",
    "sandbox-runtime-session-open-request.json",
    "sandbox-snapshot-request.json",
    "sandbox-restore-request.json",
    "sandbox-terminate-request.json",
]
for filename in mutation_examples:
    value = load_data(ROOT / "examples/contracts" / filename)
    payload = {
        key: item
        for key, item in value.items()
        if key not in {
            "operation_id",
            "attempt_id",
            "fencing_token",
            "idempotency_key",
            "request_digest",
            "deadline_at",
        }
    }
    assert value["request_digest"] == canonical_digest(payload), filename

mutation_schemas = [
    "sandbox-create-request.schema.json",
    "sandbox-desired-state-request.schema.json",
    "sandbox-lease-request.schema.json",
    "sandbox-exec-request.schema.json",
    "sandbox-cancel-exec-request.schema.json",
    "sandbox-runtime-session-open-request.schema.json",
    "sandbox-snapshot-request.schema.json",
    "sandbox-restore-request.schema.json",
    "sandbox-terminate-request.schema.json",
]
envelope_fields = {
    "operation_id",
    "attempt_id",
    "fencing_token",
    "idempotency_key",
    "request_digest",
    "deadline_at",
}
envelope = schemas["sandbox-mutation-envelope.schema.json"]
assert envelope_fields.issubset(set(envelope["required"]))
for schema_name in mutation_schemas:
    schema = schemas[schema_name]
    refs = [
        item.get("$ref")
        for item in schema.get("allOf", [])
        if isinstance(item, dict)
    ]
    assert "urn:agent-platform:sandbox-mutation-envelope:v1" in refs, schema_name

delivery = work["delivery"]
assert "callback_url" not in delivery
assert "callback_registration_id" in delivery
assert "delivery_target_id" in delivery

for plugin_path in [
    ROOT / "examples/plugins/html-anything/plugin.yaml",
    ROOT / "examples/plugins/html-to-pptx/plugin.yaml",
]:
    plugin = load_data(plugin_path)
    assert "trust" not in plugin.get("metadata", {})
    assert plugin["runtime"]["mode"] in {
        "service", "job", "sandbox_cli", "mcp", "remote_service"
    }

print(
    f"Validated {len(schema_by_id)} portable schemas, "
    f"{len(valid_cases)} valid fixtures, {len(invalid_cases)} schema-invalid fixtures, "
    f"3 semantic-invalid fixtures, and "
    f"{len(list((ROOT / 'contracts/tests/invalid-json').glob('*.json')))} "
    "strict I-JSON invalid fixtures."
)
