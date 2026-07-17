#!/usr/bin/env python3
from __future__ import annotations

import copy
import hashlib
import json
import math
from decimal import Decimal
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import rfc8785
import yaml
from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_DIRS = [ROOT / "contracts/schemas", ROOT / "examples/schemas"]
SAFE_INTEGER_MAX = 9_007_199_254_740_991
MAX_NUMBER_TOKEN_LENGTH = 1024
MAX_ABS_DECIMAL_EXPONENT = 400


def enforce_number_resource_limits(token: str) -> None:
    if len(token) > MAX_NUMBER_TOKEN_LENGTH:
        raise ValueError("JSON number token exceeds admission resource limit")
    exponent = int(token.lower().partition("e")[2] or "0")
    if abs(exponent) > MAX_ABS_DECIMAL_EXPONENT:
        raise ValueError("JSON number exponent exceeds admission resource limit")


def duplicate_guard(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate object member: {key}")
        result[key] = value
    return result


def strict_values(value: Any, path: str = "$") -> None:
    if value is None or isinstance(value, bool):
        return
    if isinstance(value, str):
        value.encode("utf-8", errors="strict")
        if any(0xD800 <= ord(char) <= 0xDFFF for char in value):
            raise ValueError(f"Lone surrogate at {path}")
        return
    if isinstance(value, int):
        if abs(value) > SAFE_INTEGER_MAX:
            raise ValueError(f"Unsafe integer at {path}")
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError(f"Non-finite number at {path}")
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            strict_values(item, f"{path}[{index}]")
        return
    if isinstance(value, dict):
        for key, item in value.items():
            strict_values(key, f"{path}.<key>")
            strict_values(item, f"{path}.{key}")
        return
    raise TypeError(f"Unsupported JSON value: {type(value)!r}")


def strict_loads(raw: str) -> Any:
    def strict_int(token: str) -> int:
        enforce_number_resource_limits(token)
        value = int(token)
        if abs(value) > SAFE_INTEGER_MAX:
            raise ValueError("Unsafe integer")
        return value

    def strict_float(token: str) -> float:
        enforce_number_resource_limits(token)
        exact = Decimal(token)
        if exact == exact.to_integral_value() and abs(exact) > SAFE_INTEGER_MAX:
            raise ValueError("Unsafe mathematical integer")
        return float(token)

    value = json.loads(
        raw,
        parse_int=strict_int,
        parse_float=strict_float,
        parse_constant=lambda token: (_ for _ in ()).throw(ValueError(token)),
        object_pairs_hook=duplicate_guard,
    )
    strict_values(value)
    rfc8785.dumps(value)
    return value


def load(path: Path) -> Any:
    value = strict_loads(path.read_text(encoding="utf-8")) if path.suffix == ".json" else yaml.safe_load(path.read_text(encoding="utf-8"))
    strict_values(value)
    rfc8785.dumps(value)
    return value


def digest(value: Any) -> str:
    return "sha256:" + hashlib.sha256(rfc8785.dumps(value)).hexdigest()


schemas: dict[str, dict[str, Any]] = {}
by_id: dict[str, dict[str, Any]] = {}
registry = Registry()
for directory in SCHEMA_DIRS:
    for path in sorted(directory.glob("*.json")):
        schema = strict_loads(path.read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
        schema_id = schema.get("$id")
        if not isinstance(schema_id, str) or not urlparse(schema_id).scheme:
            raise AssertionError(f"Schema requires an absolute $id: {path}")
        if schema_id in by_id:
            raise AssertionError(f"Duplicate schema $id: {schema_id}")
        schemas[path.name] = schema
        by_id[schema_id] = schema
        registry = registry.with_resource(schema_id, Resource.from_contents(schema))


def walk_refs(value: Any, source: Path) -> None:
    if isinstance(value, dict):
        ref = value.get("$ref")
        if isinstance(ref, str):
            parsed = urlparse(ref)
            if not parsed.scheme and not ref.startswith("#"):
                raise AssertionError(f"Relative $ref forbidden: {source}: {ref}")
            base = ref.split("#", 1)[0]
            if parsed.scheme and base and base not in by_id:
                raise AssertionError(f"Unregistered $ref: {source}: {ref}")
        for child in value.values():
            walk_refs(child, source)
    elif isinstance(value, list):
        for child in value:
            walk_refs(child, source)


for directory in SCHEMA_DIRS:
    for path in sorted(directory.glob("*.json")):
        walk_refs(load(path), path)


def validate(schema_name: str, relative: str, expected_valid: bool) -> None:
    validator = Draft202012Validator(schemas[schema_name], registry=registry, format_checker=FormatChecker())
    errors = list(validator.iter_errors(load(ROOT / relative)))
    if expected_valid and errors:
        raise AssertionError("\n".join(f"{relative}: {error.message}" for error in errors))
    if not expected_valid and not errors:
        raise AssertionError(f"Expected invalid fixture to fail: {relative}")


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
    ("provider-revision.schema.json", "examples/contracts/agent-runtime-provider-revision.json"),
    ("provider-revision.schema.json", "examples/contracts/tool-provider-revision.json"),
    ("provider-admission-decision.schema.json", "examples/contracts/provider-admission-decision.json"),
    ("provider-admission-decision.schema.json", "examples/contracts/agent-runtime-admission-decision.json"),
    ("provider-admission-decision.schema.json", "examples/contracts/tool-provider-admission-decision.json"),
    ("run-admission-context.schema.json", "examples/contracts/run-admission-context.json"),
    ("sandbox-operation-record.schema.json", "examples/contracts/sandbox-operation.json"),
    ("sandbox-operation-attempt.schema.json", "examples/contracts/sandbox-operation-attempt.json"),
    ("sandbox-reconciliation-case.schema.json", "examples/contracts/sandbox-reconciliation-case.json"),
    ("sandbox-manual-review-decision.schema.json", "examples/contracts/sandbox-manual-review-decision.json"),
    ("invocation-record.schema.json", "examples/contracts/invocation-record.json"),
    ("invocation-attempt.schema.json", "examples/contracts/invocation-attempt-1.json"),
    ("invocation-attempt.schema.json", "examples/contracts/invocation-attempt-2.json"),
    ("invocation-record.schema.json", "examples/contracts/invocation-attempt-sequence-record.json"),
    ("invocation-reconciliation-case.schema.json", "examples/contracts/invocation-reconciliation-case.json"),
    ("invocation-manual-review-decision.schema.json", "examples/contracts/invocation-manual-review-decision.json"),
    ("invocation-record.schema.json", "examples/contracts/invocation-non-idempotent-retry.json"),
    ("invocation-reconciliation-case.schema.json", "examples/contracts/invocation-retry-reconciliation-case.json"),
    ("invocation-manual-review-decision.schema.json", "examples/contracts/invocation-retry-manual-review-decision.json"),
    ("run-manifest-v2.schema.json", "examples/contracts/run-manifest-v2.json"),
]
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
for case in valid_cases:
    validate(*case, True)
for case in invalid_cases:
    validate(*case, False)

for path in sorted((ROOT / "contracts/tests/invalid-json").glob("*.json")):
    try:
        strict_loads(path.read_text(encoding="utf-8"))
    except (ValueError, TypeError, UnicodeError, rfc8785.CanonicalizationError):
        continue
    raise AssertionError(f"Expected Strict I-JSON failure: {path}")

for relative, field in [
    ("examples/contracts/sandbox-provider-revision.json", "provider_revision_digest"),
    ("examples/contracts/provider-admission-decision.json", "decision_digest"),
    ("examples/contracts/agent-runtime-provider-revision.json", "provider_revision_digest"),
    ("examples/contracts/agent-runtime-admission-decision.json", "decision_digest"),
    ("examples/contracts/tool-provider-revision.json", "provider_revision_digest"),
    ("examples/contracts/tool-provider-admission-decision.json", "decision_digest"),
    ("examples/contracts/sandbox-manual-review-decision.json", "decision_digest"),
    ("examples/contracts/sandbox-reconciliation-case.json", "case_digest"),
    ("examples/contracts/invocation-manual-review-decision.json", "decision_digest"),
    ("examples/contracts/invocation-reconciliation-case.json", "case_digest"),
    ("examples/contracts/invocation-retry-manual-review-decision.json", "decision_digest"),
    ("examples/contracts/invocation-retry-reconciliation-case.json", "case_digest"),
    ("examples/contracts/run-manifest-v2.json", "run_manifest_digest"),
]:
    value = load(ROOT / relative)
    expected = value[field]
    unsigned = copy.deepcopy(value)
    unsigned.pop(field)
    if digest(unsigned) != expected:
        raise AssertionError(f"Self-digest mismatch: {relative}")

print(f"Validated {len(by_id)} schemas, {len(valid_cases)} valid, {len(invalid_cases)} invalid, and Strict I-JSON fixtures.")
