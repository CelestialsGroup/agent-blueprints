#!/usr/bin/env python3
from __future__ import annotations

import copy
import base64
import hashlib
import json
import os
import posixpath
import shutil
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import rfc8785
import yaml
from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource

SCRIPT_ROOT = Path(__file__).resolve().parents[2]
CONTRACT_ROOT = Path(
    os.environ.get("AGENT_CONTRACT_ROOT", SCRIPT_ROOT.parent / "contract")
).resolve()
BLUEPRINT_ROOT = Path(
    os.environ.get("AGENT_BLUEPRINT_ROOT", SCRIPT_ROOT.parent / "blueprint")
).resolve()
BLUEPRINT_ARTIFACT_URN_PREFIX = "urn:agent-platform:blueprint:"
SEMANTIC_VALIDATOR_URN = "urn:agent-platform:contract-validation:semantic-validator"
BLUEPRINT_ARTIFACTS = {
    f"{BLUEPRINT_ARTIFACT_URN_PREFIX}docs/17_IDENTITY_AND_AUTHORIZATION": BLUEPRINT_ROOT / "docs/17_IDENTITY_AND_AUTHORIZATION.md",
    f"{BLUEPRINT_ARTIFACT_URN_PREFIX}docs/26_DATA_MODEL_INVARIANTS": BLUEPRINT_ROOT / "docs/26_DATA_MODEL_INVARIANTS.md",
    f"{BLUEPRINT_ARTIFACT_URN_PREFIX}tasks/PHASE0": BLUEPRINT_ROOT / "tasks/PHASE0.md",
}


def resolve_enforcement_artifact(artifact: str) -> Path:
    if artifact == SEMANTIC_VALIDATOR_URN:
        return Path(__file__).resolve()
    if artifact.startswith(BLUEPRINT_ARTIFACT_URN_PREFIX):
        try:
            return BLUEPRINT_ARTIFACTS[artifact]
        except KeyError as error:
            raise AssertionError(f"Unknown Blueprint responsibility URN: {artifact}") from error
    return CONTRACT_ROOT / artifact


AGENT_RUN_RESOURCE_LIMIT_NAMES = {
    "max_input_tokens",
    "max_output_tokens",
    "max_model_requests",
    "max_sandbox_seconds",
    "max_network_bytes",
    "max_storage_bytes",
    "max_artifact_count",
    "max_conversion_count",
}

SANDBOX_OPERATION_CONTRACTS = {
    "create": ("urn:agent-platform:sandbox-create-request:v1", "rfc8785-request-excluding-request-digest-v1"),
    "restore": ("urn:agent-platform:sandbox-restore-request:v1", "rfc8785-request-excluding-request-digest-v1"),
    "set_desired_state": ("urn:agent-platform:sandbox-desired-state-request:v1", "rfc8785-request-excluding-request-digest-v1"),
    "extend_lease": ("urn:agent-platform:sandbox-lease-request:v1", "rfc8785-request-excluding-request-digest-v1"),
    "exec": ("urn:agent-platform:sandbox-exec-request:v1", "rfc8785-request-excluding-request-digest-v1"),
    "cancel_exec": ("urn:agent-platform:sandbox-cancel-exec-request:v1", "rfc8785-request-excluding-request-digest-v1"),
    "open_runtime_session": ("urn:agent-platform:sandbox-runtime-session-open-request:v1", "rfc8785-request-excluding-request-digest-v1"),
    "snapshot": ("urn:agent-platform:sandbox-snapshot-request:v1", "rfc8785-request-excluding-request-digest-v1"),
    "terminate": ("urn:agent-platform:sandbox-terminate-request:v1", "rfc8785-request-excluding-request-digest-v1"),
    "read_sandbox": ("urn:agent-platform:sandbox-status-operation-descriptor:v1", "rfc8785-full-document-v1"),
    "read_operation": ("urn:agent-platform:sandbox-operation-read-operation-descriptor:v1", "rfc8785-full-document-v1"),
    "read_result": ("urn:agent-platform:sandbox-exec-result-operation-descriptor:v1", "rfc8785-full-document-v1"),
    "read_snapshot_manifest": ("urn:agent-platform:sandbox-snapshot-manifest-operation-descriptor:v1", "rfc8785-full-document-v1"),
    "read_events": ("urn:agent-platform:sandbox-event-read-operation-descriptor:v1", "rfc8785-full-document-v1"),
}
RUNTIME_OPERATION_CONTRACTS = {
    "start": ("urn:agent-platform:agent-runtime-start-request:v1", "rfc8785-request-excluding-request-digest-v1", "request_digest"),
    "submit_command": ("urn:agent-platform:agent-runtime-command:v1", "rfc8785-command-excluding-command-digest-v1", "command_digest"),
    "read_status": ("urn:agent-platform:agent-runtime-status-operation-descriptor:v1", "rfc8785-full-document-v1", None),
    "read_events": ("urn:agent-platform:agent-runtime-event-read-operation-descriptor:v1", "rfc8785-full-document-v1", None),
}
PLUGIN_OPERATION_CONTRACTS = {
    "invoke": ("urn:agent-platform:plugin-invocation-request:v1", "rfc8785-request-excluding-request-digest-v1"),
    "status": ("urn:agent-platform:plugin-status-operation-descriptor:v1", "rfc8785-full-document-v1"),
    "cancel": ("urn:agent-platform:plugin-cancellation-request:v1", "rfc8785-request-excluding-request-digest-v1"),
    "read_events": ("urn:agent-platform:plugin-event-read-operation-descriptor:v1", "rfc8785-full-document-v1"),
}


_C01_RUNTIME_READ_CHECK = "runtime_read.http_authority"
_C01_RUNTIME_READ_SCHEMA_CASES = {
    "urn:agent-platform:agent-runtime-read-bad-request-error:v1": [
        "status-read-invalid-request-400", "event-read-invalid-request-400",
    ],
    "urn:agent-platform:agent-runtime-read-throttled-error:v1": [
        "status-read-throttled-429", "event-read-throttled-429",
    ],
}
_C01_RUNTIME_SUITE_ACTIVE = "conformance/runtime/v1/suite.json"
_C01_RUNTIME_SUITE_SNAPSHOT = "conformance/runtime/v1/revisions/1.0.0/suite.json"
_C01_RUNTIME_OPENAPI_ACTIVE = "openapi/agent-runtime-provider-v1.yaml"
_C01_RUNTIME_OPENAPI_SNAPSHOT = "openapi/agent-runtime-provider-v1.0.0.snapshot.yaml"
_C01_HISTORICAL_OPENAPI_SHA256 = (
    "f75bd9484d9059435021f65147cab1a22b4cb0376ea47ce6e165fde0494f5811"
)


def _c01_jcs_digest(value: dict[str, Any], excluded: str | None = None) -> str:
    material = copy.deepcopy(value)
    if excluded is not None:
        material.pop(excluded, None)
    return "sha256:" + hashlib.sha256(rfc8785.dumps(material)).hexdigest()


def _c01_walk_dicts(value: Any):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _c01_walk_dicts(child)
    elif isinstance(value, list):
        for child in value:
            yield from _c01_walk_dicts(child)


def _c01_validate_runtime_registries(
    root: Path,
) -> tuple[dict[tuple[str, str, str], Path], dict[tuple[str, str, str], Path]]:
    active_suite = root / _C01_RUNTIME_SUITE_ACTIVE
    revisions = root / "conformance/runtime/v1/revisions"
    suite_paths = ([active_suite] if active_suite.is_file() else []) + (
        sorted(revisions.rglob("suite.json")) if revisions.is_dir() else []
    )
    suite_registry: dict[tuple[str, str, str], Path] = {}
    suite_digests: set[str] = set()
    for path in suite_paths:
        suite = json.loads(path.read_text(encoding="utf-8"))
        declared = suite.get("suite_digest")
        if declared != _c01_jcs_digest(suite, "suite_digest"):
            raise AssertionError(f"C01 Runtime Suite self-digest drift: {path.relative_to(root)}")
        key = (suite.get("suite_id"), suite.get("suite_version"), declared)
        if not all(isinstance(item, str) and item for item in key):
            raise AssertionError("C01 Runtime Suite tuple is incomplete")
        if key in suite_registry or declared in suite_digests:
            raise AssertionError("C01 Runtime Suite registry duplicate tuple/digest")
        suite_registry[key] = path
        suite_digests.add(declared)
    expected_suite_versions = {
        ("agent-runtime-provider", "1.0.0"),
        ("agent-runtime-provider", "1.0.1"),
    }
    if {(key[0], key[1]) for key in suite_registry} != expected_suite_versions:
        raise AssertionError("C01 Runtime Suite registry active/snapshot version set drift")
    expected_suite_paths = {
        (root / _C01_RUNTIME_SUITE_ACTIVE).resolve(),
        (root / _C01_RUNTIME_SUITE_SNAPSHOT).resolve(),
    }
    if {path.resolve() for path in suite_registry.values()} != expected_suite_paths:
        raise AssertionError("C01 Runtime Suite registry path set drift")

    openapi_root = root / "openapi"
    port_registry: dict[tuple[str, str, str], Path] = {}
    port_digests: set[str] = set()
    for path in sorted(openapi_root.glob("agent-runtime-provider*.yaml")):
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
        version = document.get("info", {}).get("version")
        if version not in {"1.0.0", "1.0.1"}:
            raise AssertionError("C01 Runtime Port registry contains an unsupported OpenAPI version")
        contract_digest = "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
        key = ("agent-runtime-provider", "v1", contract_digest)
        if key in port_registry or contract_digest in port_digests:
            raise AssertionError("C01 Runtime Port registry duplicate tuple/digest")
        port_registry[key] = path
        port_digests.add(contract_digest)
    expected_port_paths = {
        (root / _C01_RUNTIME_OPENAPI_ACTIVE).resolve(),
        (root / _C01_RUNTIME_OPENAPI_SNAPSHOT).resolve(),
    }
    if {path.resolve() for path in port_registry.values()} != expected_port_paths:
        raise AssertionError("C01 Runtime Port registry active/snapshot path set drift")
    snapshot_path = root / _C01_RUNTIME_OPENAPI_SNAPSHOT
    if hashlib.sha256(snapshot_path.read_bytes()).hexdigest() != _C01_HISTORICAL_OPENAPI_SHA256:
        raise AssertionError("C01 historical Runtime OpenAPI snapshot byte drift")
    if yaml.safe_load(snapshot_path.read_text(encoding="utf-8"))["info"]["version"] != "1.0.0":
        raise AssertionError("C01 historical Runtime OpenAPI version drift")
    if yaml.safe_load((root / _C01_RUNTIME_OPENAPI_ACTIVE).read_text(encoding="utf-8"))["info"]["version"] != "1.0.1":
        raise AssertionError("C01 active Runtime OpenAPI version drift")

    for path in sorted((root / "examples/contracts").glob("*.json")):
        document = json.loads(path.read_text(encoding="utf-8"))
        for item in _c01_walk_dicts(document):
            if item.get("suite_id") == "agent-runtime-provider" and {
                "suite_version", "suite_digest",
            } <= set(item):
                key = (item["suite_id"], item["suite_version"], item["suite_digest"])
                if key not in suite_registry:
                    raise AssertionError(f"C01 unresolved Runtime Suite tuple in {path.name}")
                if item["suite_version"] == "1.0.1" and item.get("result") in {"passed", "certified"}:
                    raise AssertionError("C01 active Runtime Suite must not be represented as passed/certified")
            if item.get("protocol") == "agent-runtime-provider" and {
                "protocol_version", "contract_digest",
            } <= set(item):
                key = (item["protocol"], item["protocol_version"], item["contract_digest"])
                if key not in port_registry:
                    raise AssertionError(f"C01 unresolved Runtime Port tuple in {path.name}")
    return suite_registry, port_registry


def _c01_runtime_read_operations(document: dict[str, Any]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for route, path_item in document.get("paths", {}).items():
        operation = path_item.get("get")
        if isinstance(operation, dict) and operation.get("operationId") in {
            "getAgentRuntimeRun", "readAgentRuntimeEvents",
        }:
            result[operation["operationId"]] = {"route": route, "operation": operation}
    if set(result) != {"getAgentRuntimeRun", "readAgentRuntimeEvents"}:
        raise AssertionError("C01 Runtime read operations are missing or duplicated")
    return result


def _c01_expected_http_authority(events: bool) -> dict[str, Any]:
    route = "/v1/runs/{runtime_run_id}/events" if events else "/v1/runs/{runtime_run_id}"
    query: dict[str, Any]
    if events:
        query = {
            "mode": "allowlist",
            "allowed-parameters": ["after_event_sequence", "limit"],
            "multiplicity": "at-most-once-each",
            "ordering": "any",
            "unknown-parameter": "reject-400",
            "repeated-parameter": "reject-400",
            "ambiguous-percent-encoding": "reject-400",
            "lexical-format": "canonical-unsigned-ascii-decimal",
            "lexical-pattern": "^(0|[1-9][0-9]*)$",
            "rejected-lexical-forms": [
                "sign", "leading-zero", "empty", "whitespace", "exponent", "fraction",
            ],
            "parameters": {
                "after_event_sequence": {
                    "omission-default": 0,
                    "explicit-default-equivalent": True,
                    "minimum": 0,
                    "maximum": 9_007_199_254_740_991,
                },
                "limit": {
                    "omission-default": 1000,
                    "explicit-default-equivalent": True,
                    "minimum": 1,
                    "maximum": 1000,
                },
            },
            "malformed-or-out-of-range": "reject-400",
            "valid-retention-expiry": "respond-410",
        }
    else:
        query = {
            "mode": "forbidden",
            "empty-marker": "reject-400",
            "unknown-parameter": "reject-400",
            "repeated-parameter": "reject-400",
        }
    return {
        "authority-version": "runtime-read-http-authority-v1",
        "operation-recognition": {
            "method": "GET",
            "path-shape": route,
            "match": "exact",
            "unknown-route": "c01-out-of-scope",
            "pre-operation-parser-failure": "c01-out-of-scope",
        },
        "runtime-run-id": {
            "segment-count": 1,
            "min-length": 1,
            "max-length": 200,
            "case-fold": "forbidden",
            "unicode-normalization": "forbidden",
            "slash-collapse": "forbidden",
            "dot-segment-processing": "forbidden",
            "encoded-path-separator-equivalence": "forbidden",
        },
        "query": query,
        "body": {
            "mode": "forbidden",
            "nonzero-content-length": "reject-400",
            "ambiguous-content-length": "reject-400",
            "transfer-encoding": "reject-400",
            "expect": "reject-400",
        },
        "descriptor-digest-mismatch": "reject-403",
    }


def _c01_expected_retry(events: bool) -> dict[str, Any]:
    return {
        "authority-version": "runtime-read-retry-authority-v1",
        "durable-caller-minimum-wait": "at-least-retry-after",
        "attempt": "fresh-authorized-read-attempt",
        "token": "fresh",
        "fencing": "non-stale",
        "descriptor-digest": "recompute-for-new-attempt-token-fencing",
        "logical-status-target": "not-applicable" if events else "unchanged",
        "event-cursor-limit": "unchanged" if events else "not-applicable",
        "event-cursor-advance-on-429": "forbidden" if events else "not-applicable",
        "adapter-auto-retry": "forbidden",
        "mutation-replay": "forbidden",
    }


def _c01_validate_openapi_and_schemas(root: Path) -> None:
    document = yaml.safe_load(
        (root / "openapi/agent-runtime-provider-v1.yaml").read_text(encoding="utf-8")
    )
    if document.get("info", {}).get("version") != "1.0.1":
        raise AssertionError("C01 Runtime OpenAPI version drift")
    operations = _c01_runtime_read_operations(document)
    admission = {
        "operation-recognition-required": True,
        "caller-token-descriptor-binding-required": True,
        "before-provider-state-read": True,
        "independent-of-run-existence": True,
        "listener-saturation-eligible": False,
    }
    for operation_id, events in (
        ("getAgentRuntimeRun", False), ("readAgentRuntimeEvents", True),
    ):
        operation = operations[operation_id]["operation"]
        expected_route = (
            "/v1/runs/{runtime_run_id}/events" if events
            else "/v1/runs/{runtime_run_id}"
        )
        if operations[operation_id]["route"] != expected_route:
            raise AssertionError(f"C01 Runtime read route drift: {operation_id}")
        if operation.get("x-runtime-read-http-authority") != _c01_expected_http_authority(events):
            raise AssertionError(f"C01 Runtime read HTTP authority drift: {operation_id}")
        expected_precedence = ["400", "401", "403", "429", "404"]
        if events:
            expected_precedence.append("410")
        expected_precedence.append("200")
        if operation.get("x-runtime-read-response-precedence") != expected_precedence:
            raise AssertionError(f"C01 Runtime read precedence drift: {operation_id}")
        if operation.get("x-runtime-read-admission") != admission:
            raise AssertionError(f"C01 Runtime read admission drift: {operation_id}")
        if operation.get("x-runtime-read-retry") != _c01_expected_retry(events):
            raise AssertionError(f"C01 Runtime read retry drift: {operation_id}")
        for status, response_name in (
            ("400", "RuntimeReadBadRequest"), ("429", "RuntimeReadTooManyRequests"),
        ):
            if operation.get("responses", {}).get(status) != {
                "$ref": f"#/components/responses/{response_name}"
            }:
                raise AssertionError(f"C01 Runtime read {status} response binding drift")

    responses = document["components"]["responses"]
    bad_request = responses["RuntimeReadBadRequest"]
    if bad_request.get("x-runtime-read-header-authority") != {
        "authority-version": "runtime-read-header-authority-v1",
        "retry-after": {"presence": "forbidden"},
    } or "headers" in bad_request:
        raise AssertionError("C01 400 Retry-After authority drift")
    throttled = responses["RuntimeReadTooManyRequests"]
    if throttled.get("x-runtime-read-header-authority") != {
        "authority-version": "runtime-read-header-authority-v1",
        "retry-after": {
            "presence": "required",
            "cardinality": "exactly-one",
            "wire-format": "canonical-decimal-integer-delta-seconds",
            "lexical-pattern": "^[1-9][0-9]*$",
            "rejected-lexical-forms": [
                "leading-zero", "plus-sign", "minus-sign", "whitespace", "decimal-point",
                "exponent", "non-ascii-digit", "empty",
            ],
            "minimum": 1,
            "invalid-response-on": [
                "missing", "repeated", "non-integer", "zero", "negative", "unsafe-parse",
            ],
            "invalid-response-retry": "forbidden",
        },
    }:
        raise AssertionError("C01 429 raw Retry-After authority drift")
    if throttled.get("headers", {}).get("Retry-After", {}).get("required") is not True:
        raise AssertionError("C01 429 Retry-After cardinality drift")
    if throttled["headers"]["Retry-After"].get("schema") != {
        "type": "integer", "minimum": 1,
    }:
        raise AssertionError("C01 429 parsed Retry-After boundary drift")

    schema_profiles = {
        "agent-runtime-read-bad-request-error.schema.json": (
            "urn:agent-platform:agent-runtime-read-bad-request-error:v1",
            "RUNTIME_READ_REQUEST_INVALID", False,
        ),
        "agent-runtime-read-throttled-error.schema.json": (
            "urn:agent-platform:agent-runtime-read-throttled-error:v1",
            "RUNTIME_READ_THROTTLED", True,
        ),
    }
    expected_refs = {
        "RuntimeReadBadRequest": "../schemas/agent-runtime-read-bad-request-error.schema.json",
        "RuntimeReadTooManyRequests": "../schemas/agent-runtime-read-throttled-error.schema.json",
    }
    for response_name, reference in expected_refs.items():
        if responses[response_name].get("content", {}).get("application/json", {}).get("schema") != {
            "$ref": reference
        }:
            raise AssertionError(f"C01 response body Schema binding drift: {response_name}")
    for filename, (schema_id, code, retryable) in schema_profiles.items():
        schema = json.loads((root / "schemas" / filename).read_text(encoding="utf-8"))
        if schema.get("$id") != schema_id or schema.get("unevaluatedProperties") is not False:
            raise AssertionError(f"C01 error Schema identity/closure drift: {filename}")
        if schema.get("allOf", [{}])[0] != {"$ref": "urn:agent-platform:standard-error:v1"}:
            raise AssertionError(f"C01 error Schema StandardError binding drift: {filename}")
        properties = schema.get("allOf", [{}, {}])[1].get("properties", {})
        if properties.get("code") != {"const": code} or properties.get("retryable") != {
            "const": retryable
        }:
            raise AssertionError(f"C01 error Schema code/retryable drift: {filename}")
        if properties.get("trace_id") != {"type": "string", "minLength": 1}:
            raise AssertionError(f"C01 error Schema trace drift: {filename}")
        if code == "RUNTIME_READ_REQUEST_INVALID":
            if properties.get("message") != {"const": "Runtime read request is invalid."}:
                raise AssertionError("C01 400 message drift")
        elif properties.get("message") != {
            "type": "string", "minLength": 1, "maxLength": 2000,
        }:
            raise AssertionError("C01 429 bounded message drift")


def _c01_stable_constraint_id(entry: dict[str, Any]) -> str:
    material = (
        f"{entry['schema_id']}\n{entry['constraint_index']}\n{entry['statement']}"
    ).encode()
    return "sem-" + hashlib.sha256(material).hexdigest()[:16]


def _c01_snapshot_protected_state() -> dict[str, str]:
    roots = [CONTRACT_ROOT, SCRIPT_ROOT / "evidence", SCRIPT_ROOT / "build"]
    snapshot: dict[str, str] = {}
    for root in roots:
        if not root.exists():
            continue
        for path in sorted(item for item in root.rglob("*") if item.is_file()):
            key = f"{root}:{path.relative_to(root).as_posix()}"
            snapshot[key] = hashlib.sha256(path.read_bytes()).hexdigest()
    return snapshot


def _c01_partition_traceability(
    root: Path, traceability: dict[str, Any], known_checks: set[str],
    executed_checks: set[str],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if set(traceability) != {
        "traceability_id", "version", "generated_at", "critical_schema_ids", "constraints",
    }:
        raise AssertionError("Semantic traceability top-level shape drift")
    schemas_by_id: dict[str, dict[str, Any]] = {}
    for path in sorted((root / "schemas").glob("*.json")):
        schema = json.loads(path.read_text(encoding="utf-8"))
        if schema["$id"] in schemas_by_id:
            raise AssertionError("Semantic traceability Schema ID collision")
        schemas_by_id[schema["$id"]] = schema
    expected_critical = {
        schema_id
        for schema_id, schema in schemas_by_id.items()
        if schema.get("x-semantic-constraints")
    }
    declared_critical = traceability["critical_schema_ids"]
    if len(declared_critical) != len(set(declared_critical)) or set(declared_critical) != expected_critical:
        raise AssertionError(
            "Semantic traceability does not enumerate every schema with stable semantic constraints"
        )
    generated_critical = {
        (schema_id, index): statement
        for schema_id in declared_critical
        for index, statement in enumerate(schemas_by_id[schema_id]["x-semantic-constraints"])
    }
    suite_cache: dict[str, set[str]] = {}
    identifiers: set[str] = set()
    coordinates: set[tuple[str, int]] = set()
    critical_entries: list[dict[str, Any]] = []
    supplemental_entries: list[dict[str, Any]] = []
    for entry in traceability["constraints"]:
        if set(entry) != {
            "constraint_id", "schema_id", "constraint_index", "statement", "enforcements",
        }:
            raise AssertionError("Semantic traceability entry shape drift")
        if entry["schema_id"] not in schemas_by_id:
            raise AssertionError("Semantic traceability references an unresolved Schema")
        if not isinstance(entry["constraint_index"], int) or entry["constraint_index"] < 0:
            raise AssertionError("Semantic traceability constraint index drift")
        if entry["constraint_id"] != _c01_stable_constraint_id(entry):
            raise AssertionError("Semantic traceability stable constraint ID drift")
        coordinate = (entry["schema_id"], entry["constraint_index"])
        if entry["constraint_id"] in identifiers or coordinate in coordinates:
            raise AssertionError("Semantic traceability ID or Schema/index collision")
        identifiers.add(entry["constraint_id"])
        coordinates.add(coordinate)
        if coordinate in generated_critical:
            if entry["statement"] != generated_critical[coordinate]:
                raise AssertionError("Semantic traceability is stale relative to its source Schema")
            critical_entries.append(entry)
        else:
            if entry["schema_id"] in expected_critical:
                raise AssertionError("Critical semantic constraint coordinate is outside its source Schema")
            supplemental_entries.append(copy.deepcopy(entry))
        if not entry["enforcements"]:
            raise AssertionError("Semantic traceability constraint has no enforcement responsibility")
        for enforcement in entry["enforcements"]:
            if set(enforcement) != {"kind", "artifact", "check_id", "status"}:
                raise AssertionError("Semantic traceability enforcement shape drift")
            artifact = enforcement["artifact"]
            if artifact == SEMANTIC_VALIDATOR_URN:
                enforcement_path = Path(__file__).resolve()
            elif artifact.startswith(BLUEPRINT_ARTIFACT_URN_PREFIX):
                try:
                    enforcement_path = BLUEPRINT_ARTIFACTS[artifact]
                except KeyError as error:
                    raise AssertionError(
                        f"Unknown Blueprint responsibility URN: {artifact}"
                    ) from error
            else:
                enforcement_path = root / artifact
            if not enforcement_path.exists():
                raise AssertionError("Semantic traceability references a missing enforcement artifact")
            if enforcement["status"] == "contract_gate":
                if enforcement["kind"] != "semantic_validator" or artifact != SEMANTIC_VALIDATOR_URN:
                    raise AssertionError(
                        "Contract-gate semantic evidence must be an executable semantic-validator check"
                    )
                if enforcement["check_id"] not in known_checks:
                    raise AssertionError("Semantic traceability references an unknown contract check ID")
                if enforcement["check_id"] not in executed_checks:
                    raise AssertionError(
                        "Semantic traceability references a contract check not executed in this Gate"
                    )
            elif enforcement["status"] == "phase0_implementation_required":
                if enforcement_path.suffix == ".json":
                    cache_key = str(enforcement_path)
                    if cache_key not in suite_cache:
                        suite = json.loads(enforcement_path.read_text(encoding="utf-8"))
                        suite_cache[cache_key] = {
                            test["test_id"]
                            for profile in suite.get("profiles", [])
                            for test in profile.get("tests", [])
                        }
                    if enforcement["kind"] != "conformance_test" or (
                        enforcement["check_id"] not in suite_cache[cache_key]
                    ):
                        raise AssertionError(
                            "Semantic traceability references a missing Conformance Suite test_id"
                        )
                elif artifact.startswith(BLUEPRINT_ARTIFACT_URN_PREFIX):
                    if f"`{enforcement['check_id']}`" not in enforcement_path.read_text(
                        encoding="utf-8"
                    ):
                        raise AssertionError(
                            "Semantic traceability references an undocumented Phase 0 responsibility ID"
                        )
                else:
                    raise AssertionError(
                        "Phase 0 implementation evidence must resolve to a Suite JSON or responsibility Markdown"
                    )
            else:
                raise AssertionError("Semantic traceability contains an unsupported enforcement status")
    if set(generated_critical) != {
        (entry["schema_id"], entry["constraint_index"]) for entry in critical_entries
    }:
        raise AssertionError("Semantic traceability does not cover every critical constraint")
    return critical_entries, supplemental_entries


def _c01_validate_supplemental_traceability(
    root: Path, known_checks: set[str], executed_checks: set[str],
) -> None:
    traceability = json.loads((root / "semantic-constraints-v1.json").read_text(encoding="utf-8"))
    _critical, supplemental = _c01_partition_traceability(
        root, traceability, known_checks, executed_checks,
    )
    if [entry["schema_id"] for entry in supplemental] != list(_C01_RUNTIME_READ_SCHEMA_CASES):
        raise AssertionError("C01 supplemental traceability order/set drift")
    for entry in supplemental:
        expected_suite_ids = _C01_RUNTIME_READ_SCHEMA_CASES[entry["schema_id"]]
        contract_gate = []
        suite_checks = []
        for enforcement in entry["enforcements"]:
            if set(enforcement) != {"kind", "artifact", "check_id", "status"}:
                raise AssertionError("C01 supplemental enforcement shape drift")
            if enforcement["status"] == "contract_gate":
                contract_gate.append(enforcement)
                if enforcement != {
                    "kind": "semantic_validator",
                    "artifact": SEMANTIC_VALIDATOR_URN,
                    "check_id": _C01_RUNTIME_READ_CHECK,
                    "status": "contract_gate",
                }:
                    raise AssertionError("C01 supplemental Contract Gate mapping drift")
            elif enforcement["status"] == "phase0_implementation_required":
                suite_checks.append(enforcement["check_id"])
                if enforcement["kind"] != "conformance_test" or enforcement["artifact"] != (
                    "conformance/runtime/v1/suite.json"
                ):
                    raise AssertionError("C01 supplemental Suite reference drift")
            else:
                raise AssertionError("C01 supplemental enforcement status drift")
        if len(contract_gate) != 1 or suite_checks != expected_suite_ids:
            raise AssertionError("C01 supplemental enforcement order/cardinality drift")


def _c01_validate_suite_cases(root: Path) -> None:
    suite = json.loads((root / "conformance/runtime/v1/suite.json").read_text(encoding="utf-8"))
    runtime = next(
        profile for profile in suite["profiles"] if profile["profile_id"] == "runtime-core-v1"
    )
    expected = [
        "status-read-invalid-request-400", "event-read-invalid-request-400",
        "status-read-throttled-429", "event-read-throttled-429",
    ]
    selected = [test for test in runtime["tests"] if test["test_id"] in expected]
    if [test["test_id"] for test in selected] != expected:
        raise AssertionError("C01 Runtime Suite case order/set drift")
    required_tokens = {
        expected[0]: ["c01-out-of-scope", "cannot satisfy this case", "remains 403", "no Retry-After"],
        expected[1]: ["c01-out-of-scope", "Malformed or out-of-range input is 400", "retention is 410", "remains 403"],
        expected[2]: ["exactly one raw Retry-After", "response invalid and forbids retry", "recomputes rather than reuses"],
        expected[3]: ["exactly one raw Retry-After", "preserves cursor and limit", "does not advance the cursor"],
    }
    for test in selected:
        description = test["description"]
        if any(token not in description for token in required_tokens[test["test_id"]]):
            raise AssertionError(f"C01 Runtime Suite authority case drift: {test['test_id']}")
        if "phase0_implementation_required" not in description or "does not claim Provider passage" not in description:
            raise AssertionError(f"C01 Runtime Suite maturity boundary drift: {test['test_id']}")


def validate_c01_runtime_read_semantics(
    root: Path, known_checks: set[str], executed_checks: set[str],
) -> None:
    executed_before = set(executed_checks)
    try:
        _c01_validate_openapi_and_schemas(root)
        _c01_validate_runtime_registries(root)
        _c01_validate_suite_cases(root)
        if _C01_RUNTIME_READ_CHECK not in known_checks:
            raise AssertionError("C01 Runtime read semantic check is not registered")
        executed_checks.add(_C01_RUNTIME_READ_CHECK)
        _c01_validate_supplemental_traceability(root, known_checks, executed_checks)
    except Exception:
        executed_checks.clear()
        executed_checks.update(executed_before)
        raise


def self_test_c01_runtime_read() -> None:
    protected_before = _c01_snapshot_protected_state()
    with tempfile.TemporaryDirectory(prefix="c01-semantic-") as temporary:
        root = Path(temporary) / "contract"
        shutil.copytree(CONTRACT_ROOT, root)
        active_suite_path = root / _C01_RUNTIME_SUITE_ACTIVE
        active_suite = json.loads(active_suite_path.read_text(encoding="utf-8"))
        active_suite["suite_digest"] = _c01_jcs_digest(active_suite, "suite_digest")
        active_suite_path.write_text(
            json.dumps(active_suite, indent=2) + "\n", encoding="utf-8",
        )
        known = {_C01_RUNTIME_READ_CHECK}
        executed: set[str] = set()
        validate_c01_runtime_read_semantics(root, known, executed)
        if executed != {_C01_RUNTIME_READ_CHECK}:
            raise AssertionError("C01 semantic check was not marked after successful structure validation")

        openapi_path = root / "openapi/agent-runtime-provider-v1.yaml"
        original_openapi = openapi_path.read_bytes()
        document = yaml.safe_load(original_openapi)
        document["paths"]["/v1/runs/{runtime_run_id}"]["get"][
            "x-runtime-read-response-precedence"
        ][0:2] = ["401", "400"]
        openapi_path.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
        mutation_executed: set[str] = set()
        try:
            validate_c01_runtime_read_semantics(root, known, mutation_executed)
        except AssertionError:
            pass
        else:
            raise AssertionError("C01 semantic OpenAPI structure mutation did not fail closed")
        if mutation_executed:
            raise AssertionError("C01 failed structure mutation retained an executed check mark")
        openapi_path.write_bytes(original_openapi)

        semantic_path = root / "semantic-constraints-v1.json"
        original_semantic = semantic_path.read_bytes()
        traceability = json.loads(original_semantic)
        supplemental = [
            entry for entry in traceability["constraints"]
            if entry["schema_id"] in _C01_RUNTIME_READ_SCHEMA_CASES
        ]
        supplemental[0]["enforcements"][0]["check_id"] = "runtime_read.unknown"
        semantic_path.write_text(json.dumps(traceability, indent=2) + "\n", encoding="utf-8")
        mutation_executed = set()
        try:
            validate_c01_runtime_read_semantics(root, known, mutation_executed)
        except AssertionError:
            pass
        else:
            raise AssertionError("C01 semantic unknown check mutation did not fail closed")
        if mutation_executed:
            raise AssertionError("C01 failed traceability mutation retained an executed check mark")
        semantic_path.write_bytes(original_semantic)

        traceability = json.loads(original_semantic)
        supplemental = [
            entry for entry in traceability["constraints"]
            if entry["schema_id"] in _C01_RUNTIME_READ_SCHEMA_CASES
        ]
        supplemental[0]["enforcements"][0]["check_id"] = "runtime_read.unexecuted"
        semantic_path.write_text(json.dumps(traceability, indent=2) + "\n", encoding="utf-8")
        mutation_executed = set()
        try:
            validate_c01_runtime_read_semantics(
                root, known | {"runtime_read.unexecuted"}, mutation_executed,
            )
        except AssertionError:
            pass
        else:
            raise AssertionError("C01 semantic known-but-unexecuted mutation did not fail closed")
        if mutation_executed:
            raise AssertionError("C01 unexecuted-check mutation retained an executed check mark")
        semantic_path.write_bytes(original_semantic)

        traceability = json.loads(original_semantic)
        indexes = [
            index for index, entry in enumerate(traceability["constraints"])
            if entry["schema_id"] in _C01_RUNTIME_READ_SCHEMA_CASES
        ]
        traceability["constraints"][indexes[0]], traceability["constraints"][indexes[1]] = (
            traceability["constraints"][indexes[1]], traceability["constraints"][indexes[0]],
        )
        semantic_path.write_text(json.dumps(traceability, indent=2) + "\n", encoding="utf-8")
        try:
            validate_c01_runtime_read_semantics(root, known, set())
        except AssertionError:
            pass
        else:
            raise AssertionError("C01 semantic supplemental reorder did not fail closed")
        semantic_path.write_bytes(original_semantic)

        def expect_failure(label: str) -> None:
            mutation_executed: set[str] = set()
            try:
                validate_c01_runtime_read_semantics(root, known, mutation_executed)
            except AssertionError:
                pass
            else:
                raise AssertionError(f"C01 semantic mutation did not fail closed: {label}")
            if mutation_executed:
                raise AssertionError(f"C01 semantic mutation retained an executed mark: {label}")

        for label, mutate in (
            (
                "supplemental-delete",
                lambda value, indexes: value["constraints"].pop(indexes[0]),
            ),
            (
                "supplemental-statement",
                lambda value, indexes: value["constraints"][indexes[0]].update({"statement": "drift"}),
            ),
            (
                "supplemental-duplicate-collision",
                lambda value, indexes: value["constraints"].append(copy.deepcopy(value["constraints"][indexes[0]])),
            ),
            (
                "supplemental-unresolved-schema",
                lambda value, indexes: value["constraints"][indexes[0]].update({"schema_id": "urn:missing"}),
            ),
        ):
            traceability = json.loads(original_semantic)
            indexes = [
                index for index, entry in enumerate(traceability["constraints"])
                if entry["schema_id"] in _C01_RUNTIME_READ_SCHEMA_CASES
            ]
            mutate(traceability, indexes)
            semantic_path.write_text(json.dumps(traceability, indent=2) + "\n", encoding="utf-8")
            expect_failure(label)
            semantic_path.write_bytes(original_semantic)

        capabilities_path = root / "examples/contracts/agent-runtime-capabilities.json"
        capabilities_bytes = capabilities_path.read_bytes()
        capabilities = json.loads(capabilities_bytes)
        capabilities["checkpoint_profiles"][0]["suite_digest"] = "sha256:" + "0" * 64
        capabilities_path.write_text(json.dumps(capabilities, indent=2) + "\n", encoding="utf-8")
        expect_failure("unresolved-suite-tuple")
        capabilities_path.write_bytes(capabilities_bytes)

        revision_path = root / "examples/contracts/agent-runtime-provider-revision.json"
        revision_bytes = revision_path.read_bytes()
        revision = json.loads(revision_bytes)
        revision["port"]["contract_digest"] = "sha256:" + "0" * 64
        revision_path.write_text(json.dumps(revision, indent=2) + "\n", encoding="utf-8")
        expect_failure("unresolved-port-tuple")
        revision_path.write_bytes(revision_bytes)

        revision = json.loads(revision_bytes)
        revision["conformance"][0].update({
            "suite_version": "1.0.1",
            "suite_digest": active_suite["suite_digest"],
            "result": "passed",
        })
        revision_path.write_text(json.dumps(revision, indent=2) + "\n", encoding="utf-8")
        expect_failure("active-suite-passed")
        revision_path.write_bytes(revision_bytes)

        snapshot_suite_path = root / _C01_RUNTIME_SUITE_SNAPSHOT
        snapshot_suite_bytes = snapshot_suite_path.read_bytes()
        snapshot_suite_path.unlink()
        expect_failure("missing-suite-snapshot")
        snapshot_suite_path.parent.mkdir(parents=True, exist_ok=True)
        snapshot_suite_path.write_bytes(snapshot_suite_bytes)

        duplicate_suite_path = snapshot_suite_path.parent.parent / "duplicate" / "suite.json"
        duplicate_suite_path.parent.mkdir(parents=True, exist_ok=True)
        duplicate_suite_path.write_bytes(snapshot_suite_bytes)
        expect_failure("duplicate-suite-tuple")
        duplicate_suite_path.unlink()

        active_openapi_path = root / _C01_RUNTIME_OPENAPI_ACTIVE
        snapshot_openapi_path = root / _C01_RUNTIME_OPENAPI_SNAPSHOT
        active_openapi_bytes = active_openapi_path.read_bytes()
        snapshot_openapi_bytes = snapshot_openapi_path.read_bytes()
        active_openapi_path.write_bytes(snapshot_openapi_bytes)
        snapshot_openapi_path.write_bytes(active_openapi_bytes)
        expect_failure("active-snapshot-port-swap")
        active_openapi_path.write_bytes(active_openapi_bytes)
        snapshot_openapi_path.write_bytes(snapshot_openapi_bytes)

        final_executed: set[str] = set()
        validate_c01_runtime_read_semantics(root, known, final_executed)
    if _c01_snapshot_protected_state() != protected_before:
        raise AssertionError("C01 semantic self-test changed protected Contract/build/evidence state")


if "--self-test-c01-runtime-read" in sys.argv:
    if sys.argv[1:] != ["--self-test-c01-runtime-read"]:
        raise SystemExit("--self-test-c01-runtime-read cannot be combined with other arguments")
    self_test_c01_runtime_read()
    print("C01 Runtime read semantic authority self-test passed.")
    raise SystemExit(0)
if len(sys.argv) != 1:
    raise SystemExit(f"Unknown arguments: {sys.argv[1:]}")


SCHEMA_REGISTRY = Registry()
for schema_path in sorted((CONTRACT_ROOT / "schemas").glob("*.json")):
    schema_value = json.loads(schema_path.read_text(encoding="utf-8"))
    SCHEMA_REGISTRY = SCHEMA_REGISTRY.with_resource(schema_value["$id"], Resource.from_contents(schema_value))


KNOWN_CONTRACT_CHECKS = {
    "runtime_start.execution_topology",
    "runtime_start.workspace_binding",
    "runtime_start.sandbox_binding",
    "runtime_start.request_digest",
    "runtime_start.input_binding",
    "runtime_start.immutable_context_binding",
    "runtime_authorization.digest",
    "runtime_authorization.lineage",
    "runtime_authorization.ceiling",
    "runtime_authorization.internal_binding",
    "runtime_authorization.scope",
    "runtime_authorization.expiry",
    "runtime_authorization.artifact_coverage",
    "runtime_token.binding",
    "runtime_token.lifetime",
    "runtime_token.audience",
    "runtime_command.digest",
    "runtime_command.sequence",
    "runtime_command.idempotency",
    "runtime_command.fencing",
    "runtime_command.user_control_binding",
    "runtime_command.system_safety_binding",
    "runtime_command.child_admission_binding",
    "workflow_run.lifecycle",
    "workflow_root_binding.digest",
    "workflow_root_binding.scope",
    "workflow_root_binding.atomic_creation",
    "agent_run.topology",
    "agent_run.spawn_binding",
    "agent_budget.digest",
    "agent_budget.scope",
    "agent_budget.shared_ledger",
    "child_spawn.digest",
    "child_spawn.scope",
    "child_spawn.provider_boundary",
    "child_spawn.idempotency",
    "child_admission.digest",
    "child_admission.outcome",
    "child_admission.atomic_creation",
    "control_fanout.digest",
    "control_fanout.authority",
    "control_fanout.coverage",
    "control_fanout.fencing",
    "control_fanout.recovery",
    "work_order.multiagent_terminal",
    "system_safety_control.digest",
    "system_safety_control.scope",
    "system_safety_control.evidence",
    "system_safety_control.reduction_only",
    "commercial_revocation.digest",
    "commercial_revocation.time_order",
    "commercial_revocation.sender_binding",
    "commercial_revocation.authorization_binding",
    "commercial_revocation.fanout",
    "sandbox_token.binding",
    "sandbox_token.lifetime",
    "sandbox_spec.execution_ceiling",
    "sandbox_spec.workspace_binding",
    "work_order.failure_paths",
    "work_order_control.grant_binding",
    "work_order_control.conditional_cas",
    "work_order_control.authority_exclusive",
    "work_order_state.machine",
    "conversation_branch.head_consistency",
    "conversation_branch.workspace_binding",
    "conversation_branch.create",
    "conversation_branch.created_workspace",
    "workspace_revision.chain",
    "provider_resolution.decision_digest",
    "provider_resolution.execution_scope",
    "provider_resolution.identity_dependency",
    "provider_resolution.selected_candidate",
    "provider_revision.integrity",
    "policy_decision.outcome_time",
    "technical_usage.binding",
    "usage_report.finality",
    "settlement.accounting",
    "runtime_gateway.frame_integrity",
    "artifact_operation.binding",
    "artifact_operation.cancellation",
    "no_usage.accounting",
    "compatibility.fail_closed",
    "secret_mediation.binding",
    "artifact_ingest.lifecycle",
    "capability_invocation.request_digest",
    "capability_invocation.owner_request_binding",
    "capability_invocation.resolution_binding",
    "capability_invocation.execution_context",
    "capability_invocation.token_binding",
    "capability_invocation.token_lifetime",
    "capability_invocation.token_lineage",
    "capability_invocation.operation_binding",
    "capability_invocation.artifact_grant_expiry",
    "capability_invocation.staging_grant",
    "workspace_manifest.digest",
    "workspace_manifest.path_policy",
    "workspace_manifest.counts",
    "workspace_manifest.symlink_policy",
    "runtime_session.requested_scope_subset",
    "runtime_session.sandbox_slot_binding",
    "runtime_session.scope_class",
    "runtime_session.channel_policy",
    "runtime_session.route_digest",
    "runtime_session.route_scope",
    "runtime_session.route_opaque",
    "canonical_event.work_binding",
    "canonical_event.execution_scope",
    "canonical_event.source_dedupe",
    "canonical_event.producer_binding",
    "canonical_event.registry_binding",
    "execution_grant.clock_skew",
    "execution_grant.expiration_order",
    "execution_grant.max_ttl",
    "execution_grant.request_digest",
    "execution_grant.principal_context",
    "execution_grant.request_identity",
    "execution_grant.commercial_limits",
    "execution_grant.snapshot_validity",
    "service_token.binding",
    "service_token.lifetime",
    "service_token.scope",
    "work_session.binding",
    "work_session.lifetime",
    "work_session.scope",
    "plugin_token.binding",
    "plugin_token.lifetime",
    "principal_context.digest",
    "principal_context.time_window",
    "principal_context.closed_attributes",
    "gateway_binding.closed_modes",
    "gateway_binding.port_contract",
    "gateway_binding.policy_alignment",
    "gateway_port.contract_mapping",
    "gateway_port.audience_binding",
    "artifact_grant.expiry",
    "artifact_grant.digest",
    "artifact_grant.scope",
    "artifact_grant.provider_permissions",
    "run_manifest.digest",
    "run_manifest.request_binding",
    "run_manifest.admission",
    "run_manifest.runtime_resolution",
    "run_manifest.sandbox_resolution",
    "run_manifest.experience_binding",
    "run_manifest.conversation_binding",
    "run_manifest.execution_inputs",
    "run_manifest.authorization_ceiling",
    "run_manifest.workspace_binding",
    "run_manifest.gateway_binding",
    "run_manifest.commercial_event_binding",
    "run_manifest.orchestration_binding",
    "artifact_staging_grant.digest",
    "artifact_staging_grant.scope",
    "artifact_staging_grant.expiry",
    "artifact_staging_grant.permissions",
    "artifact_gateway.operation_binding",
    "artifact_gateway.token_binding",
    "egress_destination.digest",
    "egress_destination.owner_scope",
    "egress_destination.request_policy",
    "egress_gateway.request_binding",
    "egress_gateway.token_binding",
    "usage_observation.observation_identity",
    "usage_observation.meter_and_evidence",
    "usage_observation.incomplete_status",
    "usage_observation.provider_boundary",
    "semantic_traceability.known_but_unexecuted",
    "runtime_read.http_authority",
}
EXECUTED_CONTRACT_CHECKS: set[str] = set()


def mark_checks(*check_ids: str) -> None:
    unknown = set(check_ids) - KNOWN_CONTRACT_CHECKS
    if unknown:
        raise AssertionError(f"Validator attempted to mark unknown contract checks: {sorted(unknown)}")
    EXECUTED_CONTRACT_CHECKS.update(check_ids)


def load(relative: str) -> Any:
    return json.loads((CONTRACT_ROOT / relative).read_text(encoding="utf-8"))


def load_yaml(relative: str) -> Any:
    return yaml.safe_load((CONTRACT_ROOT / relative).read_text(encoding="utf-8"))


def canonical_digest(value: Any) -> str:
    return "sha256:" + hashlib.sha256(rfc8785.dumps(value)).hexdigest()


def parse_datetime(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def validate_work_order_control_authority() -> None:
    contract = load_yaml("openapi/agent-access-v1.yaml")
    paths = contract["paths"]
    forbidden_paths = {
        "/v1/work-orders/{work_order_id}/pause",
        "/v1/work-orders/{work_order_id}/resume",
        "/v1/work-orders/{work_order_id}/cancel",
        "/v1/work-orders/{work_order_id}/approvals/{approval_id}/decision",
    }
    if forbidden_paths & set(paths):
        raise AssertionError("Agent Access exposes a legacy user control authority path")
    control = paths.get("/v1/work-orders/{work_order_id}/control", {}).get("post")
    request_schema = (
        control or {}
    ).get("requestBody", {}).get("content", {}).get("application/json", {}).get("schema", {})
    if (
        control is None
        or control.get("operationId") != "controlWorkOrder"
        or request_schema.get("$ref") != "../schemas/work-order-control-request.schema.json"
    ):
        raise AssertionError("Agent Access lacks the authoritative WorkOrderControlRequest route")
    mark_checks("work_order_control.authority_exclusive")


def validate_self_digest(value: dict[str, Any], field: str) -> None:
    unsigned = copy.deepcopy(value)
    expected = unsigned.pop(field)
    actual = canonical_digest(unsigned)
    if actual != expected:
        raise AssertionError(f"{field} mismatch: expected {actual}, got {expected}")


def validate_principal_context(snapshot: dict[str, Any]) -> None:
    validate_self_digest(snapshot, "principal_context_digest")
    issued_at = parse_datetime(snapshot["issued_at"])
    expires_at = parse_datetime(snapshot["expires_at"])
    if expires_at <= issued_at:
        raise AssertionError("PrincipalContextSnapshot expiry is not later than issuance")
    forbidden_fragments = {"password", "secret", "token", "credential", "email", "display_name"}
    if any(fragment in key for key in snapshot["attributes"] for fragment in forbidden_fragments):
        raise AssertionError("PrincipalContextSnapshot contains credentials or mutable display attributes")
    mark_checks(
        "principal_context.digest",
        "principal_context.time_window",
        "principal_context.closed_attributes",
    )


def validate_execution_grant_request(
    grant: dict[str, Any], request: dict[str, Any], *, authenticated_conversation_id: str,
) -> None:
    if grant["nbf"] > grant["iat"] + 30 or grant["iat"] >= grant["exp"] or grant["exp"] - grant["iat"] > 300:
        raise AssertionError("ExecutionGrant time window is invalid")
    if grant["request_digest_profile"] != "rfc8785-request-excluding-execution-grant-v1":
        raise AssertionError("ExecutionGrant uses an unsupported request digest profile")
    unsigned = copy.deepcopy(request)
    unsigned.pop("execution_grant", None)
    if grant["request_digest"] != canonical_digest(unsigned):
        raise AssertionError("ExecutionGrant request_digest does not bind the submitted request")
    validate_principal_context(grant["principal_context"])
    principal = grant["principal_context"]
    if grant["principal_context_digest"] != principal["principal_context_digest"]:
        raise AssertionError("ExecutionGrant principal_context_digest does not bind its snapshot")
    principal_bindings = {
        "client_app_id": "client_app_id",
        "external_tenant_id": "external_tenant_id",
        "external_principal_id": "external_principal_id",
    }
    if any(grant[claim] != principal[field] for claim, field in principal_bindings.items()):
        raise AssertionError("ExecutionGrant claims differ from PrincipalContextSnapshot")
    commercial = grant["commercial_authorization"]
    validate_self_digest(commercial, "commercial_authorization_digest")
    commercial_issued_at = parse_datetime(commercial["issued_at"])
    commercial_expires_at = parse_datetime(commercial["expires_at"])
    if commercial_expires_at <= commercial_issued_at:
        raise AssertionError("CommercialAuthorizationSnapshot expiry is not later than issuance")
    grant_issued_at = datetime.fromtimestamp(grant["iat"], tz=timezone.utc)
    grant_expires_at = datetime.fromtimestamp(grant["exp"], tz=timezone.utc)
    if grant_issued_at < max(parse_datetime(principal["issued_at"]), commercial_issued_at) or grant_expires_at > min(
        parse_datetime(principal["expires_at"]), commercial_expires_at
    ):
        raise AssertionError("ExecutionGrant is not fully covered by its identity and commercial snapshots")
    contract_id = grant["request_contract_id"]
    if contract_id == "urn:agent-platform:conversation-turn-request:v1":
        if not {"branch_id", "client_message_id", "scenario"} <= set(request):
            raise AssertionError("ExecutionGrant request_contract_id does not match the submitted request shape")
        if authenticated_conversation_id != grant["conversation_id"]:
            raise AssertionError("ConversationTurn path and ExecutionGrant bind different Conversations")
        bindings = {
            "branch_id": request["branch_id"],
            "client_message_id": request["client_message_id"],
            "scenario_id": request["scenario"]["id"],
            "scenario_version": request["scenario"]["version"],
            "scenario_definition_digest": request["scenario"]["definition_digest"],
        }
    elif contract_id == "urn:agent-platform:work-order-request:v1":
        if "work" not in request:
            raise AssertionError("ExecutionGrant request_contract_id does not match the submitted request shape")
        work = request["work"]
        bindings = {
            "conversation_id": work["conversation_id"],
            "turn_id": work["turn_id"],
            "branch_id": work["branch_id"],
            "client_message_id": work["client_message_id"],
            "scenario_id": work["scenario_id"],
            "scenario_version": work["scenario_version"],
            "scenario_definition_digest": work["scenario_definition_digest"],
        }
    elif contract_id == "urn:agent-platform:work-order-control-request:v1":
        if not {"control_request_id", "work_order_id", "conversation_id", "branch_id", "action"} <= set(request):
            raise AssertionError("ExecutionGrant request_contract_id does not match the submitted request shape")
        if authenticated_conversation_id != request["conversation_id"]:
            raise AssertionError("WorkOrderControl path and request bind different Conversations")
        bindings = {
            "conversation_id": request["conversation_id"],
            "branch_id": request["branch_id"],
            "work_order_id": request["work_order_id"],
            "control_request_id": request["control_request_id"],
        }
        forbidden = {"turn_id", "client_message_id", "scenario_id", "scenario_version", "scenario_definition_digest"}
        if forbidden & set(grant):
            raise AssertionError("Control ExecutionGrant contains stale Turn or Scenario bindings")
    else:
        raise AssertionError("ExecutionGrant request_contract_id is unsupported")
    if any(grant[field] != value for field, value in bindings.items()):
        raise AssertionError("ExecutionGrant identity bindings differ from the submitted request")
    if not set(grant["capabilities"]) <= set(commercial["authorized_capabilities"]):
        raise AssertionError("ExecutionGrant capabilities exceed commercial authorization")
    if any(
        name not in commercial["authorized_limits"] or value > commercial["authorized_limits"][name]
        for name, value in grant["limits"].items()
    ):
        raise AssertionError("ExecutionGrant limits exceed commercial authorization")
    mark_checks(
        "execution_grant.clock_skew",
        "execution_grant.expiration_order",
        "execution_grant.max_ttl",
        "execution_grant.request_digest",
        "execution_grant.principal_context",
        "execution_grant.request_identity",
        "execution_grant.commercial_limits",
        "execution_grant.snapshot_validity",
    )
    if contract_id == "urn:agent-platform:work-order-control-request:v1":
        mark_checks("work_order_control.grant_binding")


def validate_service_access_token(
    token: dict[str, Any], *, registered_issuer: str, authenticated_subject: str,
    authenticated_client_id: str, allowed_scopes: set[str],
) -> None:
    audience = token["aud"] if isinstance(token["aud"], list) else [token["aud"]]
    scopes = token["scope"].split(" ")
    if not token["iat"] <= token["nbf"] < token["exp"] or token["exp"] - token["iat"] > 300:
        raise AssertionError("Service Access Token lifetime is invalid")
    if (
        token["iss"] != registered_issuer
        or token["sub"] != authenticated_subject
        or token["client_id"] != authenticated_client_id
        or audience != ["https://agent-api.agent-platform.internal"]
    ):
        raise AssertionError("Service Access Token differs from authenticated workload")
    if len(scopes) != len(set(scopes)) or not set(scopes) <= allowed_scopes:
        raise AssertionError("Service Access Token scopes are not allowlisted")
    mark_checks("service_token.binding", "service_token.lifetime", "service_token.scope")


def validate_work_session_claims(
    claims: dict[str, Any], request: dict[str, Any], conversation: dict[str, Any],
    *, tenant_id: str,
) -> None:
    commercial = request["commercial_authorization"]
    principal = request["principal_context"]
    validate_self_digest(commercial, "commercial_authorization_digest")
    validate_principal_context(principal)
    if request["external_principal_id"] != principal["external_principal_id"]:
        raise AssertionError("WorkSession request and PrincipalContext identify different subjects")
    expected = {
        "client_app_id": principal["client_app_id"],
        "tenant_id": tenant_id,
        "principal_id": request["external_principal_id"],
        "conversation_id": conversation["conversation_id"],
        "commercial_authorization_id": commercial["commercial_authorization_id"],
        "commercial_authorization_digest": commercial["commercial_authorization_digest"],
        "commercial_authorization_expires_at": commercial["expires_at"],
        "principal_context_digest": principal["principal_context_digest"],
    }
    if any(claims[field] != value for field, value in expected.items()):
        raise AssertionError("WorkSession claims differ from the admitted creation context")
    if (
        not claims["iat"] <= claims["nbf"] < claims["exp"]
        or claims["exp"] - claims["iat"] > min(request["ttl_seconds"], 3600)
        or datetime.fromtimestamp(claims["exp"], tz=timezone.utc)
        > parse_datetime(claims["commercial_authorization_expires_at"])
    ):
        raise AssertionError("WorkSession claims outlive the admitted authorization")
    if not set(claims["scopes"]) <= set(request["scopes"]):
        raise AssertionError("WorkSession claims widen requested scopes")
    mark_checks("work_session.binding", "work_session.lifetime", "work_session.scope")


def validate_plugin_compatibility_token(
    request: dict[str, Any], token: dict[str, Any], *, plugin_id: str,
    provider_revision_id: str, audience: str, permissions_digest: str,
    operation_document: dict[str, Any] | None = None,
) -> None:
    validate_self_digest(request, "request_digest")
    operation_document = operation_document or request
    operation = token["operation"]
    if operation not in PLUGIN_OPERATION_CONTRACTS:
        raise AssertionError("Compatibility Plugin token authorizes an unknown operation")
    contract_id, digest_profile = PLUGIN_OPERATION_CONTRACTS[operation]
    if digest_profile == "rfc8785-request-excluding-request-digest-v1":
        validate_self_digest(operation_document, "request_digest")
        operation_digest = operation_document["request_digest"]
    else:
        operation_digest = canonical_digest(operation_document)
    expected = {
        "sub": "spn_agent_capability_bridge",
        "aud": audience,
        "tenant_id": request["tenant_id"],
        "client_app_id": request["client_app_id"],
        "work_order_id": request["work_order_id"],
        "plugin_id": plugin_id,
        "provider_revision_id": provider_revision_id,
        "operation": operation,
        "invocation_id": operation_document["invocation_id"],
        "invocation_attempt_id": operation_document["invocation_attempt_id"],
        "fencing_token": operation_document["fencing_token"],
        "capability_id": request["capability"]["id"],
        "capability_version": request["capability"]["version"],
        "staging_session_id": request["output_staging"]["session_id"],
        "permissions_digest": permissions_digest,
        "invocation_request_digest": request["request_digest"],
        "operation_contract_id": contract_id,
        "operation_digest_profile": digest_profile,
        "operation_request_digest": operation_digest,
        "deadline_at": request["deadline_at"],
    }
    if any(token[field] != value for field, value in expected.items()):
        raise AssertionError("Compatibility Plugin token differs from its bridged request")
    expirations = [parse_datetime(request["deadline_at"])]
    if operation == "invoke":
        if token["authority_mode"] != "execution":
            raise AssertionError("Compatibility Plugin Invoke requires execution authority")
        expirations.extend([
            parse_datetime(request["output_staging"]["expires_at"]),
            *(parse_datetime(item["expires_at"]) for item in request["input_artifacts"]),
        ])
    elif token["authority_mode"] != "safety_control":
        raise AssertionError("Compatibility Plugin control/read operation lacks safety-control authority")
    if (
        not token["iat"] <= token["nbf"] < token["exp"]
        or token["exp"] - token["iat"] > 300
        or operation == "invoke"
        and datetime.fromtimestamp(token["exp"], tz=timezone.utc) > min(expirations)
    ):
        raise AssertionError("Compatibility Plugin token authority or lifetime is invalid")
    mark_checks("plugin_token.binding", "plugin_token.lifetime")


def validate_provider_resolution(resolution: dict[str, Any]) -> None:
    validate_self_digest(resolution, "decision_digest")
    evaluations = resolution["candidate_evaluations"]
    candidate_keys = [
        (item["provider_instance_id"], item["provider_revision_id"], item["provider_audience"])
        for item in evaluations
    ]
    if len(candidate_keys) != len(set(candidate_keys)):
        raise AssertionError("ProviderResolution contains duplicate candidate evaluations")
    selected = [item for item in evaluations if item["outcome"] == "selected"]
    if len(selected) != 1:
        raise AssertionError("ProviderResolution must contain exactly one selected candidate")
    snapshot = resolution["selected_provider_revision"]
    if selected[0]["provider_instance_id"] != resolution["selected_provider_instance_id"]:
        raise AssertionError("ProviderResolution selected instance conflicts with candidate evidence")
    if selected[0]["provider_revision_id"] != snapshot["provider_revision_id"]:
        raise AssertionError("ProviderResolution selected revision conflicts with candidate evidence")
    if selected[0]["provider_audience"] != resolution["selected_provider_audience"]:
        raise AssertionError("ProviderResolution selected audience conflicts with candidate evidence")
    scope = resolution["execution_scope"]
    scope_id_fields = {
        "work_order": "work_order_id",
        "artifact_operation": "artifact_operation_id",
        "artifact_ingest": "artifact_ingest_session_id",
    }
    scope_id_field = scope_id_fields.get(scope["kind"])
    if (
        not resolution["tenant_id"]
        or not resolution["client_app_id"]
        or scope_id_field is None
        or not scope.get(scope_id_field)
    ):
        raise AssertionError("ProviderResolution is missing its Tenant, ClientApplication or execution scope")
    identity_mode = resolution["identity_dependency"]["mode"]
    if (identity_mode == "principal_context") != (resolution["principal_context_digest"] is not None):
        raise AssertionError("ProviderResolution identity dependency conflicts with Principal context binding")
    mark_checks(
        "provider_resolution.decision_digest",
        "provider_resolution.execution_scope",
        "provider_resolution.identity_dependency",
        "provider_resolution.selected_candidate",
    )


def validate_provider_architecture(context: dict[str, Any], suites: list[dict[str, Any]]) -> None:
    protocol_by_kind = {
        "agent_runtime": "agent-runtime-provider",
        "sandbox": "sandbox-provider",
    }
    suites_by_id = {suite["suite_id"]: suite for suite in suites}
    for revision in context["provider_revisions"]:
        expected_protocol = protocol_by_kind.get(revision["provider_kind"], "capability-provider")
        if revision["port"]["protocol"] != expected_protocol:
            raise AssertionError("Provider kind is bound to the wrong stable Port")
        implementation = revision["implementation"]
        if implementation["provenance"]["build_artifact_digest"] != implementation["distribution_digest"]:
            raise AssertionError("Provider distribution and BuildProvenance bind different artifacts")
        if implementation["distribution_type"] == "oci_image" and "image_digest" not in implementation:
            raise AssertionError("OCI Provider implementation is missing image_digest")
        for result in revision["conformance"]:
            suite = suites_by_id.get(result["suite_id"])
            if suite is None or result["suite_version"] != suite["suite_version"] or result["suite_digest"] != suite["suite_digest"]:
                raise AssertionError("Provider conformance does not bind an admitted immutable Suite")
            if result["suite_profile_id"] not in {profile["profile_id"] for profile in suite["profiles"]}:
                raise AssertionError("Provider conformance binds an unknown Suite profile")
    mark_checks("provider_revision.integrity")


def permissions_are_subset(current: dict[str, Any], ceiling: dict[str, Any]) -> bool:
    if not set(current["model"]["allowed_model_profiles"]) <= set(ceiling["model"]["allowed_model_profiles"]):
        return False
    if not set(current["tool"]["allowed_capabilities"]) <= set(ceiling["tool"]["allowed_capabilities"]):
        return False
    for permission in ("read", "stage_new_version"):
        if current["artifact"][permission] and not ceiling["artifact"][permission]:
            return False
    egress_rank = {"none": 0, "restricted": 1, "full": 2}
    if egress_rank[current["egress"]["mode"]] > egress_rank[ceiling["egress"]["mode"]]:
        return False
    if not set(current["egress"]["allowed_destination_classes"]) <= set(
        ceiling["egress"]["allowed_destination_classes"]
    ):
        return False
    ceiling_slots = {
        item["sandbox_slot_key"]: set(item["allowed_operations"])
        for item in ceiling["sandbox_slots"]
    }
    return all(
        item["sandbox_slot_key"] in ceiling_slots
        and set(item["allowed_operations"]) <= ceiling_slots[item["sandbox_slot_key"]]
        for item in current["sandbox_slots"]
    )


def validate_gateway_bindings(
    bindings: dict[str, Any], budget: dict[str, Any], permissions: dict[str, Any],
) -> None:
    expected_contracts = {
        "model": (
            "urn:agent-platform:openapi:capability-provider:v1",
            CONTRACT_ROOT / "openapi/capability-provider-v1.yaml",
        ),
        "tool": (
            "urn:agent-platform:openapi:capability-provider:v1",
            CONTRACT_ROOT / "openapi/capability-provider-v1.yaml",
        ),
        "artifact": (
            "urn:agent-platform:openapi:artifact-gateway:v1",
            CONTRACT_ROOT / "openapi/artifact-gateway-v1.yaml",
        ),
        "egress": (
            "urn:agent-platform:openapi:egress-gateway:v1",
            CONTRACT_ROOT / "openapi/egress-gateway-v1.yaml",
        ),
    }
    for kind, binding in bindings.items():
        if binding["kind"] != kind:
            raise AssertionError("Runtime Gateway binding is stored under the wrong kind")
        if binding["mode"] == "disabled" and "port" in binding:
            raise AssertionError("Disabled Runtime Gateway binding exposes a routable identity")
        if binding["mode"] == "enabled":
            port = binding["port"]
            expected_contract_id, contract_path = expected_contracts[kind]
            contract_digest = "sha256:" + hashlib.sha256(contract_path.read_bytes()).hexdigest()
            if port["gateway_kind"] != kind:
                raise AssertionError("Runtime Gateway Port kind differs from its binding")
            if port["contract_id"] != expected_contract_id or port["contract_digest"] != contract_digest:
                raise AssertionError("Runtime Gateway Port does not bind the admitted executable contract")
            if not port["audience"] or not port["binding_digest"]:
                raise AssertionError("Runtime Gateway Port lacks audience or immutable binding digest")
    required_modes = {
        "model": budget["policies"]["model_gateway_required"]
        or bool(permissions["model"]["allowed_model_profiles"]),
        "tool": budget["policies"]["tool_gateway_required"]
        or bool(permissions["tool"]["allowed_capabilities"]),
        "artifact": permissions["artifact"]["read"] or permissions["artifact"]["stage_new_version"],
        "egress": budget["policies"]["egress_gateway_required"]
        or permissions["egress"]["mode"] != "none",
    }
    for kind, required in required_modes.items():
        if required and bindings[kind]["mode"] != "enabled":
            raise AssertionError(f"Required {kind} Gateway binding is disabled")
    mark_checks(
        "gateway_binding.closed_modes",
        "gateway_binding.port_contract",
        "gateway_binding.policy_alignment",
        "gateway_port.contract_mapping",
        "gateway_port.audience_binding",
    )


def validate_runtime_authorization(
    authorization: dict[str, Any], manifest: dict[str, Any], runtime_start: dict[str, Any],
    predecessor: dict[str, Any] | None = None,
) -> None:
    validate_self_digest(authorization, "authorization_digest")
    validate_self_digest(authorization["execution_budget"], "budget_digest")
    validate_self_digest(
        authorization["agent_run_budget_allocation"], "allocation_digest"
    )
    validate_self_digest(authorization["policy_decision"], "decision_digest")
    validate_self_digest(authorization["effective_permissions"], "permissions_digest")
    if (
        authorization["policy_decision"]["execution_budget_id"] != authorization["execution_budget"]["budget_id"]
        or authorization["policy_decision"]["execution_budget_digest"] != authorization["execution_budget"]["budget_digest"]
        or authorization["policy_decision"]["effective_permissions_digest"]
        != authorization["effective_permissions"]["permissions_digest"]
    ):
        raise AssertionError("RuntimeAuthorization budget, policy and permission digests are not closed")
    expected_tenant = authorization["tenant_id"]
    expected_work_order = authorization["work_order_id"]
    expected_execution_scope = {
        "kind": "work_order",
        "work_order_id": expected_work_order,
    }
    for component_name in ("execution_budget", "policy_decision"):
        component = authorization[component_name]
        if (
            component["tenant_id"] != expected_tenant
            or component["execution_scope"] != expected_execution_scope
        ):
            raise AssertionError(f"RuntimeAuthorization {component_name} crosses its Tenant or WorkOrder")
    permissions = authorization["effective_permissions"]
    if permissions["tenant_id"] != expected_tenant or permissions["execution_scope"] != expected_execution_scope:
        raise AssertionError("RuntimeAuthorization effective_permissions crosses its Tenant or WorkOrder")
    commercial_binding = authorization["commercial_authorization"]
    policy = authorization["policy_decision"]
    if (
        policy["commercial_authorization_id"] != commercial_binding["commercial_authorization_id"]
        or policy["commercial_authorization_digest"] != commercial_binding["commercial_authorization_digest"]
    ):
        raise AssertionError("RuntimeAuthorization PolicyDecision binds a different CommercialAuthorization")
    if authorization["authorization_sequence"] == 1:
        if predecessor is not None or authorization["predecessor_authorization_digest"] is not None:
            raise AssertionError("Initial RuntimeAuthorization cannot have a predecessor")
        if authorization["renewal_reason"] != "initial_dispatch":
            raise AssertionError("Initial RuntimeAuthorization uses the wrong reason")
    else:
        if predecessor is None:
            raise AssertionError("Renewed RuntimeAuthorization lacks its predecessor")
        if authorization["authorization_sequence"] != predecessor["authorization_sequence"] + 1:
            raise AssertionError("RuntimeAuthorization sequence contains a gap")
        if authorization["predecessor_authorization_digest"] != predecessor["authorization_digest"]:
            raise AssertionError("RuntimeAuthorization predecessor digest mismatch")
        if authorization["renewal_reason"] == "initial_dispatch":
            raise AssertionError("Renewed RuntimeAuthorization uses initial_dispatch")
    expected_scope = {
        "tenant_id": manifest["tenant_id"],
        "work_order_id": manifest["work_order_id"],
        "runtime_run_id": runtime_start["runtime_run_id"],
        "run_manifest_digest": manifest["run_manifest_digest"],
        "commercial_authorization": manifest["commercial_authorization"],
    }
    if any(authorization[field] != value for field, value in expected_scope.items()):
        raise AssertionError("RuntimeAuthorization crosses its immutable Run scope")
    if authorization["agent_run_budget_allocation"] != manifest["agent_run_budget_allocation"]:
        raise AssertionError("RuntimeAuthorization changes its immutable AgentRun budget allocation")
    if authorization["authorization_sequence"] == 1:
        for field in ("execution_budget", "policy_decision", "effective_permissions"):
            if authorization[field] != manifest[field]:
                raise AssertionError("Initial RuntimeAuthorization differs from the RunManifest ceiling")
    else:
        if any(
            authorization["execution_budget"]["limits"][name] > manifest["execution_budget"]["limits"][name]
            for name in authorization["execution_budget"]["limits"]
        ):
            raise AssertionError("Renewed RuntimeAuthorization widens the execution budget")
        if authorization["execution_budget"]["policies"] != manifest["execution_budget"]["policies"]:
            raise AssertionError("Renewed RuntimeAuthorization changes admitted enforcement policy")
        outcome_rank = {"deny": 0, "approval_required": 1, "allow": 2}
        if outcome_rank[authorization["policy_decision"]["outcome"]] > outcome_rank[manifest["policy_decision"]["outcome"]]:
            raise AssertionError("Renewed RuntimeAuthorization widens the policy outcome")
        if not permissions_are_subset(authorization["effective_permissions"], manifest["effective_permissions"]):
            raise AssertionError("Renewed RuntimeAuthorization widens effective permissions")
    issued_at = parse_datetime(authorization["issued_at"])
    expires_at = parse_datetime(authorization["expires_at"])
    if expires_at <= issued_at:
        raise AssertionError("RuntimeAuthorization expiry is not later than issuance")
    if (expires_at - issued_at).total_seconds() > manifest["authorization_renewal_policy"]["max_ttl_seconds"]:
        raise AssertionError("RuntimeAuthorization exceeds the admitted renewal TTL")
    expiry_ceiling = min(
        parse_datetime(commercial_binding["expires_at"]),
        parse_datetime(authorization["execution_budget"]["expires_at"]),
        parse_datetime(authorization["policy_decision"]["expires_at"]),
        *(
            parse_datetime(grant["expires_at"])
            for grant in authorization["artifact_grants"]
        ),
    )
    if expires_at > expiry_ceiling:
        raise AssertionError("RuntimeAuthorization outlives a bound budget, policy or ArtifactGrant")
    requirements = {
        (item["artifact_id"], item["version_id"], item["artifact_digest"]): item
        for item in manifest["artifact_access_requirements"]
    }
    covered: set[tuple[str, str, str]] = set()
    for grant in authorization["artifact_grants"]:
        validate_self_digest(grant, "grant_digest")
        grant_issued_at = parse_datetime(grant["issued_at"])
        grant_expires_at = parse_datetime(grant["expires_at"])
        if grant_expires_at <= grant_issued_at:
            raise AssertionError("Runtime ArtifactGrant expiry is not later than issuance")
        if grant_issued_at < issued_at or grant_expires_at > expires_at:
            raise AssertionError("Runtime ArtifactGrant is outside its RuntimeAuthorization window")
        key = (grant["artifact_id"], grant["version_id"], grant["artifact_digest"])
        requirement = requirements.get(key)
        if requirement is None or grant["tenant_id"] != manifest["tenant_id"] or grant["execution_scope"] != expected_execution_scope:
            raise AssertionError("Runtime ArtifactGrant does not cover an admitted requirement")
        if any(
            grant[field] != runtime_start[field]
            for field in ("runtime_run_id", "invocation_id", "invocation_attempt_id")
        ):
            raise AssertionError("Runtime ArtifactGrant is not bound to the current InvocationAttempt")
        if not set(grant["permissions"]) <= set(requirement["allowed_permissions"]):
            raise AssertionError("Runtime ArtifactGrant exceeds admitted permissions")
        artifact_binding = manifest["gateway_bindings"]["artifact"]
        if artifact_binding["mode"] != "enabled" or grant["gateway_binding"] != artifact_binding["port"]:
            raise AssertionError("Runtime ArtifactGrant uses a Gateway outside the admitted RunManifest")
        covered.add(key)
    if covered != set(requirements) or len(authorization["artifact_grants"]) != len(requirements):
        raise AssertionError("Runtime ArtifactGrants do not exactly cover admitted requirements")
    validate_gateway_bindings(
        manifest["gateway_bindings"], authorization["execution_budget"], authorization["effective_permissions"]
    )
    mark_checks(
        "runtime_authorization.digest",
        "runtime_authorization.lineage",
        "runtime_authorization.ceiling",
        "runtime_authorization.internal_binding",
        "runtime_authorization.scope",
        "runtime_authorization.expiry",
        "runtime_authorization.artifact_coverage",
        "agent_budget.digest",
        "agent_budget.scope",
        "artifact_grant.expiry",
        "artifact_grant.digest",
        "artifact_grant.scope",
        "artifact_grant.provider_permissions",
    )


def limits_are_subset(candidate: dict[str, int], ceiling: dict[str, int]) -> bool:
    return set(candidate) <= set(ceiling) and all(
        candidate[name] <= ceiling[name] for name in candidate
    )


def validate_agent_run_budget_allocation(
    allocation: dict[str, Any], budget: dict[str, Any], agent_run: dict[str, Any],
    parent_allocation: dict[str, Any] | None = None,
) -> None:
    validate_self_digest(allocation, "allocation_digest")
    if any((
        allocation["tenant_id"] != budget["tenant_id"],
        budget["execution_scope"] != {
            "kind": "work_order",
            "work_order_id": allocation["work_order_id"],
        },
        allocation["agent_run_id"] != agent_run["agent_run_id"],
        allocation["work_order_budget_id"] != budget["budget_id"],
        allocation["work_order_budget_digest"] != budget["budget_digest"],
        parse_datetime(allocation["issued_at"]) >= parse_datetime(allocation["expires_at"]),
        parse_datetime(allocation["expires_at"]) > parse_datetime(budget["expires_at"]),
    )):
        raise AssertionError("AgentRun budget allocation crosses its shared WorkOrder budget")
    if set(allocation["limits"]) != AGENT_RUN_RESOURCE_LIMIT_NAMES or not limits_are_subset(
        allocation["limits"], budget["limits"]
    ):
        raise AssertionError("AgentRun budget allocation exceeds the WorkOrder hard ceiling")
    if agent_run["run_kind"] == "root":
        if parent_allocation is not None or "parent_allocation_id" in allocation:
            raise AssertionError("Root AgentRun allocation cannot have a parent")
        budget_resource_limits = {
            name: budget["limits"][name] for name in AGENT_RUN_RESOURCE_LIMIT_NAMES
        }
        if allocation["limits"] != budget_resource_limits:
            raise AssertionError("Root AgentRun allocation must equal WorkOrder resource limits")
    else:
        if parent_allocation is None:
            raise AssertionError("Child AgentRun allocation lacks its parent allocation")
        validate_self_digest(parent_allocation, "allocation_digest")
        if any((
            set(parent_allocation["limits"]) != AGENT_RUN_RESOURCE_LIMIT_NAMES,
            parse_datetime(allocation["issued_at"]) < parse_datetime(parent_allocation["issued_at"]),
            allocation.get("parent_allocation_id") != parent_allocation["allocation_id"],
            allocation.get("parent_allocation_digest") != parent_allocation["allocation_digest"],
            not limits_are_subset(allocation["limits"], parent_allocation["limits"]),
        )):
            raise AssertionError("Child AgentRun allocation exceeds or changes its parent allocation")
    mark_checks("agent_budget.digest", "agent_budget.scope", "agent_budget.shared_ledger")


def validate_workflow_root_binding(
    binding: dict[str, Any], workflow_run: dict[str, Any], agent_run: dict[str, Any],
    manifest: dict[str, Any],
) -> None:
    validate_self_digest(binding, "binding_digest")
    if agent_run["run_kind"] != "root" or any((
        binding["tenant_id"] != workflow_run["tenant_id"],
        binding["work_order_id"] != workflow_run["work_order_id"],
        binding["workflow_run_id"] != workflow_run["workflow_run_id"],
        binding["root_agent_run_id"] != agent_run["agent_run_id"],
        agent_run["root_agent_run_id"] != agent_run["agent_run_id"],
        binding["run_manifest_digest"] != manifest["run_manifest_digest"],
        parse_datetime(binding["bound_at"]) < parse_datetime(workflow_run["created_at"]),
        parse_datetime(binding["bound_at"]) < parse_datetime(agent_run["created_at"]),
    )):
        raise AssertionError("WorkflowRunRootBinding crosses its admitted Root execution")
    mark_checks(
        "workflow_run.lifecycle", "workflow_root_binding.digest",
        "workflow_root_binding.scope", "workflow_root_binding.atomic_creation",
    )


def validate_execution_topology(
    manifest: dict[str, Any], workflow_run: dict[str, Any], agent_run: dict[str, Any],
    runtime_start: dict[str, Any],
) -> None:
    validate_self_digest(manifest["orchestration_binding"], "binding_digest")
    validate_self_digest(runtime_start, "request_digest")
    tenant_ids = {manifest["tenant_id"], workflow_run["tenant_id"], agent_run["tenant_id"], runtime_start["tenant_id"]}
    if len(tenant_ids) != 1:
        raise AssertionError("Execution topology crosses tenants")
    if workflow_run["workflow_run_id"] != manifest["workflow_run_id"]:
        raise AssertionError("RunManifest and WorkflowRun IDs differ")
    if workflow_run["work_order_id"] != manifest["work_order_id"]:
        raise AssertionError("WorkflowRun belongs to a different WorkOrder")
    if workflow_run["workflow"] != manifest["workflow"] or workflow_run["orchestration_binding"] != manifest["orchestration_binding"]:
        raise AssertionError("WorkflowRun and RunManifest bind different orchestration evidence")
    if agent_run["agent_run_id"] != manifest["agent_run_id"] or runtime_start["agent_run_id"] != manifest["agent_run_id"]:
        raise AssertionError("AgentRun identity is not closed across Manifest and Runtime start")
    if agent_run["workflow_run_id"] != manifest["workflow_run_id"] or agent_run["work_order_id"] != manifest["work_order_id"]:
        raise AssertionError("AgentRun belongs to a different WorkflowRun or WorkOrder")
    if agent_run["runtime_run_id"] != runtime_start["runtime_run_id"]:
        raise AssertionError("One AgentRun must bind exactly one AgentRuntimeRun identity")
    if agent_run["run_manifest_digest"] != manifest["run_manifest_digest"] or runtime_start["run_manifest_digest"] != manifest["run_manifest_digest"]:
        raise AssertionError("Execution topology binds different RunManifest digests")
    topology = manifest["run_topology"]
    if runtime_start["run_topology"] != topology or any(
        agent_run[field] != topology[field]
        for field in (
            "run_kind", "root_agent_run_id", "run_depth",
            "required_for_work_order_completion",
        )
    ):
        raise AssertionError("AgentRun topology differs across Manifest and Runtime Start")
    if agent_run["run_kind"] == "root":
        if agent_run["root_agent_run_id"] != agent_run["agent_run_id"] or agent_run["run_depth"] != 0:
            raise AssertionError("Root AgentRun must identify itself at depth zero")
        if runtime_start["input"]["source_kind"] != "conversation_message" or (
            runtime_start["input_message_id"] != runtime_start["input"]["input_message_id"]
        ):
            raise AssertionError("Root Runtime input does not bind the admitted Conversation message")
    else:
        if any((
            agent_run.get("parent_agent_run_id") != topology.get("parent_agent_run_id"),
            agent_run.get("spawn_request_id") != topology.get("spawn_request_id"),
            runtime_start["input"]["source_kind"] != "delegated_task",
            runtime_start["input"].get("child_agent_spawn_request_id") != agent_run.get("spawn_request_id"),
            agent_run["run_depth"] < 1,
            "input_message_id" in runtime_start,
        )):
            raise AssertionError("Child AgentRun is not bound to its admitted SpawnRequest and parent")
    if runtime_start["workflow_run_id"] != manifest["workflow_run_id"]:
        raise AssertionError("Runtime start belongs to a different WorkflowRun")
    if agent_run["runtime_provider_resolution_id"] != manifest["agent_runtime"]["resolution_id"]:
        raise AssertionError("AgentRun and RunManifest bind different Runtime Provider resolutions")
    for resolution in manifest["capability_resolutions"]:
        if (
            resolution["tenant_id"] != manifest["tenant_id"]
            or resolution["execution_scope"] != {
                "kind": "work_order",
                "work_order_id": manifest["work_order_id"],
            }
        ):
            raise AssertionError("ProviderResolution crosses the RunManifest execution scope")
        validate_provider_resolution(resolution)
    for field in ("workspace_revision_id", "workspace_revision_digest"):
        if runtime_start[field] != manifest["conversation"][field]:
            raise AssertionError(f"Runtime start and RunManifest differ on {field}")
    for field in (
        "input", "context_package", "gateway_bindings", "admission_limits",
        "run_topology", "workspace_binding",
    ):
        if runtime_start[field] != manifest[field]:
            raise AssertionError(f"Runtime start and RunManifest differ on executable context {field}")
    workspace_binding = manifest["workspace_binding"]
    if any((
        workspace_binding["base_workspace_revision_id"]
        != manifest["conversation"]["workspace_revision_id"],
        workspace_binding["base_workspace_revision_digest"]
        != manifest["conversation"]["workspace_revision_digest"],
        runtime_start["workspace_revision_id"]
        != workspace_binding["base_workspace_revision_id"],
        runtime_start["workspace_revision_digest"]
        != workspace_binding["base_workspace_revision_digest"],
    )):
        raise AssertionError("AgentRun Workspace binding differs from its admitted base revision")
    if workspace_binding["workspace_mode"] == "read_only_parent_revision" and any(
        "files_write" in slot["allowed_operations"]
        for slot in manifest["effective_permissions"]["sandbox_slots"]
    ):
        raise AssertionError("Read-only AgentRun Workspace permits Sandbox file writes")
    if runtime_start["input"]["content_digest"] != canonical_digest(runtime_start["input"]["content"]):
        raise AssertionError("Runtime input content_digest does not bind the actual content")
    expanded_context_bytes = sum(item["size_bytes"] for item in runtime_start["context_package"]["items"])
    if expanded_context_bytes > runtime_start["runtime_authorization"]["execution_budget"]["limits"]["max_storage_bytes"]:
        raise AssertionError("Expanded Context Package exceeds the admitted storage budget")
    validate_runtime_authorization(runtime_start["runtime_authorization"], manifest, runtime_start)
    validate_agent_run_budget_allocation(
        manifest["agent_run_budget_allocation"], manifest["execution_budget"], agent_run,
        None,
    ) if agent_run["run_kind"] == "root" else None
    expected_sandboxes = {
        (item["sandbox_slot_key"], item["sandbox_id"])
        for item in manifest["sandboxes"]
    }
    actual_sandboxes = {
        (item["sandbox_slot_key"], item["sandbox_id"])
        for item in runtime_start["sandbox_bindings"]
    }
    if len(actual_sandboxes) != len(runtime_start["sandbox_bindings"]) or actual_sandboxes != expected_sandboxes:
        raise AssertionError("Runtime start Sandbox bindings do not exactly match RunManifest")
    mark_checks(
        "runtime_start.execution_topology",
        "runtime_start.workspace_binding",
        "runtime_start.sandbox_binding",
        "runtime_start.request_digest",
        "runtime_start.input_binding",
        "runtime_start.immutable_context_binding",
        "run_manifest.conversation_binding",
        "run_manifest.execution_inputs",
        "run_manifest.authorization_ceiling",
        "run_manifest.workspace_binding",
        "run_manifest.gateway_binding",
        "run_manifest.orchestration_binding",
        "agent_run.topology",
    )


def validate_child_agent_admission(
    spawn: dict[str, Any], decision: dict[str, Any], workflow_run: dict[str, Any],
    parent_run: dict[str, Any], root_run: dict[str, Any], parent_manifest: dict[str, Any],
    child_run: dict[str, Any],
    child_manifest: dict[str, Any], child_start: dict[str, Any], work_order_budget: dict[str, Any],
    parent_allocation: dict[str, Any], existing_agent_runs: list[dict[str, Any]],
) -> None:
    validate_self_digest(spawn, "request_digest")
    validate_self_digest(decision, "decision_digest")
    delegated_input = spawn["delegated_input"]
    if any((
        delegated_input["source_kind"] != "delegated_task",
        delegated_input.get("child_agent_spawn_request_id") != spawn["spawn_request_id"],
        delegated_input["content_digest"] != canonical_digest(delegated_input["content"]),
        spawn["tenant_id"] != parent_run["tenant_id"],
        spawn["work_order_id"] != parent_run["work_order_id"],
        spawn["workflow_run_id"] != parent_run["workflow_run_id"],
        spawn["parent_agent_run_id"] != parent_run["agent_run_id"],
        spawn["parent_runtime_run_id"] != parent_run["runtime_run_id"],
        spawn["root_agent_run_id"] != root_run["agent_run_id"],
        spawn["parent_run_depth"] != parent_run["run_depth"],
    )):
        raise AssertionError("Child SpawnRequest crosses its immutable parent execution")
    forbidden_provider_fields = {
        "child_agent_run_id", "runtime_run_id", "provider_revision_id",
        "provider_resolution_id", "sandbox_id", "budget_allocation",
    }
    if forbidden_provider_fields & set(spawn):
        raise AssertionError("Child SpawnRequest assigns Platform-owned admission fields")
    requested_capabilities = {
        (item["id"], item["version"], item.get("profile"))
        for item in spawn["required_capabilities"]
    }
    admitted_capabilities = {
        (
            item["capability"]["id"], item["capability"]["version"],
            item["capability"].get("profile"),
        )
        for item in child_manifest["capability_resolutions"]
    }
    if not requested_capabilities <= admitted_capabilities:
        raise AssertionError("Child Admission omits a requested Capability resolution")
    if any((
        child_manifest["effective_permissions"]["permissions_id"]
        == parent_manifest["effective_permissions"]["permissions_id"]
        and child_manifest["effective_permissions"]["permissions_digest"]
        != parent_manifest["effective_permissions"]["permissions_digest"],
        child_manifest["policy_decision"]["decision_id"]
        == parent_manifest["policy_decision"]["decision_id"]
        and child_manifest["policy_decision"]["decision_digest"]
        != parent_manifest["policy_decision"]["decision_digest"],
    )):
        raise AssertionError("Child Admission reuses an immutable authorization ID with new content")
    limits = work_order_budget["limits"]
    if any((
        parent_run["run_depth"] + 1 > limits["max_agent_depth"],
        len(existing_agent_runs) + 1 > limits["max_agent_runs"],
        sum(item.get("status", "running") not in {"succeeded", "failed", "cancelled"} for item in existing_agent_runs) + 1
        > limits["max_parallel_agent_runs"],
    )):
        raise AssertionError("Child SpawnRequest exceeds shared WorkOrder topology limits")
    if decision["outcome"] != "accepted" or decision["reason_codes"] != ["admitted"] or any((
        decision["spawn_request_id"] != spawn["spawn_request_id"],
        decision["spawn_request_digest"] != spawn["request_digest"],
        decision["tenant_id"] != spawn["tenant_id"],
        decision["work_order_id"] != spawn["work_order_id"],
        decision["workflow_run_id"] != spawn["workflow_run_id"],
        decision["parent_agent_run_id"] != parent_run["agent_run_id"],
        decision["child_agent_run_id"] != child_run["agent_run_id"],
        decision["runtime_run_id"] != child_run["runtime_run_id"],
        decision["runtime_provider_resolution_id"]
        != child_run["runtime_provider_resolution_id"],
        decision["runtime_provider_resolution_id"]
        != child_manifest["agent_runtime"]["resolution_id"],
        decision["run_manifest_digest"] != child_manifest["run_manifest_digest"],
        decision["budget_allocation"] != child_manifest["agent_run_budget_allocation"],
        decision["workspace_binding"] != child_manifest["workspace_binding"],
        decision["workspace_binding"]["workspace_mode"] != spawn["workspace_mode"],
        decision["workspace_binding"]["base_workspace_revision_id"]
        != parent_manifest["conversation"]["workspace_revision_id"],
        decision["workspace_binding"]["base_workspace_revision_digest"]
        != parent_manifest["conversation"]["workspace_revision_digest"],
        (spawn["sandbox_mode"] == "none") != (len(child_manifest["sandboxes"]) == 0),
        child_run["spawn_request_id"] != spawn["spawn_request_id"],
        child_run["parent_agent_run_id"] != parent_run["agent_run_id"],
        child_run["root_agent_run_id"] != root_run["agent_run_id"],
        child_run["run_depth"] != parent_run["run_depth"] + 1,
        child_run["required_for_work_order_completion"]
        != spawn["required_for_work_order_completion"],
        child_manifest["input"] != delegated_input,
        parse_datetime(spawn["requested_at"]) < parse_datetime(parent_run["created_at"]),
        parse_datetime(decision["budget_allocation"]["issued_at"])
        < parse_datetime(spawn["requested_at"]),
        parse_datetime(decision["budget_allocation"]["issued_at"])
        > parse_datetime(decision["decided_at"]),
        parse_datetime(decision["decided_at"]) < parse_datetime(spawn["requested_at"]),
        parse_datetime(child_run["created_at"]) < parse_datetime(decision["decided_at"]),
        parse_datetime(decision["decided_at"]) > parse_datetime(work_order_budget["expires_at"]),
    )):
        raise AssertionError("Child AdmissionDecision does not atomically bind the admitted child")
    validate_agent_run_budget_allocation(
        decision["budget_allocation"], work_order_budget, child_run, parent_allocation
    )
    validate_execution_topology(child_manifest, workflow_run, child_run, child_start)
    mark_checks(
        "child_spawn.digest", "child_spawn.scope", "child_spawn.provider_boundary",
        "child_spawn.idempotency", "child_admission.digest", "child_admission.outcome",
        "child_admission.atomic_creation", "agent_run.spawn_binding",
    )


def validate_agent_run_control_fanout(
    fanout: dict[str, Any], active_runs: list[dict[str, Any]],
    current_fencing: dict[str, int], authority_fact: dict[str, Any],
    previous_fanout: dict[str, Any] | None = None,
) -> None:
    validate_self_digest(fanout, "fanout_digest")
    if previous_fanout is None:
        if any((
            fanout["fanout_version"] != 1,
            fanout["previous_fanout_digest"] is not None,
            fanout["created_at"] != fanout["updated_at"],
            any(target["control_state"] != "pending" for target in fanout["targets"]),
        )):
            raise AssertionError("Initial AgentRun fanout is not a pending version-one snapshot")
    else:
        validate_self_digest(previous_fanout, "fanout_digest")
        immutable_fields = {
            "fanout_id", "tenant_id", "work_order_id", "action", "authority_kind",
            "authority_id", "authority_digest", "created_at",
        }
        if any((
            fanout["fanout_version"] != previous_fanout["fanout_version"] + 1,
            fanout["previous_fanout_digest"] != previous_fanout["fanout_digest"],
            parse_datetime(fanout["updated_at"]) <= parse_datetime(previous_fanout["updated_at"]),
            any(fanout[field] != previous_fanout[field] for field in immutable_fields),
        )):
            raise AssertionError("AgentRun fanout progress breaks its append-only predecessor chain")
        previous_targets = {
            (target["agent_run_id"], target["runtime_run_id"]): target
            for target in previous_fanout["targets"]
        }
        allowed_progress = {
            "pending": {"pending", "dispatched", "confirmed", "terminal_before_control", "outcome_unknown"},
            "dispatched": {"dispatched", "confirmed", "terminal_before_control", "outcome_unknown"},
            "outcome_unknown": {"outcome_unknown", "dispatched", "confirmed", "terminal_before_control"},
            "confirmed": {"confirmed"},
            "terminal_before_control": {"terminal_before_control"},
        }
        for target in fanout["targets"]:
            target_key = (target["agent_run_id"], target["runtime_run_id"])
            previous_target = previous_targets.get(target_key)
            if previous_target is None or any(
                target.get(field) != previous_target.get(field)
                for field in (
                    "target_fencing_token", "system_safety_control_id",
                    "system_safety_control_digest",
                )
            ) or target["control_state"] not in allowed_progress[previous_target["control_state"]]:
                raise AssertionError("AgentRun fanout target identity or progress regressed")
    user_control_action = authority_fact.get("action")
    expected_fanout_action = (
        "cancel" if user_control_action == "interrupt_and_enqueue" else user_control_action
    )
    if fanout["authority_kind"] == "work_order_control_request" and any((
        fanout["authority_id"] != authority_fact["control_request_id"],
        fanout["authority_digest"] != canonical_digest({
            key: value for key, value in authority_fact.items() if key != "execution_grant"
        }),
        expected_fanout_action not in {"pause", "cancel"},
        fanout["action"] != expected_fanout_action,
        fanout["work_order_id"] != authority_fact["work_order_id"],
    )):
        raise AssertionError("AgentRun fanout binds a different WorkOrderControlRequest")
    expected = {(item["agent_run_id"], item["runtime_run_id"]) for item in active_runs}
    actual = {(item["agent_run_id"], item["runtime_run_id"]) for item in fanout["targets"]}
    if len(actual) != len(fanout["targets"]) or actual != expected:
        raise AssertionError("AgentRun control fanout does not cover every active Run exactly once")
    if any(
        item["tenant_id"] != fanout["tenant_id"]
        or item["work_order_id"] != fanout["work_order_id"]
        for item in active_runs
    ):
        raise AssertionError("AgentRun control fanout crosses Tenant or WorkOrder scope")
    for target in fanout["targets"]:
        if target["target_fencing_token"] <= current_fencing[target["runtime_run_id"]]:
            raise AssertionError("AgentRun control fanout does not advance per-Run fencing")
        if fanout["authority_kind"] == "system_safety_trigger" and not {
            "system_safety_control_id", "system_safety_control_digest"
        } <= set(target):
            raise AssertionError("System AgentRun fanout lacks a per-Run SystemSafetyControl")
        if fanout["authority_kind"] == "work_order_control_request" and {
            "system_safety_control_id", "system_safety_control_digest"
        } & set(target):
            raise AssertionError("User AgentRun fanout mixes SystemSafetyControl authority")
    mark_checks(
        "control_fanout.digest", "control_fanout.authority", "control_fanout.coverage",
        "control_fanout.fencing", "control_fanout.recovery",
    )


def validate_multiagent_terminal(
    root_state: str, children: list[tuple[bool, str]], work_order_state: str,
) -> None:
    active_states = {"accepted", "running", "waiting_input", "waiting_approval", "paused", "cancel_requested", "outcome_unknown"}
    if work_order_state in {"completed", "partial", "failed", "cancelled"} and any(
        state in active_states for _, state in children
    ):
        raise AssertionError("Terminal WorkOrder leaves an active Child AgentRun")
    if work_order_state == "completed" and (
        root_state != "succeeded"
        or any(required and state != "succeeded" for required, state in children)
    ):
        raise AssertionError("Completed WorkOrder lacks successful Root and required Child Runs")
    if work_order_state == "cancelled" and (
        root_state not in {"cancelled", "failed"}
        or any(state not in {"cancelled", "failed"} for _, state in children)
    ):
        raise AssertionError("Cancelled WorkOrder lacks terminal evidence for every AgentRun")
    mark_checks("work_order.multiagent_terminal")


def validate_runtime_token(
    token: dict[str, Any], manifest: dict[str, Any], agent_run: dict[str, Any],
    runtime_start: dict[str, Any], operation_document: dict[str, Any] | None = None,
    system_safety_control: dict[str, Any] | None = None,
) -> None:
    authorization = runtime_start["runtime_authorization"]
    operation_document = operation_document or runtime_start
    operation = token["operation"]
    authority_mode = token["authority_mode"]
    if operation not in RUNTIME_OPERATION_CONTRACTS:
        raise AssertionError("Agent Runtime token authorizes an unknown operation")
    contract_id, digest_profile, digest_field = RUNTIME_OPERATION_CONTRACTS[operation]
    if digest_field:
        validate_self_digest(operation_document, digest_field)
        operation_digest = operation_document[digest_field]
    else:
        operation_digest = canonical_digest(operation_document)
    expected = {
        "sub": "spn_agent_runtime_controller",
        "tenant_id": manifest["tenant_id"],
        "runtime_run_id": operation_document["runtime_run_id"],
        "agent_run_id": manifest["agent_run_id"],
        "workflow_run_id": manifest["workflow_run_id"],
        "work_order_id": manifest["work_order_id"],
        "run_manifest_digest": manifest["run_manifest_digest"],
        "runtime_authorization_digest": authorization["authorization_digest"],
        "operation": operation,
        "operation_contract_id": contract_id,
        "operation_digest_profile": digest_profile,
        "operation_request_digest": operation_digest,
        "invocation_id": operation_document["invocation_id"],
        "invocation_attempt_id": operation_document["invocation_attempt_id"],
        "fencing_token": operation_document["fencing_token"],
        "policy_decision_digest": authorization["policy_decision"]["decision_digest"],
        "execution_budget_digest": authorization["execution_budget"]["budget_digest"],
        "effective_permissions_digest": authorization["effective_permissions"]["permissions_digest"],
    }
    for field, value in expected.items():
        if token[field] != value:
            raise AssertionError(f"Agent Runtime token differs from execution context on {field}")
    if not token["iat"] <= token["nbf"] < token["exp"]:
        raise AssertionError("Agent Runtime token operation or lifetime is invalid")
    if operation == "start" and authority_mode != "execution":
        raise AssertionError("Agent Runtime Start requires execution authority")
    if operation in {"read_status", "read_events"} and authority_mode != "safety_control":
        raise AssertionError("Agent Runtime reads require safety-control authority")
    if operation == "submit_command":
        safety_commands = {"cancel", "pause"}
        if (authority_mode == "safety_control") != (operation_document["type"] in safety_commands):
            raise AssertionError("Agent Runtime safety-control authority only permits Cancel or Pause")
        command_uses_system_control = "system_safety_control_id" in operation_document
        token_uses_system_control = "system_safety_control_id" in token
        if command_uses_system_control != token_uses_system_control:
            raise AssertionError("Agent Runtime token and command disagree on SystemSafetyControl authority")
        if command_uses_system_control:
            if system_safety_control is None:
                raise AssertionError("System-issued Runtime command lacks its SystemSafetyControl fact")
            expected_safety_binding = {
                "system_safety_control_id": system_safety_control["safety_control_id"],
                "system_safety_control_digest": system_safety_control["control_digest"],
            }
            if any(token.get(field) != value for field, value in expected_safety_binding.items()):
                raise AssertionError("Agent Runtime token binds a different SystemSafetyControl")
            if datetime.fromtimestamp(token["nbf"], tz=timezone.utc) < parse_datetime(
                system_safety_control["issued_at"]
            ):
                raise AssertionError("Agent Runtime safety token predates SystemSafetyControl issuance")
    elif "system_safety_control_id" in token or "system_safety_control_digest" in token:
        raise AssertionError("Only a system-issued Cancel/Pause command may bind SystemSafetyControl")
    if agent_run["runtime_run_id"] != token["runtime_run_id"]:
        raise AssertionError("Agent Runtime token binds a different AgentRun")
    runtime_resolution = next(
        item for item in manifest["capability_resolutions"]
        if item["resolution_id"] == manifest["agent_runtime"]["resolution_id"]
    )
    if (
        token["provider_revision_id"] != runtime_resolution["selected_provider_revision"]["provider_revision_id"]
        or token["aud"] != runtime_resolution["selected_provider_audience"]
        or token["iss"] != "agent-platform"
    ):
        raise AssertionError("Agent Runtime token binds a different ProviderRevision")
    token_expiry = datetime.fromtimestamp(token["exp"], tz=timezone.utc)
    if token["exp"] - token["iat"] > 300:
        raise AssertionError("Agent Runtime token exceeds its maximum TTL")
    operation_deadline = (
        parse_datetime(operation_document["deadline_at"])
        if "deadline_at" in operation_document else None
    )
    if operation_deadline is not None and token_expiry > operation_deadline:
        raise AssertionError("Agent Runtime token outlives its operation deadline")
    if authority_mode == "execution" and token_expiry > parse_datetime(authorization["expires_at"]):
        raise AssertionError("Agent Runtime execution token outlives RuntimeAuthorization")
    if authority_mode == "execution" and datetime.fromtimestamp(
        token["nbf"], tz=timezone.utc
    ) < parse_datetime(authorization["issued_at"]):
        raise AssertionError("Agent Runtime execution token predates RuntimeAuthorization")
    mark_checks("runtime_token.binding", "runtime_token.lifetime", "runtime_token.audience")


def validate_sandbox_token(
    token: dict[str, Any], operation_document: dict[str, Any], resolution: dict[str, Any],
    manifest: dict[str, Any], *, sandbox_id: str | None = None,
) -> None:
    operation = token["operation"]
    if operation not in SANDBOX_OPERATION_CONTRACTS:
        raise AssertionError("Sandbox token authorizes an unknown operation")
    contract_id, digest_profile = SANDBOX_OPERATION_CONTRACTS[operation]
    if digest_profile == "rfc8785-request-excluding-request-digest-v1":
        validate_self_digest(operation_document, "request_digest")
        expected_request_digest = operation_document["request_digest"]
        expected_deadline = operation_document["deadline_at"]
    else:
        expected_request_digest = canonical_digest(operation_document)
        expected_deadline = token["deadline_at"]
    document_sandbox_id = operation_document.get("sandbox_id")
    if sandbox_id is None:
        sandbox_id = document_sandbox_id or operation_document.get("spec", {}).get("sandbox_id")
    if not sandbox_id or (document_sandbox_id and document_sandbox_id != sandbox_id):
        raise AssertionError("Sandbox operation document crosses its HTTP Sandbox target")
    spec = operation_document.get("spec")
    if spec and (
        spec["sandbox_id"] != sandbox_id
        or spec["tenant_id"] != manifest["tenant_id"]
        or spec["work_order_id"] != manifest["work_order_id"]
    ):
        raise AssertionError("Sandbox mutation spec crosses its admitted execution scope")
    expected = {
        "iss": "agent-platform",
        "sub": "spn_agent_sandbox_controller",
        "aud": resolution["selected_provider_audience"],
        "operation": operation,
        "provider_revision_id": resolution["selected_provider_revision"]["provider_revision_id"],
        "sandbox_id": sandbox_id,
        "operation_id": operation_document["operation_id"],
        "attempt_id": operation_document["attempt_id"],
        "fencing_token": operation_document["fencing_token"],
        "tenant_id": manifest["tenant_id"],
        "work_order_id": manifest["work_order_id"],
        "policy_digest": manifest["policy_decision"]["decision_digest"],
        "request_contract_id": contract_id,
        "request_digest_profile": digest_profile,
        "request_digest": expected_request_digest,
        "deadline_at": expected_deadline,
    }
    if any(token[field] != value for field, value in expected.items()):
        raise AssertionError("Sandbox token differs from its admitted operation")
    if not token["iat"] <= token["nbf"] < token["exp"] or token["exp"] - token["iat"] > 300:
        raise AssertionError("Sandbox token lifetime is invalid")
    if datetime.fromtimestamp(token["exp"], tz=timezone.utc) > parse_datetime(token["deadline_at"]):
        raise AssertionError("Sandbox token outlives its operation deadline")
    if datetime.fromtimestamp(token["nbf"], tz=timezone.utc) < parse_datetime(
        manifest["policy_decision"]["decided_at"]
    ):
        raise AssertionError("Sandbox operation token predates its PolicyDecision")
    mark_checks("sandbox_token.binding", "sandbox_token.lifetime")


def validate_sandbox_spec(
    spec: dict[str, Any], manifest: dict[str, Any], capabilities: dict[str, Any],
) -> None:
    workspace_binding = manifest["workspace_binding"]
    expected_commit_mode = (
        "read_only"
        if workspace_binding["commit_mode"] == "none"
        else "cas_new_revision"
    )
    if (
        spec["tenant_id"] != manifest["tenant_id"]
        or spec["work_order_id"] != manifest["work_order_id"]
        or spec["workspace"]["base_revision_id"]
        != workspace_binding["base_workspace_revision_id"]
        or spec["workspace"]["base_revision_digest"]
        != workspace_binding["base_workspace_revision_digest"]
        or spec["workspace"]["commit_mode"] != expected_commit_mode
        or (
            expected_commit_mode == "cas_new_revision"
            and spec["workspace"]["base_workspace_head_version"]
            != workspace_binding["expected_workspace_head_version"]
        )
    ):
        raise AssertionError("SandboxSpec crosses its admitted WorkOrder or Workspace binding")
    lease_expiry = parse_datetime(spec["lease"]["expires_at"])
    execution_ceiling = min(
        parse_datetime(manifest["commercial_authorization"]["expires_at"]),
        parse_datetime(manifest["execution_budget"]["expires_at"]),
    )
    budget_created_at = parse_datetime(manifest["execution_budget"]["created_at"])
    maximum_lease_expiry = lease_expiry.timestamp() + spec["lease"]["max_extension_seconds"]
    maximum_lease_seconds = maximum_lease_expiry - budget_created_at.timestamp()
    if (
        lease_expiry <= budget_created_at
        or maximum_lease_expiry > execution_ceiling.timestamp()
        or maximum_lease_seconds > manifest["execution_budget"]["limits"]["max_sandbox_seconds"]
    ):
        raise AssertionError("Sandbox lease outlives the admitted execution ceiling")
    resolution = next(
        (item for item in manifest["capability_resolutions"]
         if item["resolution_id"] == spec["provider_resolution_id"]),
        None,
    )
    slot = next(
        (item for item in manifest["sandboxes"]
         if item["sandbox_id"] == spec["sandbox_id"]
         and item["sandbox_slot_key"] == spec["sandbox_slot_key"]),
        None,
    )
    if resolution is None or slot is None:
        raise AssertionError("SandboxSpec references an unadmitted ProviderResolution")
    if (
        resolution["selected_provider_revision"]["provider_revision_id"] != spec["provider_revision_id"]
        or capabilities["provider_revision_id"] != spec["provider_revision_id"]
        or capabilities["api_version"] != slot["provider_api_version"]
        or slot["resolution_id"] != spec["provider_resolution_id"]
        or slot["sandbox_spec_digest"] != canonical_digest(spec)
        or slot["runtime_profile"] != spec["runtime_profile"]
    ):
        raise AssertionError("SandboxSpec differs from its admitted slot or ProviderRevision")
    supported_capabilities = {
        (item["id"], version)
        for item in capabilities["capabilities"]
        for version in item["versions"]
    }
    required_capabilities = {(item["id"], item["version"]) for item in spec["required_capabilities"]}
    if not required_capabilities <= supported_capabilities:
        raise AssertionError("SandboxSpec requires an unsupported Provider capability")
    runtime_profiles = {item["id"] for item in capabilities["runtime_profiles"]}
    limits = capabilities["limits"]
    resource_limits = {
        "cpu_millis": "max_cpu_millis",
        "memory_bytes": "max_memory_bytes",
        "ephemeral_storage_bytes": "max_ephemeral_storage_bytes",
        "workspace_bytes": "max_workspace_bytes",
        "gpu_count": "max_gpu_count",
    }
    if spec["runtime_profile"] not in runtime_profiles or any(
        spec["resources"].get(resource, 0) > limits[limit]
        for resource, limit in resource_limits.items()
    ) or maximum_lease_seconds > limits["max_lease_seconds"]:
        raise AssertionError("SandboxSpec exceeds Provider capabilities")
    egress = manifest["effective_permissions"]["egress"]
    if (
        spec["network"]["mode"] != egress["mode"]
        or spec["network"]["mode"] == "restricted"
        and (not spec["network"].get("policy_reference")
             or spec["network"].get("egress_gateway_required") is not True)
    ):
        raise AssertionError("Sandbox network policy differs from effective permissions")
    mark_checks("sandbox_spec.execution_ceiling", "sandbox_spec.workspace_binding")


def validate_capability_invocation(
    request: dict[str, Any], token: dict[str, Any], resolution: dict[str, Any],
    execution_owner: dict[str, Any], operation_request: dict[str, Any] | None = None,
    predecessor: dict[str, Any] | None = None,
) -> None:
    validate_self_digest(request, "request_digest")
    validate_provider_resolution(resolution)
    for value, digest_field in (
        (request["execution_budget"], "budget_digest"),
        (request["policy_decision"], "decision_digest"),
        (request["effective_permissions"], "permissions_digest"),
        (request["output_staging_grant"], "grant_digest"),
    ):
        validate_self_digest(value, digest_field)
    selected_revision = resolution["selected_provider_revision"]
    if (
        request["provider_resolution_id"] != resolution["resolution_id"]
        or request["provider_instance_id"] != resolution["selected_provider_instance_id"]
        or request["provider_revision_id"] != selected_revision["provider_revision_id"]
        or resolution["tenant_id"] != request["tenant_id"]
        or resolution["client_app_id"] != request["client_app_id"]
        or resolution["execution_scope"] != request["execution_scope"]
        or resolution["capability"] != {
            "id": request["capability"]["id"],
            "version": request["capability"]["version"],
            "profile": request["capability"].get("profile"),
        }
    ):
        raise AssertionError("Capability request differs from its admitted ProviderResolution")
    budget = request["execution_budget"]
    policy = request["policy_decision"]
    permissions = request["effective_permissions"]
    commercial = request["commercial_authorization"]
    expected_execution_scope = request["execution_scope"]
    for component in (budget, policy):
        if (
            component["tenant_id"] != request["tenant_id"]
            or component["execution_scope"] != expected_execution_scope
        ):
            raise AssertionError("Capability executable authorization crosses Tenant or execution scope")
    if permissions["tenant_id"] != request["tenant_id"] or permissions["execution_scope"] != expected_execution_scope:
        raise AssertionError("Capability executable authorization crosses Tenant or execution scope")
    if (
        policy["execution_budget_id"] != budget["budget_id"]
        or policy["execution_budget_digest"] != budget["budget_digest"]
        or policy["effective_permissions_digest"] != permissions["permissions_digest"]
        or policy["commercial_authorization_id"] != commercial["commercial_authorization_id"]
        or policy["commercial_authorization_digest"] != commercial["commercial_authorization_digest"]
    ):
        raise AssertionError("Capability executable Budget, Policy, Permissions or Commercial binding is not closed")
    if expected_execution_scope["kind"] == "work_order":
        if any((
            execution_owner["work_order_id"] != expected_execution_scope["work_order_id"],
            request["execution_owner_request_digest"] != execution_owner["request_binding"]["request_digest"],
        )):
            raise AssertionError("Capability request differs from its WorkOrder admission owner")
        artifact_binding = execution_owner["gateway_bindings"]["artifact"]
    elif expected_execution_scope["kind"] == "artifact_operation":
        operation = execution_owner["artifact_operation"]
        request_context = execution_owner["request_context"]
        if any((
            operation["artifact_operation_id"] != expected_execution_scope["artifact_operation_id"],
            request["execution_owner_request_digest"] != operation["request_digest"],
            request_context["request_digest"] != operation["request_digest"],
            operation["execution_budget_digest"] != budget["budget_digest"],
            operation["policy_decision_digest"] != policy["decision_digest"],
            operation["effective_permissions_digest"] != permissions["permissions_digest"],
            operation["artifact_gateway_binding_digest"]
            != execution_owner["artifact_gateway_binding"]["binding_digest"],
        )):
            raise AssertionError("Capability request differs from its ArtifactOperation admission owner")
        artifact_binding = {
            "mode": "enabled",
            "port": execution_owner["artifact_gateway_binding"],
        }
    else:
        raise AssertionError("ArtifactIngest cannot dispatch through Capability Invocation")
    if any(
        budget["limits"][name] > execution_owner["execution_budget"]["limits"][name]
        for name in budget["limits"]
    ) or not permissions_are_subset(permissions, execution_owner["effective_permissions"]):
        raise AssertionError("Capability executable authorization widens its execution-owner ceiling")
    if request["capability"]["id"] not in permissions["tool"]["allowed_capabilities"]:
        raise AssertionError("Capability is absent from EffectivePermissions")
    request_deadline = parse_datetime(request["deadline_at"])
    authorization_expiry = min(
        parse_datetime(commercial["expires_at"]),
        parse_datetime(budget["expires_at"]),
        parse_datetime(policy["expires_at"]),
    )
    if request_deadline > authorization_expiry:
        raise AssertionError("Capability request deadline outlives executable authorization")

    staging_grant = request["output_staging_grant"]
    if any(
        staging_grant[field] != request[field]
        for field in ("tenant_id", "execution_scope", "invocation_id", "invocation_attempt_id")
    ):
        raise AssertionError("ArtifactStagingGrant crosses its Capability InvocationAttempt")
    if artifact_binding["mode"] != "enabled" or staging_grant["gateway_binding"] != artifact_binding["port"]:
        raise AssertionError("ArtifactStagingGrant uses a Gateway outside the admitted execution owner")
    staging_issued = parse_datetime(staging_grant["issued_at"])
    staging_expires = parse_datetime(staging_grant["expires_at"])
    if staging_expires <= staging_issued or staging_expires > min(request_deadline, parse_datetime(commercial["expires_at"])):
        raise AssertionError("ArtifactStagingGrant has an invalid authorization window")

    operation_profiles = {
        "invoke": (
            "urn:agent-platform:capability-invocation-request:v1",
            "rfc8785-request-excluding-request-digest-v1",
        ),
        "status": (
            "urn:agent-platform:capability-status-operation-descriptor:v1",
            "rfc8785-full-document-v1",
        ),
        "cancel": (
            "urn:agent-platform:capability-cancellation-request:v1",
            "rfc8785-request-excluding-request-digest-v1",
        ),
        "read_events": (
            "urn:agent-platform:capability-event-read-operation-descriptor:v1",
            "rfc8785-full-document-v1",
        ),
    }
    if operation_request is None:
        operation_request = request
    if token["operation"] == "invoke":
        operation_digest = request["request_digest"]
    elif token["operation"] == "cancel":
        validate_self_digest(operation_request, "request_digest")
        operation_digest = operation_request["request_digest"]
    else:
        if operation_request.get("operation") != token["operation"]:
            raise AssertionError("Capability operation descriptor has the wrong operation")
        operation_digest = canonical_digest(operation_request)
    operation_contract_id, operation_digest_profile = operation_profiles[token["operation"]]
    expected = {
        "sub": "spn_agent_capability_dispatcher",
        "aud": resolution["selected_provider_audience"],
        "tenant_id": request["tenant_id"],
        "client_app_id": request["client_app_id"],
        "principal_context_digest": request["principal_context_digest"],
        "execution_scope": request["execution_scope"],
        "provider_resolution_id": request["provider_resolution_id"],
        "provider_instance_id": request["provider_instance_id"],
        "provider_revision_id": request["provider_revision_id"],
        "capability_id": request["capability"]["id"],
        "capability_version": request["capability"]["version"],
        "invocation_id": request["invocation_id"],
        "invocation_attempt_id": request["invocation_attempt_id"],
        "fencing_token": request["fencing_token"],
        "invocation_request_digest": request["request_digest"],
        "operation_contract_id": operation_contract_id,
        "operation_digest_profile": operation_digest_profile,
        "operation_request_digest": operation_digest,
        "policy_decision_digest": policy["decision_digest"],
        "execution_budget_digest": budget["budget_digest"],
        "permissions_digest": permissions["permissions_digest"],
        "staging_grant_digest": staging_grant["grant_digest"],
    }
    for field, value in expected.items():
        if token[field] != value:
            raise AssertionError(f"Capability operation token differs from admitted context on {field}")
    if not token["iat"] <= token["nbf"] < token["exp"] or token["exp"] - token["iat"] > 300:
        raise AssertionError("Capability operation token lifetime is invalid")
    token_expiry = datetime.fromtimestamp(token["exp"], tz=timezone.utc)
    if token["operation"] == "invoke":
        if token["authority_mode"] != "execution" or token_expiry > min(
            request_deadline, parse_datetime(commercial["expires_at"])
        ):
            raise AssertionError("Capability execution token outlives the admitted request")
        execution_not_before = max(
            parse_datetime(policy["decided_at"]),
            parse_datetime(budget["created_at"]),
            parse_datetime(staging_grant["issued_at"]),
            *(parse_datetime(grant["issued_at"]) for grant in request["input_artifact_grants"]),
        )
        if datetime.fromtimestamp(token["nbf"], tz=timezone.utc) < execution_not_before:
            raise AssertionError("Capability execution token predates its admitted authority")
    elif token["authority_mode"] != "safety_control":
        raise AssertionError("Capability control/read operation lacks safety-control authority")
    if token["authorization_sequence"] == 1:
        if predecessor is not None or token["predecessor_jti"] is not None or token["operation"] != "invoke":
            raise AssertionError("Initial Capability token has invalid lineage or operation")
    else:
        if predecessor is None:
            raise AssertionError("Renewed Capability operation token lacks its predecessor")
        if token["authorization_sequence"] != predecessor["authorization_sequence"] + 1:
            raise AssertionError("Capability operation token sequence contains a gap")
        if token["predecessor_jti"] != predecessor["jti"]:
            raise AssertionError("Capability operation token predecessor mismatch")
        invariant_fields = set(expected) - {
            "operation_contract_id", "operation_digest_profile", "operation_request_digest"
        }
        if any(token[field] != predecessor[field] for field in invariant_fields):
            raise AssertionError("Renewed Capability operation token widens or changes Invocation scope")
        target_provider_operation_id = operation_request.get(
            "provider_operation_id", predecessor.get("provider_operation_id")
        )
        if token.get("provider_operation_id") != target_provider_operation_id:
            raise AssertionError("Capability operation token targets a different Provider operation")

    for grant in request["input_artifact_grants"]:
        validate_self_digest(grant, "grant_digest")
        if any(
            grant[field] != request[field] for field in ("invocation_id", "invocation_attempt_id")
        ):
            raise AssertionError("Capability ArtifactGrant crosses its InvocationAttempt")
        if grant["tenant_id"] != request["tenant_id"] or grant["execution_scope"] != request["execution_scope"]:
            raise AssertionError("Capability ArtifactGrant crosses its Tenant or execution scope")
        grant_issued_at = parse_datetime(grant["issued_at"])
        grant_expires_at = parse_datetime(grant["expires_at"])
        if grant_expires_at <= grant_issued_at or grant_expires_at > min(
            request_deadline, parse_datetime(commercial["expires_at"])
        ):
            raise AssertionError("Capability ArtifactGrant has an invalid request window")
        if grant["gateway_binding"] != artifact_binding["port"] or "finalize" in grant["permissions"]:
            raise AssertionError("Capability Provider has invalid Artifact Gateway or finalize authority")
    mark_checks(
        "capability_invocation.request_digest",
        "capability_invocation.owner_request_binding",
        "capability_invocation.resolution_binding",
        "capability_invocation.execution_context",
        "capability_invocation.token_binding",
        "capability_invocation.token_lifetime",
        "capability_invocation.token_lineage",
        "capability_invocation.operation_binding",
        "capability_invocation.artifact_grant_expiry",
        "capability_invocation.staging_grant",
        "artifact_staging_grant.digest",
        "artifact_staging_grant.scope",
        "artifact_staging_grant.expiry",
        "artifact_staging_grant.permissions",
        "artifact_grant.digest",
        "artifact_grant.expiry",
        "artifact_grant.scope",
        "artifact_grant.provider_permissions",
    )


def validate_artifact_gateway(
    staging_grant: dict[str, Any], staging_object: dict[str, Any],
    stage_token: dict[str, Any], staging_commit: dict[str, Any], commit_token: dict[str, Any],
    artifact_grant: dict[str, Any], read_descriptor: dict[str, Any],
    read_token: dict[str, Any], capability_request: dict[str, Any], *, caller_subject: str,
) -> None:
    validate_self_digest(staging_grant, "grant_digest")
    descriptor = copy.deepcopy(staging_object)
    descriptor.pop("request_digest")
    encoded_content = descriptor.pop("content_base64")
    if staging_object["request_digest"] != canonical_digest(descriptor):
        raise AssertionError("Artifact staging object request digest mismatch")
    content = base64.b64decode(encoded_content, validate=True)
    raw_digest = "sha256:" + hashlib.sha256(content).hexdigest()
    if len(content) != staging_object["size_bytes"] or raw_digest != staging_object["digest"]:
        raise AssertionError("Artifact staging object content does not match declared bytes")
    expected_scope = {
        "sub": caller_subject,
        "tenant_id": staging_grant["tenant_id"],
        "execution_scope": staging_grant["execution_scope"],
        "invocation_id": staging_grant["invocation_id"],
        "invocation_attempt_id": staging_grant["invocation_attempt_id"],
        "gateway_binding_digest": staging_grant["gateway_binding"]["binding_digest"],
        "staging_grant_digest": staging_grant["grant_digest"],
    }
    for token, operation_request, operation, contract_id, digest_profile in (
        (
            stage_token, staging_object, "stage_object",
            "urn:agent-platform:artifact-staging-object-request:v1",
            "rfc8785-artifact-stage-metadata-excluding-content-and-request-digest-v1",
        ),
        (
            commit_token, staging_commit, "commit_staging",
            "urn:agent-platform:artifact-staging-commit-request:v1",
            "rfc8785-request-excluding-request-digest-v1",
        ),
    ):
        if (
            token["operation"] != operation
            or token["operation_contract_id"] != contract_id
            or token["operation_digest_profile"] != digest_profile
            or token["aud"] != staging_grant["gateway_binding"]["audience"]
        ):
            raise AssertionError("Artifact Gateway token operation or audience mismatch")
        if any(token[field] != value for field, value in expected_scope.items()):
            raise AssertionError("Artifact Gateway token crosses its StagingGrant scope")
        if token["fencing_token"] != operation_request["fencing_token"]:
            raise AssertionError("Artifact Gateway token fencing differs from the operation")
        if token["request_digest"] != operation_request["request_digest"]:
            raise AssertionError("Artifact Gateway token request digest mismatch")
        if not token["iat"] <= token["nbf"] < token["exp"] or token["exp"] - token["iat"] > 300:
            raise AssertionError("Artifact Gateway token lifetime is invalid")
        if datetime.fromtimestamp(token["exp"], tz=timezone.utc) > parse_datetime(staging_grant["expires_at"]):
            raise AssertionError("Artifact Gateway token outlives its StagingGrant")
        if datetime.fromtimestamp(token["nbf"], tz=timezone.utc) < parse_datetime(staging_grant["issued_at"]):
            raise AssertionError("Artifact Gateway token predates its StagingGrant")
    validate_self_digest(artifact_grant, "grant_digest")
    if (
        artifact_grant["tenant_id"] != capability_request["tenant_id"]
        or artifact_grant["execution_scope"] != capability_request["execution_scope"]
        or artifact_grant["invocation_id"] != capability_request["invocation_id"]
        or artifact_grant["invocation_attempt_id"] != capability_request["invocation_attempt_id"]
    ):
        raise AssertionError("Artifact read Grant crosses its Capability InvocationAttempt")
    expected_read_descriptor = {
        "operation": "read_content",
        "tenant_id": capability_request["tenant_id"],
        "execution_scope": capability_request["execution_scope"],
        "invocation_id": capability_request["invocation_id"],
        "invocation_attempt_id": capability_request["invocation_attempt_id"],
        "fencing_token": capability_request["fencing_token"],
        "artifact_id": artifact_grant["artifact_id"],
        "version_id": artifact_grant["version_id"],
    }
    if read_descriptor != expected_read_descriptor:
        raise AssertionError("Artifact read operation descriptor differs from its ArtifactGrant")
    read_expected = {
        "operation": "read_content",
        "sub": caller_subject,
        "operation_contract_id": "urn:agent-platform:artifact-read-operation-descriptor:v1",
        "operation_digest_profile": "rfc8785-full-document-v1",
        "aud": artifact_grant["gateway_binding"]["audience"],
        "tenant_id": artifact_grant["tenant_id"],
        "execution_scope": artifact_grant["execution_scope"],
        "invocation_id": artifact_grant["invocation_id"],
        "invocation_attempt_id": artifact_grant["invocation_attempt_id"],
        "fencing_token": capability_request["fencing_token"],
        "gateway_binding_digest": artifact_grant["gateway_binding"]["binding_digest"],
        "request_digest": canonical_digest(read_descriptor),
        "artifact_grant_digest": artifact_grant["grant_digest"],
    }
    if "read" not in artifact_grant["permissions"]:
        raise AssertionError("Artifact read requires a Capability ArtifactGrant with read permission")
    if any(read_token[field] != value for field, value in read_expected.items()):
        raise AssertionError("Artifact read token differs from its ArtifactGrant or operation descriptor")
    if not read_token["iat"] <= read_token["nbf"] < read_token["exp"] or read_token["exp"] - read_token["iat"] > 300:
        raise AssertionError("Artifact read token lifetime is invalid")
    if datetime.fromtimestamp(read_token["exp"], tz=timezone.utc) > parse_datetime(artifact_grant["expires_at"]):
        raise AssertionError("Artifact read token outlives its ArtifactGrant")
    if datetime.fromtimestamp(read_token["nbf"], tz=timezone.utc) < parse_datetime(artifact_grant["issued_at"]):
        raise AssertionError("Artifact read token predates its ArtifactGrant")
    validate_self_digest(staging_commit, "request_digest")
    committed = staging_commit["objects"]
    if len(committed) > staging_grant["max_object_count"]:
        raise AssertionError("Artifact staging commit exceeds object-count limit")
    if sum(item["size_bytes"] for item in committed) > staging_grant["max_total_bytes"]:
        raise AssertionError("Artifact staging commit exceeds total-byte limit")
    if any(
        item["media_type"] not in staging_grant["allowed_media_types"]
        or item["size_bytes"] > staging_grant["max_object_bytes"]
        for item in committed
    ):
        raise AssertionError("Artifact staging commit exceeds media or object-byte limits")
    mark_checks("artifact_gateway.operation_binding", "artifact_gateway.token_binding")


def validate_egress_gateway(
    destination: dict[str, Any], request: dict[str, Any], token: dict[str, Any], response: dict[str, Any],
    binding: dict[str, Any], authorization: dict[str, Any], *, caller_subject: str,
) -> None:
    validate_self_digest(destination, "destination_revision_digest")
    validate_self_digest(request, "request_digest")
    destination_binding = {
        field: destination[field]
        for field in (
            "destination_id", "destination_revision_id", "destination_revision_digest",
            "destination_class",
        )
    }
    if any(request[field] != value for field, value in destination_binding.items()):
        raise AssertionError("Egress request binds a different DestinationRevision")
    owner = destination["owner"]
    if (
        owner.get("tenant_id", request["tenant_id"]) != request["tenant_id"]
        or owner.get("client_app_id", request["client_app_id"]) != request["client_app_id"]
    ):
        raise AssertionError("Egress DestinationRevision crosses its owner scope")
    allowed_query_names = set(destination["allowed_query_names"])
    allowed_headers = set(destination["allowed_request_headers"])
    forbidden_headers = {
        "authorization", "connection", "cookie", "host", "proxy-authorization",
        "proxy-connection", "te", "trailer", "transfer-encoding", "upgrade",
    }
    if (
        request["method"] not in destination["allowed_methods"]
        or not any(request["path"].startswith(prefix) for prefix in destination["allowed_path_prefixes"])
        or any(item["name"] not in allowed_query_names for item in request.get("query", []))
        or any(
            item["name"].lower() not in allowed_headers
            or item["name"].lower() in forbidden_headers
            for item in request["headers"]
        )
        or destination["redirect_policy"]["mode"] == "deny"
        and destination["redirect_policy"]["max_redirects"] != 0
    ):
        raise AssertionError("Egress HTTP operation exceeds DestinationRevision policy")
    expected = {
        "sub": caller_subject,
        "aud": binding["audience"],
        "tenant_id": request["tenant_id"],
        "client_app_id": request["client_app_id"],
        "work_order_id": request["work_order_id"],
        "runtime_run_id": request["runtime_run_id"],
        "invocation_id": request["invocation_id"],
        "invocation_attempt_id": request["invocation_attempt_id"],
        "fencing_token": request["fencing_token"],
        "destination_id": request["destination_id"],
        "destination_revision_id": request["destination_revision_id"],
        "destination_revision_digest": request["destination_revision_digest"],
        "destination_class": request["destination_class"],
        "gateway_binding_digest": binding["binding_digest"],
        "operation": "http_exchange",
        "operation_contract_id": "urn:agent-platform:egress-http-request:v1",
        "operation_digest_profile": "rfc8785-request-excluding-request-digest-v1",
        "request_digest": request["request_digest"],
        "policy_decision_digest": authorization["policy_decision"]["decision_digest"],
        "execution_budget_digest": authorization["execution_budget"]["budget_digest"],
        "permissions_digest": authorization["effective_permissions"]["permissions_digest"],
        "runtime_authorization_digest": authorization["authorization_digest"],
    }
    if any(token[field] != value for field, value in expected.items()):
        raise AssertionError("Egress token differs from the admitted HTTP request")
    if not token["iat"] <= token["nbf"] < token["exp"] or token["exp"] - token["iat"] > 300:
        raise AssertionError("Egress token lifetime is invalid")
    if datetime.fromtimestamp(token["exp"], tz=timezone.utc) > parse_datetime(authorization["expires_at"]):
        raise AssertionError("Egress token outlives its RuntimeAuthorization")
    if datetime.fromtimestamp(token["nbf"], tz=timezone.utc) < parse_datetime(authorization["issued_at"]):
        raise AssertionError("Egress token predates its RuntimeAuthorization")
    if request["destination_class"] not in authorization["effective_permissions"]["egress"]["allowed_destination_classes"]:
        raise AssertionError("Egress destination class is absent from EffectivePermissions")
    if any(
        response[field] != request[field]
        for field in ("invocation_id", "invocation_attempt_id", "fencing_token", "request_digest")
    ):
        raise AssertionError("Egress response belongs to a different request")
    mark_checks(
        "egress_destination.digest", "egress_destination.owner_scope",
        "egress_destination.request_policy", "egress_gateway.request_binding",
        "egress_gateway.token_binding",
    )


def validate_workspace_content_manifest(manifest: dict[str, Any]) -> None:
    validate_self_digest(manifest, "manifest_digest")
    paths = [entry["path"] for entry in manifest["entries"]]
    if len(paths) != len(set(paths)):
        raise AssertionError("Workspace Content Manifest contains duplicate paths")
    if any(posixpath.normpath(path) != path or path.startswith("/") or path in {".", ".."} for path in paths):
        raise AssertionError("Workspace Content Manifest contains a non-normalized path")
    if manifest["path_case_policy"] == "case_insensitive" and len({path.casefold() for path in paths}) != len(paths):
        raise AssertionError("Workspace Content Manifest contains a case-colliding path")
    if manifest["entry_count"] != len(manifest["entries"]):
        raise AssertionError("Workspace Content Manifest entry_count mismatch")
    total_bytes = sum(entry.get("size_bytes", 0) for entry in manifest["entries"] if entry["entry_type"] == "file")
    if manifest["total_file_bytes"] != total_bytes:
        raise AssertionError("Workspace Content Manifest total_file_bytes mismatch")
    symlinks = [entry for entry in manifest["entries"] if entry["entry_type"] == "symlink"]
    if manifest["symlink_policy"] == "forbid" and symlinks:
        raise AssertionError("Workspace Content Manifest forbids symlinks")
    symlink_paths = {entry["path"] for entry in symlinks}
    for entry in symlinks:
        target = entry["symlink_target"]
        resolved = posixpath.normpath(posixpath.join(posixpath.dirname(entry["path"]), target))
        if target.startswith("/") or resolved == ".." or resolved.startswith("../"):
            raise AssertionError("Workspace Content Manifest symlink escapes the root")
        target_parts = resolved.split("/")
        prefixes = {"/".join(target_parts[:index]) for index in range(1, len(target_parts) + 1)}
        if prefixes & (symlink_paths - {entry["path"]}):
            raise AssertionError("Workspace Content Manifest symlink traverses another symlink")
    mark_checks(
        "workspace_manifest.digest",
        "workspace_manifest.path_policy",
        "workspace_manifest.counts",
        "workspace_manifest.symlink_policy",
    )


def validate_canonical_event_source(event: dict[str, Any]) -> None:
    expected = canonical_digest({
        "tenant_id": event["tenant_id"],
        "producer_id": event["producer_id"],
        "source_stream_id": event["source_stream_id"],
        "source_event_id": event["source_event_id"],
    })
    if event["dedupe_key"] != expected:
        raise AssertionError("CanonicalEvent dedupe_key does not bind source identity")
    if event["producer_kind"] == "provider":
        if event["provider_revision_id"] is None or event["metadata"].get("provider_instance_id") is None:
            raise AssertionError("Provider-originated CanonicalEvent lacks immutable Provider binding")
    elif event["provider_revision_id"] is not None or event["metadata"].get("provider_instance_id") is not None:
        raise AssertionError("Platform-originated CanonicalEvent carries Provider identity")
    work_fields = {"work_order_id", "turn_id", "branch_id", "input_message_id", "work_sequence"}
    if work_fields & set(event) and not work_fields <= set(event):
        raise AssertionError("CanonicalEvent has a partial executable Work binding")
    scope = event.get("execution_scope")
    aggregate_type = event["aggregate"]["type"]
    if aggregate_type in {"artifact_operation", "artifact_ingest"}:
        expected_kind = aggregate_type
        expected_id_field = {
            "artifact_operation": "artifact_operation_id",
            "artifact_ingest": "artifact_ingest_session_id",
        }[aggregate_type]
        if (
            scope is None
            or scope["kind"] != expected_kind
            or scope[expected_id_field] != event["aggregate"]["id"]
            or work_fields & set(event)
            or "conversation_id" in event
        ):
            raise AssertionError("CanonicalEvent execution scope differs from its non-Work aggregate")
    elif aggregate_type == "secret_grant":
        if scope is None:
            raise AssertionError("SecretGrant event lacks its execution scope")
    elif scope is not None:
        raise AssertionError("CanonicalEvent carries execution scope for an aggregate that does not own it")
    mark_checks(
        "canonical_event.work_binding",
        "canonical_event.execution_scope",
        "canonical_event.source_dedupe",
        "canonical_event.producer_binding",
    )


def validate_artifact_operation_event_binding(
    event: dict[str, Any], operation: dict[str, Any],
) -> None:
    expected_data = {
        "artifact_operation_id": operation["artifact_operation_id"],
        "operation_kind": operation["operation_kind"],
        "state": operation["status"],
        "state_version": operation["state_version"],
        "request_digest": operation["request_digest"],
    }
    for field in (
        "provider_resolution_id", "invocation_id", "invocation_request_digest",
        "cancellation_intent_id", "cancellation_source_kind", "cancellation_source_id",
        "cancellation_source_digest", "cancellation_outbox_message_id",
        "cancellation_requested_at", "cancellation_reconciliation_case_id",
        "terminal_stage", "terminal_evidence_digest",
    ):
        if field in operation:
            expected_data[field] = operation[field]
    if (
        event["aggregate"] != {
            "type": "artifact_operation",
            "id": operation["artifact_operation_id"],
            "sequence": operation["state_version"],
        }
        or event["data"] != expected_data
    ):
        raise AssertionError("ArtifactOperation event differs from its authoritative aggregate state")
    mark_checks("canonical_event.execution_scope")


def validate_canonical_event_registry_binding(
    event: dict[str, Any], registries: list[dict[str, Any]],
) -> None:
    registry = next((candidate for candidate in registries if event["event_registry"] == {
        "registry_id": candidate["registry_id"],
        "registry_version": candidate["registry_version"],
        "registry_digest": candidate["registry_digest"],
    }), None)
    if registry is None:
        raise AssertionError("CanonicalEvent does not bind an admitted core Event Registry revision")
    expected_producer_kind = {
        "platform-core": "platform",
        "agent-runtime-core": "provider",
    }.get(registry["registry_id"])
    if expected_producer_kind is None or event["producer_kind"] != expected_producer_kind:
        raise AssertionError("CanonicalEvent producer does not own the bound core Event Registry")
    definition = next(
        (item for item in registry["definitions"] if item["type"] == event["type"] and item["data_version"] == event["data_version"]),
        None,
    )
    if definition is None:
        raise AssertionError("CanonicalEvent type and data_version are not admitted")
    schema = {"$ref": definition["data_schema"]["uri"]}
    errors = list(
        Draft202012Validator(schema, registry=SCHEMA_REGISTRY, format_checker=FormatChecker())
        .iter_errors(event["data"])
    )
    if errors:
        raise AssertionError("CanonicalEvent data does not validate against the admitted core Event schema")
    mark_checks("canonical_event.registry_binding")


def validate_semantic_traceability(traceability: dict[str, Any]) -> None:
    _c01_partition_traceability(
        CONTRACT_ROOT, traceability, KNOWN_CONTRACT_CHECKS, EXECUTED_CONTRACT_CHECKS,
    )


def validate_work_order_control_contract(request: dict[str, Any]) -> None:
    has_message_cas = "expected_message_head_version" in request
    if request["action"] in {"append_input", "interrupt"}:
        if not has_message_cas or "content" not in request:
            raise AssertionError("Executable control input lacks Message CAS or content")
        if request["content"]["content_digest"] != canonical_digest(request["content"]["content"]):
            raise AssertionError("WorkOrder control content digest mismatch")
        forbidden_internal_ids = {"input_id", "input_message_id"} & set(request["content"])
        if forbidden_internal_ids:
            raise AssertionError("Client WorkOrder control contains Platform-owned input identity")
    elif has_message_cas:
        raise AssertionError("Non-message WorkOrder control incorrectly depends on Message CAS")
    mark_checks("work_order_control.conditional_cas")


def validate_runtime_session_request(
    request: dict[str, Any], manifest: dict[str, Any], authorized_scopes: set[str],
) -> None:
    slots = {item["sandbox_slot_key"] for item in manifest["sandboxes"]}
    if request["sandbox_slot_key"] not in slots:
        raise AssertionError("RuntimeSession selects a Sandbox slot outside the RunManifest")
    requested = set(request.get("requested_scopes", []))
    control_scopes = {"control", "input", "clipboard", "file-transfer"}
    required_scope = "runtime:control" if requested & control_scopes else "runtime:view"
    if required_scope not in authorized_scopes:
        raise AssertionError("RuntimeSession scopes exceed authenticated authorization")
    recording = request["recording"]
    if request["runtime_type"] == "port_forward" and recording["mode"] != "disabled":
        raise AssertionError("Port-forward RuntimeSession cannot be recorded")
    allowed_channels = {
        "terminal": {"terminal", "file_delta"},
        "browser": {"browser", "file_delta"},
        "desktop": {"desktop", "file_delta"},
        "port_forward": set(),
    }[request["runtime_type"]]
    if recording["mode"] == "platform_managed" and not set(recording["channels"]) <= allowed_channels:
        raise AssertionError("RuntimeSession recording channels conflict with runtime_type")
    mark_checks(
        "runtime_session.requested_scope_subset",
        "runtime_session.sandbox_slot_binding",
        "runtime_session.scope_class",
        "runtime_session.channel_policy",
    )


def validate_runtime_session_route(
    route: dict[str, Any], request: dict[str, Any], response: dict[str, Any],
    manifest: dict[str, Any], grant: dict[str, Any],
) -> None:
    digest_input = {
        field: route[field]
        for field in (
            "runtime_session_id", "sandbox_id", "runtime_type", "provider_route_reference"
        )
    }
    if route["provider_route_digest"] != canonical_digest(digest_input):
        raise AssertionError("RuntimeSessionRoute provider route digest mismatch")
    slot = next(
        (item for item in manifest["sandboxes"]
         if item["sandbox_id"] == route["sandbox_id"]
         and item["sandbox_slot_key"] == route["sandbox_slot_key"]),
        None,
    )
    if slot is None or any((
        route["tenant_id"] != manifest["tenant_id"],
        route["client_app_id"] != grant["client_app_id"],
        route["principal_id"] != grant["sub"],
        route["work_order_id"] != manifest["work_order_id"],
        route["runtime_session_id"] != response["runtime_session_id"],
        route["sandbox_slot_key"] != request["sandbox_slot_key"],
        route["runtime_type"] != request["runtime_type"],
        route["connection_generation"] != response["connection_generation"],
        route["expires_at"] != response["expires_at"],
    )):
        raise AssertionError("RuntimeSessionRoute crosses its admitted session scope")
    scope_by_type = {
        "terminal": {"terminal:connect"},
        "browser": {"browser:view", "browser:control"},
        "desktop": {"desktop:view", "desktop:control"},
        "port_forward": {"port-forward:connect"},
    }
    if not set(route["scopes"]) <= scope_by_type[route["runtime_type"]]:
        raise AssertionError("RuntimeSessionRoute contains incompatible scopes")
    if (
        "://" in route["provider_route_reference"]
        or parse_datetime(route["expires_at"]) > min(
            parse_datetime(manifest["commercial_authorization"]["expires_at"]),
            parse_datetime(manifest["execution_budget"]["expires_at"]),
        )
    ):
        raise AssertionError("RuntimeSessionRoute exposes an endpoint or outlives authorization")
    mark_checks(
        "runtime_session.route_digest", "runtime_session.route_scope",
        "runtime_session.route_opaque",
    )


def validate_usage_observations(
    result: dict[str, Any], meter: dict[str, Any], technical_entry: dict[str, Any],
) -> None:
    observations = result["usage"]
    ids = [item["observation_id"] for item in observations]
    if len(ids) != len(set(ids)):
        raise AssertionError("Provider returned duplicate UsageObservation identities")
    platform_owned = {
        "entry_id", "tenant_id", "execution_scope", "work_order_id",
        "recorded_at", "idempotency_key", "producer",
    }
    for observation in observations:
        if platform_owned & set(observation):
            raise AssertionError("Provider UsageObservation contains Platform-owned ledger fields")
        if observation["meter_id"] != meter["meter_id"] or observation["meter_version"] != meter["meter_version"]:
            raise AssertionError("UsageObservation binds a different MeterDefinition")
        if observation["unit"] != meter["base_unit"]:
            raise AssertionError("UsageObservation unit differs from MeterDefinition")
        if observation["evidence_digest"] != canonical_digest({"evidence_reference": observation["evidence_reference"]}):
            raise AssertionError("UsageObservation evidence digest mismatch")
    if observations and technical_entry.get("source_observation_id") not in set(ids):
        raise AssertionError("Platform TechnicalUsageEntry does not bind a validated UsageObservation")
    source = next(
        (item for item in observations if item["observation_id"] == technical_entry.get("source_observation_id")),
        None,
    )
    if source is not None and any(
        technical_entry[field] != source[field]
        for field in ("meter_id", "meter_version", "quantity", "unit", "measurement_status", "occurred_at")
    ):
        raise AssertionError("Platform TechnicalUsageEntry changes Provider observation semantics")
    mark_checks(
        "usage_observation.observation_identity",
        "usage_observation.incomplete_status",
        "usage_observation.provider_boundary",
        "usage_observation.meter_and_evidence",
    )


def validate_gateway_frames(connect: dict[str, Any], control: dict[str, Any]) -> None:
    channels = [cursor["channel"] for cursor in connect["resume_cursors"]]
    if len(channels) != len(set(channels)):
        raise AssertionError("Runtime Gateway resume cursors contain duplicate channels")
    control_payload = {
        field: control[field]
        for field in ("command", "columns", "rows", "text", "key", "url")
        if field in control
    }
    if control["control_digest"] != canonical_digest(control_payload):
        raise AssertionError("Runtime Gateway control_digest does not bind the command payload")
    if connect["runtime_session_id"] != control["runtime_session_id"] or connect["connection_generation"] != control["connection_generation"]:
        raise AssertionError("Runtime Gateway frames belong to different session generations")
    mark_checks("runtime_gateway.frame_integrity")


def validate_event_registry(registry: dict[str, Any]) -> None:
    validate_self_digest(registry, "registry_digest")
    if registry["registry_id"] == "agent-runtime-core":
        root = load("schemas/agent-runtime-event-data.schema.json")
        dependencies = sorted(
            [
                load("schemas/capability-error.schema.json"),
                load("schemas/child-agent-run-spawn-request.schema.json"),
                load("schemas/runtime-input-envelope.schema.json"),
                load("schemas/runtime-input-content.schema.json"),
                load("schemas/usage-observation.schema.json"),
            ],
            key=lambda schema: schema["$id"],
        )
        uri_prefix = "urn:agent-platform:agent-runtime-event-data:v1#/$defs/"
    elif registry["registry_id"] == "platform-core":
        root = load("schemas/platform-core-event-data.schema.json")
        dependencies = [load("schemas/work-order-state.schema.json")]
        uri_prefix = "urn:agent-platform:platform-core-event-data:v1#/$defs/"
    else:
        raise AssertionError("Unknown EventTypeRegistry ownership domain")
    expected_schema_digest = canonical_digest({
        "root": root,
        "dependencies": dependencies,
    })
    keys: set[tuple[str, int]] = set()
    for definition in registry["definitions"]:
        key = (definition["type"], definition["data_version"])
        if key in keys:
            raise AssertionError("EventTypeRegistry contains duplicate type plus data_version")
        keys.add(key)
        if definition["data_schema"]["digest"] != expected_schema_digest:
            raise AssertionError("EventTypeRegistry data schema digest is not admitted")
        if definition["data_schema"]["digest_profile"] != "rfc8785-schema-closure-v1":
            raise AssertionError("EventTypeRegistry uses an unsupported Schema closure digest profile")
        if not definition["data_schema"]["uri"].startswith(uri_prefix):
            raise AssertionError("Core event points outside its admitted payload registry")
        fragment = definition["data_schema"]["uri"].removeprefix(uri_prefix)
        if fragment not in root.get("$defs", {}):
            raise AssertionError("EventTypeRegistry points at a missing payload definition")


def validate_usage_contracts(
    meter: dict[str, Any], entry: dict[str, Any], report: dict[str, Any], settlement: dict[str, Any],
    execution_owner: dict[str, Any] | None = None,
) -> None:
    validate_self_digest(meter, "definition_digest")
    validate_self_digest(report, "usage_report_digest")
    validate_self_digest(settlement, "settlement_envelope_digest")
    if entry["meter_id"] != meter["meter_id"] or entry["meter_version"] != meter["meter_version"]:
        raise AssertionError("TechnicalUsageEntry binds a different MeterDefinition")
    if entry["meter_definition_digest"] != meter["definition_digest"] or entry["unit"] != meter["base_unit"]:
        raise AssertionError("TechnicalUsageEntry Meter digest or unit mismatch")
    if parse_datetime(entry["recorded_at"]) < parse_datetime(entry["occurred_at"]):
        raise AssertionError("TechnicalUsageEntry was recorded before it occurred")
    if entry["execution_scope"]["kind"] == "artifact_operation":
        if execution_owner is None:
            raise AssertionError("ArtifactOperation usage lacks its execution owner evidence")
        operation = execution_owner["operation"]
        invocation = execution_owner["invocation"]
        resolution = execution_owner["resolution"]
        selected_revision = resolution["selected_provider_revision"]
        if any((
            entry["execution_scope"]["artifact_operation_id"] != operation["artifact_operation_id"],
            entry.get("invocation_id") != invocation["invocation_id"],
            invocation["execution_scope"] != entry["execution_scope"],
            entry["producer"].get("provider_revision_id") != selected_revision["provider_revision_id"],
            entry["producer"].get("provider_revision_digest") != selected_revision["provider_revision_digest"],
        )):
            raise AssertionError("ArtifactOperation usage differs from its Invocation or ProviderRevision")
    if any(
        item["tenant_id"] != report["tenant_id"]
        or item["execution_scope"] != report["execution_scope"]
        for item in report["entries"]
    ):
        raise AssertionError("UsageReport contains cross-tenant or cross-execution-scope entries")
    if len({item["entry_id"] for item in report["entries"]}) != len(report["entries"]):
        raise AssertionError("UsageReport contains duplicate entry IDs")
    if report["report_status"] == "final" and any(item["measurement_status"] not in {"confirmed", "corrected"} for item in report["entries"]):
        raise AssertionError("Final UsageReport cannot silently settle partial or estimated usage")
    if report["report_status"] == "correction" and any(item["measurement_status"] != "corrected" for item in report["entries"]):
        raise AssertionError("Correction UsageReport contains non-correction entries")
    if settlement.get("usage_report") != report:
        raise AssertionError("BusinessSettlementEnvelope binds a different UsageReport")
    for field in (
        "tenant_id", "execution_scope", "commercial_authorization_id",
        "commercial_authorization_digest", "quota_reservation_id", "quota_reservation_digest",
    ):
        if settlement[field] != report[field]:
            raise AssertionError(f"Settlement and UsageReport differ on {field}")
    if settlement["action"] != "settle" or report["report_status"] != "final":
        raise AssertionError("Initial usage settlement must embed a final UsageReport")
    mark_checks(
        "technical_usage.binding",
        "usage_report.finality",
        "settlement.accounting",
    )


def validate_policy_decision(decision: dict[str, Any]) -> None:
    validate_self_digest(decision, "decision_digest")
    actions = {item["action"] for item in decision["evaluations"]}
    expected = "deny" if "deny" in actions else "approval_required" if "ask" in actions else "allow"
    if decision["outcome"] != expected:
        raise AssertionError("PolicyDecision does not resolve deny greater than ask greater than allow")
    if datetime.fromisoformat(decision["expires_at"].replace("Z", "+00:00")) <= datetime.fromisoformat(decision["decided_at"].replace("Z", "+00:00")):
        raise AssertionError("PolicyDecision expires_at must be later than decided_at")
    mark_checks("policy_decision.outcome_time")


def validate_artifact_operation(
    request: dict[str, Any], operation: dict[str, Any], budget: dict[str, Any],
    policy: dict[str, Any], permissions: dict[str, Any], resolution: dict[str, Any],
    invocation: dict[str, Any], provider_request: dict[str, Any],
) -> None:
    context = request["operation_context"]
    unsigned_request = copy.deepcopy(request)
    unsigned_request["operation_context"].pop("request_digest")
    if context["request_digest"] != canonical_digest(unsigned_request):
        raise AssertionError("Artifact operation request digest mismatch")
    validate_self_digest(context["principal_context"], "principal_context_digest")
    for value, digest_field in (
        (budget, "budget_digest"),
        (policy, "decision_digest"),
        (permissions, "permissions_digest"),
        (resolution, "decision_digest"),
    ):
        validate_self_digest(value, digest_field)
    scope = {
        "kind": "artifact_operation",
        "artifact_operation_id": operation["artifact_operation_id"],
    }
    if any(component["execution_scope"] != scope for component in (
        budget, policy, permissions, resolution,
    )):
        raise AssertionError("Artifact operation authorization or ProviderResolution crosses execution scope")
    artifact_gateway_binding = provider_request["output_staging_grant"]["gateway_binding"]
    requested_at = parse_datetime(context["requested_at"])
    commercial_expires_at = parse_datetime(context["commercial_authorization"]["expires_at"])
    if any((
        context["operation_kind"] != operation["operation_kind"],
        context["tenant_id"] != operation["tenant_id"],
        context["client_app_id"] != operation["client_app_id"],
        context["principal_context"]["client_app_id"] != context["client_app_id"],
        context["principal_context"]["principal_context_digest"] != operation["principal_context_digest"],
        context["artifact_id"] != operation["artifact_id"],
        context["source_version_id"] != operation["source_version_id"],
        context["source_version_digest"] != operation["source_version_digest"],
        context["request_digest"] != operation["request_digest"],
        context["commercial_authorization"]["commercial_authorization_id"] != operation["commercial_authorization_id"],
        context["commercial_authorization"]["commercial_authorization_digest"] != operation["commercial_authorization_digest"],
        context["quota_reservation_id"] != operation["quota_reservation_id"],
        context["quota_reservation_digest"] != operation["quota_reservation_digest"],
        operation["policy_decision_id"] != policy["decision_id"],
        operation["policy_decision_digest"] != policy["decision_digest"],
        operation["execution_budget_id"] != budget["budget_id"],
        operation["execution_budget_digest"] != budget["budget_digest"],
        operation["effective_permissions_id"] != permissions["permissions_id"],
        operation["effective_permissions_digest"] != permissions["permissions_digest"],
        operation["artifact_gateway_binding_digest"] != artifact_gateway_binding["binding_digest"],
        budget["tenant_id"] != context["tenant_id"],
        permissions["tenant_id"] != context["tenant_id"],
        policy["tenant_id"] != context["tenant_id"],
        policy["execution_budget_id"] != budget["budget_id"],
        policy["execution_budget_digest"] != budget["budget_digest"],
        policy["effective_permissions_digest"] != permissions["permissions_digest"],
        policy["commercial_authorization_id"] != context["commercial_authorization"]["commercial_authorization_id"],
        policy["commercial_authorization_digest"] != context["commercial_authorization"]["commercial_authorization_digest"],
        parse_datetime(budget["created_at"]) < requested_at,
        parse_datetime(policy["decided_at"]) < requested_at,
        parse_datetime(budget["expires_at"]) > commercial_expires_at,
        parse_datetime(policy["expires_at"]) > commercial_expires_at,
    )):
        raise AssertionError("Artifact operation ownership or authorization binding is not closed")
    selected_revision = resolution["selected_provider_revision"]["provider_revision_id"]
    validate_self_digest(provider_request, "request_digest")
    if any((
        resolution["tenant_id"] != context["tenant_id"],
        resolution["client_app_id"] != context["client_app_id"],
        resolution["principal_context_digest"] != context["principal_context"]["principal_context_digest"],
        resolution["capability"] != context["capability"],
        operation["provider_resolution_id"] != resolution["resolution_id"],
        operation["provider_revision_id"] != selected_revision,
        invocation["execution_scope"] != scope,
        invocation["artifact_operation_id"] != operation["artifact_operation_id"],
        invocation["request_digest"] != operation["invocation_request_digest"],
        invocation["provider_resolution_id"] != resolution["resolution_id"],
        invocation["provider_revision_id"] != selected_revision,
        invocation["invocation_id"] != operation["invocation_id"],
        provider_request["execution_scope"] != scope,
        provider_request["execution_owner_request_digest"] != operation["request_digest"],
        provider_request["invocation_id"] != invocation["invocation_id"],
        provider_request["provider_resolution_id"] != resolution["resolution_id"],
        provider_request["provider_revision_id"] != selected_revision,
        provider_request["request_digest"] != invocation["request_digest"],
        provider_request["commercial_authorization"] != context["commercial_authorization"],
        provider_request["execution_budget"] != budget,
        provider_request["policy_decision"] != policy,
        provider_request["effective_permissions"] != permissions,
        any(
            grant["gateway_binding"] != artifact_gateway_binding
            for grant in provider_request["input_artifact_grants"]
        ),
    )):
        raise AssertionError("Artifact operation ProviderResolution or Invocation binding is not closed")
    if operation["status"] == "succeeded" and (
        invocation["status"] != "succeeded"
        or operation.get("result_reference") != invocation.get("result_reference")
        or not operation.get("terminal_evidence_digest")
    ):
        raise AssertionError("Successful ArtifactOperation lacks immutable Invocation evidence")
    mark_checks("artifact_operation.binding")


def validate_artifact_operation_terminal_shape(operation: dict[str, Any]) -> None:
    provider_fields = {"provider_resolution_id", "provider_revision_id"}
    invocation_fields = {"invocation_id", "invocation_request_digest"}
    stage = operation.get("terminal_stage")
    if stage == "admission" and (provider_fields | invocation_fields) & set(operation):
        raise AssertionError("Admission-terminal ArtifactOperation fabricates execution facts")
    if stage in {"resolution", "dispatch"} and invocation_fields & set(operation):
        raise AssertionError("Pre-dispatch ArtifactOperation fabricates Invocation facts")
    if stage in {"execution", "finalization"} and not (
        provider_fields | invocation_fields
    ) <= set(operation):
        raise AssertionError("Dispatched ArtifactOperation lacks immutable execution facts")
    if operation["status"] == "succeeded" and stage != "finalization":
        raise AssertionError("Successful ArtifactOperation bypasses Platform finalization")
    mark_checks("artifact_operation.binding")


def validate_artifact_operation_cancellation_binding(
    operation: dict[str, Any], receipt: dict[str, Any], invocation: dict[str, Any] | None,
) -> None:
    cancellation_states = {
        "cancel_requested", "cancelling", "cancellation_reconciling", "cancelled",
    }
    if operation["status"] not in cancellation_states:
        raise AssertionError("ArtifactOperation cancellation evidence is attached to a non-cancellation state")
    target_scope = {
        "kind": "artifact_operation",
        "artifact_operation_id": operation["artifact_operation_id"],
    }
    targets = [
        item for item in receipt["execution_cancellation_targets"]
        if item["execution_scope"] == target_scope
    ]
    if len(targets) != 1:
        raise AssertionError("ArtifactOperation cancellation does not resolve one receipt target")
    target = targets[0]
    if any((
        operation["cancellation_source_kind"]
        != "commercial_authorization_revocation_receipt",
        operation["cancellation_source_id"] != receipt["revocation_receipt_id"],
        operation["cancellation_source_digest"] != receipt["revocation_receipt_digest"],
        operation["cancellation_intent_id"] != target["cancellation_intent_id"],
        operation["cancellation_outbox_message_id"] != target["outbox_message_id"],
        parse_datetime(operation["cancellation_requested_at"])
        < parse_datetime(receipt["accepted_at"]),
    )):
        raise AssertionError("ArtifactOperation cancellation is not bound to its durable receipt intent")
    if operation["status"] == "cancel_requested" and (
        operation["state_version"] != target["expected_owner_state_version"] + 1
    ):
        raise AssertionError("ArtifactOperation cancel_requested did not consume the receipt CAS version")
    if operation["status"] in {"cancelling", "cancellation_reconciling"} and not {
        "provider_resolution_id", "provider_revision_id", "invocation_id",
        "invocation_request_digest",
    } <= set(operation):
        raise AssertionError("Dispatched ArtifactOperation cancellation lost its Invocation binding")
    if invocation is not None:
        expected_scope = {
            "kind": "artifact_operation",
            "artifact_operation_id": operation["artifact_operation_id"],
        }
        if any((
            operation.get("invocation_id") != invocation["invocation_id"],
            operation.get("invocation_request_digest") != invocation["request_digest"],
            operation.get("provider_resolution_id") != invocation["provider_resolution_id"],
            operation.get("provider_revision_id") != invocation["provider_revision_id"],
            invocation["execution_scope"] != expected_scope,
        )):
            raise AssertionError("ArtifactOperation cancellation crosses its Invocation ledger")
        allowed_invocation_states = {
            "cancel_requested": {
                "executing", "outcome_unknown", "reconciling", "manual_review",
                "cancel_requested", "cancellation_confirmed",
            },
            "cancelling": {"cancel_requested", "cancellation_confirmed"},
            "cancellation_reconciling": {"outcome_unknown", "reconciling", "manual_review"},
            "cancelled": {"cancelled"},
        }[operation["status"]]
        if invocation["status"] not in allowed_invocation_states:
            raise AssertionError("ArtifactOperation cancellation conflicts with Invocation state")
        if operation["status"] == "cancellation_reconciling" and (
            operation["cancellation_reconciliation_case_id"]
            != invocation.get("reconciliation_case_id")
        ):
            raise AssertionError("ArtifactOperation cancellation uses another Invocation reconciliation case")
    elif "invocation_id" in operation:
        raise AssertionError("Dispatched ArtifactOperation cancellation lacks its Invocation evidence")
    if operation["status"] == "cancellation_reconciling" and not operation.get(
        "cancellation_reconciliation_case_id"
    ):
        raise AssertionError("Unknown ArtifactOperation cancellation lacks a reconciliation case")
    mark_checks("artifact_operation.cancellation")


def validate_conversation_branch_create(
    request: dict[str, Any], created: dict[str, Any],
    source_branch: dict[str, Any] | None, source_message: dict[str, Any] | None,
    source_workspace: dict[str, Any],
) -> None:
    validate_self_digest(request, "request_digest")
    branch = created["branch"]
    created_workspace = created["workspace_revision"]
    validate_self_digest(created_workspace, "revision_digest")
    if created_workspace["revision_number"] == 1 and created_workspace["parent_revision_id"] is not None:
        raise AssertionError("Initial branch WorkspaceRevision cannot have a parent")
    if any((
        created["branch_request_id"] != request["branch_request_id"],
        created["request_digest"] != request["request_digest"],
        branch["conversation_id"] != request["conversation_id"],
        branch["branch_id"] != request["branch_id"],
        created_workspace["branch_id"] != request["branch_id"],
        created_workspace["revision_number"] != 1,
        created_workspace["parent_revision_id"] is not None,
        branch["workspace_head_revision_id"] != created_workspace["workspace_revision_id"],
        branch["workspace_head_revision_digest"] != created_workspace["revision_digest"],
        branch["active_work_order_id"] is not None,
        any(branch[field] != 1 for field in (
            "message_head_version", "workspace_head_version", "active_work_version", "branch_version"
        )),
    )):
        raise AssertionError("Created branch and branch-scoped WorkspaceRevision were not committed atomically")
    if request["mode"] == "fork":
        if source_branch is None or source_message is None:
            raise AssertionError("Fork validation lacks its immutable source cut")
        if any((
            request["conversation_id"] != source_branch["conversation_id"],
            request["source_branch_id"] != source_branch["branch_id"],
            request["source_message_id"] != source_branch["head_message_id"],
            request["source_message_sequence"] != source_branch["head_message_sequence"],
            request["source_message_head_version"] != source_branch["message_head_version"],
            request["source_workspace_revision_id"] != source_branch["workspace_head_revision_id"],
            request["source_workspace_revision_digest"] != source_branch["workspace_head_revision_digest"],
            request["source_workspace_head_version"] != source_branch["workspace_head_version"],
            source_message["message_id"] != request["source_message_id"],
            source_message["message_sequence"] != request["source_message_sequence"],
            source_workspace["workspace_revision_id"] != request["source_workspace_revision_id"],
            source_workspace["revision_digest"] != request["source_workspace_revision_digest"],
            created_workspace.get("forked_from_revision_id") != source_workspace["workspace_revision_id"],
            branch["forked_from_branch_id"] != request["source_branch_id"],
            branch["forked_from_message_id"] != request["source_message_id"],
            branch["head_message_id"] != request["source_message_id"],
            branch["head_message_sequence"] != request["source_message_sequence"],
        )):
            raise AssertionError("Conversation branch fork source cut or CAS is stale")
    elif request["mode"] == "create":
        if source_workspace["revision_number"] != 1 or source_workspace["parent_revision_id"] is not None:
            raise AssertionError("Empty branch create does not use the Conversation initial WorkspaceRevision")
        if any((
            branch["head_message_id"] is not None,
            branch["head_message_sequence"] != 0,
            "forked_from_branch_id" in branch,
            "forked_from_message_id" in branch,
            created_workspace.get("forked_from_revision_id") != source_workspace["workspace_revision_id"],
        )):
            raise AssertionError("Empty branch create inherited a Message or invalid Workspace cut")
    else:
        raise AssertionError("Conversation branch create uses an unknown mode")
    mark_checks("conversation_branch.create", "conversation_branch.created_workspace")


def validate_no_usage_accounting(
    attestation: dict[str, Any], delivery: dict[str, Any] | None, release: dict[str, Any],
    dispatched_attempt_count: int, technical_usage_entries: list[dict[str, Any]],
    expected_terminal_status: str | None = None,
) -> None:
    validate_self_digest(attestation, "attestation_digest")
    validate_self_digest(release, "settlement_envelope_digest")
    if dispatched_attempt_count != 0 or technical_usage_entries:
        raise AssertionError("NoUsageAttestation conflicts with dispatch or TechnicalUsage evidence")
    if delivery is not None and delivery["usage_accounting"] != {
        "kind": "confirmed_no_usage",
        "no_usage_attestation": attestation,
    }:
        raise AssertionError("DeliveryPackage does not bind the confirmed NoUsageAttestation")
    if release["action"] != "release" or release.get("no_usage_attestation") != attestation or "usage_report" in release:
        raise AssertionError("No-usage terminal did not produce an explicit release envelope")
    for field in (
        "execution_scope", "commercial_authorization_id", "commercial_authorization_digest",
        "quota_reservation_id", "quota_reservation_digest",
    ):
        if release[field] != attestation[field]:
            raise AssertionError(f"NoUsageAttestation and release differ on {field}")
    scope = attestation["execution_scope"]
    if delivery is not None and (
        release["tenant_id"] != attestation["tenant_id"]
        or release["terminal_status"] != delivery["status"]
        or scope["kind"] != "work_order"
        or delivery["work_order_id"] != scope["work_order_id"]
    ):
        raise AssertionError("No-usage delivery crosses Tenant, terminal state or WorkOrder scope")
    if delivery is None and (
        scope["kind"] == "work_order"
        or release["tenant_id"] != attestation["tenant_id"]
        or release["terminal_status"] != expected_terminal_status
    ):
        raise AssertionError("No-usage release crosses Tenant, terminal state or execution scope")
    mark_checks("no_usage.accounting", "settlement.accounting")


def validate_compatibility_decision(
    subject: dict[str, Any], decision: dict[str, Any], suite: dict[str, Any],
    bound_restore: dict[str, Any] | None = None,
) -> None:
    validate_self_digest(decision, "decision_digest")
    profiles = {profile["profile_id"] for profile in suite["profiles"]}
    evidence = decision["evidence"]
    for item in evidence:
        validate_self_digest(item, "evidence_digest")
    expected_subject_id = subject["checkpoint_id"] if decision["subject_kind"] == "runtime_checkpoint" else subject["snapshot_id"]
    expected_subject_digest = subject["digest"]
    source_provider_revision_id = (
        subject["provider_revision_id"]
        if "provider_revision_id" in subject
        else subject["source_provider_revision_id"]
    )
    required_profile = subject["compatibility_profile"]
    if any((
        decision["subject_id"] != expected_subject_id,
        decision["subject_digest"] != expected_subject_digest,
        decision["source_provider_revision_id"] != source_provider_revision_id,
        decision["source_runtime_revision"] != subject["source_runtime_revision"],
        decision["compatibility_profile"] != required_profile,
        required_profile not in profiles,
    )):
        raise AssertionError("CompatibilityDecision does not bind the exact subject and profile")
    exact_evidence = all(
        item["subject_kind"] == decision["subject_kind"]
        and item["source_provider_revision_id"] == decision["source_provider_revision_id"]
        and item["source_runtime_revision"] == decision["source_runtime_revision"]
        and item["target_provider_revision_id"] == decision["target_provider_revision_id"]
        and item["target_runtime_revision"] == decision["target_runtime_revision"]
        and item["suite_id"] == suite["suite_id"]
        and item["suite_version"] == suite["suite_version"]
        and item["suite_digest"] == suite["suite_digest"]
        and item["profile_id"] == required_profile
        and item["result"] == "passed"
        for item in evidence
    )
    if decision["result"] == "compatible" and (not evidence or not exact_evidence):
        raise AssertionError("Compatible decision lacks exact passed immutable Suite evidence")
    if bound_restore is not None and any((
        bound_restore["target_provider_revision_id"] != decision["target_provider_revision_id"],
        bound_restore["target_runtime_revision"] != decision["target_runtime_revision"],
        bound_restore["compatibility_decision"] != decision,
        decision["result"] != "compatible",
    )):
        raise AssertionError("Restore does not fail closed on its exact CompatibilityDecision")
    mark_checks("compatibility.fail_closed")


def validate_secret_mediation(
    grant: dict[str, Any], request: dict[str, Any], token: dict[str, Any],
    delivery: dict[str, Any], authenticated_sender: str, used_at: datetime,
    target_binding: dict[str, Any],
    revocation: dict[str, Any] | None = None,
) -> None:
    validate_self_digest(grant, "secret_grant_digest")
    validate_self_digest(request, "request_digest")
    issued_at = parse_datetime(grant["issued_at"])
    expires_at = parse_datetime(grant["expires_at"])
    if not issued_at < expires_at or (expires_at - issued_at).total_seconds() > 300:
        raise AssertionError("SecretGrant lifetime is invalid")
    if any(grant["persistence_policy"].values()) or grant["max_uses"] != 1:
        raise AssertionError("SecretGrant permits credential persistence or multiple use")
    if authenticated_sender != grant["workload_identity"] or grant["sender_constraint"]["subject"] != authenticated_sender:
        raise AssertionError("SecretGrant sender constraint mismatch")
    if any((
        request["secret_grant_id"] != grant["secret_grant_id"],
        request["secret_grant_digest"] != grant["secret_grant_digest"],
        request["secret_reference_ids"] != grant["secret_reference_ids"],
        request["target"] != grant["target"],
        request["purpose"] != grant["purpose"],
    )):
        raise AssertionError("CredentialAccessRequest widens or changes its SecretGrant")
    target_request = target_binding["request"]
    validate_self_digest(target_request, "request_digest")
    target_kind = grant["target"]["target_kind"]
    target_profiles = {
        "sandbox_exec": (
            "operation_id",
            "urn:agent-platform:sandbox-exec-request:v1",
            "rfc8785-sandbox-exec-intent-excluding-secret-grant-and-request-digest-v1",
        ),
        "capability_invocation": (
            "invocation_id",
            "urn:agent-platform:capability-invocation-request:v1",
            "rfc8785-capability-intent-excluding-secret-grant-and-request-digest-v1",
        ),
    }
    if target_kind not in target_profiles:
        raise AssertionError("SecretGrant targets an unsupported Phase 0 execution operation")
    target_id_field, contract_id, digest_profile = target_profiles[target_kind]
    target_intent = copy.deepcopy(target_request)
    for field in ("request_digest", "secret_reference_ids", "secret_grant_id", "secret_grant_digest"):
        target_intent.pop(field, None)
    target_intent_digest = canonical_digest(target_intent)
    if any((
        target_request.get("secret_reference_ids") != grant["secret_reference_ids"],
        target_request.get("secret_grant_id") != grant["secret_grant_id"],
        target_request.get("secret_grant_digest") != grant["secret_grant_digest"],
        grant["target"]["target_id"] != target_request[target_id_field],
        grant["target"]["target_digest"] != target_intent_digest,
        grant["target_request_contract_id"] != contract_id,
        grant["target_request_digest_profile"] != digest_profile,
        grant["target_request_digest"] != target_intent_digest,
        grant["tenant_id"] != target_binding["tenant_id"],
        grant["principal_context_digest"] != target_binding["principal_context_digest"],
        grant["execution_scope"] != target_binding["execution_scope"],
        grant["provider_instance_id"] != target_binding["provider_instance_id"],
        grant["provider_revision_id"] != target_binding["provider_revision_id"],
        grant["provider_audience"] != target_binding["provider_audience"],
        grant["workload_identity"] != target_binding["workload_identity"],
        expires_at > parse_datetime(target_binding["deadline_at"]),
    )):
        raise AssertionError("SecretGrant differs from its admitted target operation")
    if any((
        token["sub"] != authenticated_sender,
        token["aud"] != "urn:agent-platform:credential-gateway:primary",
        token["tenant_id"] != grant["tenant_id"],
        token["secret_grant_id"] != grant["secret_grant_id"],
        token["secret_grant_digest"] != grant["secret_grant_digest"],
        token["operation"] != "credential_access",
        token["request_contract_id"] != "urn:agent-platform:credential-access-request:v1",
        token["request_digest_profile"] != "rfc8785-request-excluding-request-digest-v1",
        token["request_digest"] != request["request_digest"],
        not token["iat"] <= token["nbf"] < token["exp"],
        token["exp"] - token["iat"] > 300,
        datetime.fromtimestamp(token["nbf"], tz=timezone.utc) < issued_at,
        datetime.fromtimestamp(token["exp"], tz=timezone.utc) > expires_at,
        used_at < issued_at or used_at >= expires_at,
    )):
        raise AssertionError("Credential token is not bound to one admitted SecretGrant operation")
    delivery_expiry = parse_datetime(delivery["expires_at"])
    if any((
        delivery["credential_request_id"] != request["credential_request_id"],
        delivery["delivery_mode"] != grant["purpose"],
        not delivery.get("audit_event_id"),
        delivery_expiry > expires_at,
        used_at >= delivery_expiry,
    )):
        raise AssertionError("Credential delivery is not bounded and audited before material release")
    if revocation is not None:
        validate_self_digest(revocation, "revocation_digest")
        if (
            revocation["secret_grant_id"] == grant["secret_grant_id"]
            and parse_datetime(revocation["revoked_at"]) <= used_at
        ):
            raise AssertionError("Revoked SecretGrant was accepted")
    mark_checks("secret_mediation.binding")


def validate_artifact_ingest(
    request: dict[str, Any], session: dict[str, Any], budget: dict[str, Any],
    policy: dict[str, Any], permissions: dict[str, Any], scan: dict[str, Any],
    finalize: dict[str, Any],
) -> None:
    validate_self_digest(request, "request_digest")
    validate_self_digest(budget, "budget_digest")
    validate_self_digest(policy, "decision_digest")
    validate_self_digest(permissions, "permissions_digest")
    validate_self_digest(scan, "scan_result_digest")
    validate_self_digest(finalize, "command_digest")
    principal_digest = request["principal_context"]["principal_context_digest"]
    scope = {
        "kind": "artifact_ingest",
        "artifact_ingest_session_id": session["ingest_session_id"],
    }
    if any((
        request["tenant_id"] != session["tenant_id"],
        request["client_app_id"] != session["client_app_id"],
        principal_digest != session["principal_context_digest"],
        request["artifact_id"] != session["artifact_id"],
        request["request_digest"] != session["request_digest"],
        request["commercial_authorization"]["commercial_authorization_id"] != session["commercial_authorization_id"],
        request["commercial_authorization"]["commercial_authorization_digest"] != session["commercial_authorization_digest"],
        session["policy_decision_id"] != policy["decision_id"],
        session["policy_decision_digest"] != policy["decision_digest"],
        session["execution_budget_id"] != budget["budget_id"],
        session["execution_budget_digest"] != budget["budget_digest"],
        session["effective_permissions_id"] != permissions["permissions_id"],
        session["effective_permissions_digest"] != permissions["permissions_digest"],
        budget["tenant_id"] != request["tenant_id"],
        policy["tenant_id"] != request["tenant_id"],
        permissions["tenant_id"] != request["tenant_id"],
        budget["execution_scope"] != scope,
        policy["execution_scope"] != scope,
        permissions["execution_scope"] != scope,
        policy["execution_budget_id"] != budget["budget_id"],
        policy["execution_budget_digest"] != budget["budget_digest"],
        policy["effective_permissions_digest"] != permissions["permissions_digest"],
        policy["commercial_authorization_id"] != request["commercial_authorization"]["commercial_authorization_id"],
        policy["commercial_authorization_digest"] != request["commercial_authorization"]["commercial_authorization_digest"],
        policy["outcome"] != "allow",
        not any(
            evaluation["subject_kind"] == "artifact"
            and evaluation["subject_id"] == request["artifact_id"]
            and evaluation["action"] == "allow"
            and evaluation["rule_digest"] == canonical_digest({
                "artifact_id": request["artifact_id"],
                "media_type": request["media_type"],
            })
            for evaluation in policy["evaluations"]
        ),
        budget["limits"]["max_storage_bytes"] < request["size_bytes"],
        not permissions["artifact"]["stage_new_version"],
        parse_datetime(budget["created_at"]) < parse_datetime(request["requested_at"]),
        parse_datetime(policy["decided_at"]) < parse_datetime(request["requested_at"]),
        parse_datetime(budget["expires_at"]) > parse_datetime(request["commercial_authorization"]["expires_at"]),
        parse_datetime(policy["expires_at"]) > parse_datetime(request["commercial_authorization"]["expires_at"]),
        session["confirmed_upload_digest"] != request["content_digest"],
        scan["ingest_session_id"] != session["ingest_session_id"],
        scan["content_digest"] != session["confirmed_upload_digest"],
        session["scan_result_id"] != scan["scan_result_id"],
        session["scan_result_digest"] != scan["scan_result_digest"],
    )):
        raise AssertionError("Artifact ingest ownership, upload or scan binding is not closed")
    if scan["result"] != "passed":
        raise AssertionError("Artifact ingest cannot finalize without a passing immutable scan")
    if any((
        finalize["authority"] != "platform_artifact_ledger",
        finalize["ingest_session_id"] != session["ingest_session_id"],
        finalize["confirmed_upload_digest"] != session["confirmed_upload_digest"],
        finalize["scan_result_id"] != scan["scan_result_id"],
        finalize["scan_result_digest"] != scan["scan_result_digest"],
        session["status"] != "finalized",
        not session.get("artifact_version_id"),
        not session.get("artifact_version_digest"),
    )):
        raise AssertionError("Artifact ingest finalization authority or evidence is invalid")
    mark_checks("artifact_ingest.lifecycle")


def validate_conformance_suite(suite: dict[str, Any]) -> None:
    validate_self_digest(suite, "suite_digest")
    profile_ids = [profile["profile_id"] for profile in suite["profiles"]]
    if len(profile_ids) != len(set(profile_ids)):
        raise AssertionError("Conformance suite contains duplicate profiles")
    known = set(profile_ids)
    dependencies = {profile["profile_id"]: set(profile.get("depends_on", [])) for profile in suite["profiles"]}
    if any(not value <= known for value in dependencies.values()):
        raise AssertionError("Conformance profile depends on an unknown profile")
    test_ids = [test["test_id"] for profile in suite["profiles"] for test in profile["tests"]]
    if len(test_ids) != len(set(test_ids)):
        raise AssertionError("Conformance suite contains duplicate test IDs")
    visiting: set[str] = set()
    visited: set[str] = set()
    def visit(profile_id: str) -> None:
        if profile_id in visiting:
            raise AssertionError("Conformance profile dependency cycle")
        if profile_id in visited:
            return
        visiting.add(profile_id)
        for dependency in dependencies[profile_id]:
            visit(dependency)
        visiting.remove(profile_id)
        visited.add(profile_id)
    for profile_id in profile_ids:
        visit(profile_id)


def snapshot_fields(revision: dict[str, Any], decision: dict[str, Any]) -> dict[str, Any]:
    result = {
        "provider_revision_id": revision["provider_revision_id"],
        "provider_revision_digest": revision["provider_revision_digest"],
        "provider_kind": revision["provider_kind"],
        "implementation": revision["implementation"],
        "port": revision["port"],
        "configuration_digest": revision["configuration_digest"],
        "approved_permissions_digest": revision["approved_permissions_digest"],
        "credential_binding_digest": revision["credential_binding_digest"],
        "conformance_set_digest": revision["conformance_set_digest"],
        "admission_decision_id": decision["decision_id"],
        "admission_decision_digest": decision["decision_digest"],
        "admission_status": "certified",
    }
    return result


def provider_snapshot_bindings(manifest: dict[str, Any]) -> list[tuple[dict[str, Any], str]]:
    bindings = [(item["selected_provider_revision"], item["selected_provider_instance_id"]) for item in manifest["capability_resolutions"]]
    bindings.extend((item["provider_revision"], item["provider_instance_id"]) for item in manifest["selected_experiences"])
    return bindings


def capability_key(value: dict[str, Any], id_field: str = "id") -> tuple[str, str, str | None]:
    return (value[id_field], value["version"], value.get("profile"))


def revision_supports(revision: dict[str, Any], key: tuple[str, str, str | None]) -> bool:
    return any((item["capability"], item["version"], item.get("profile")) == key and item["status"] == "passed" for item in revision["conformance"])


def validate_run_admission(manifest: dict[str, Any], context: dict[str, Any]) -> None:
    validate_self_digest(manifest, "run_manifest_digest")
    mark_checks("run_manifest.digest")
    location = manifest["location"]
    location_unsigned = {
        key: value for key, value in location.items() if key != "placement_decision_digest"
    }
    if (
        location["placement_decision_digest"] != canonical_digest(location_unsigned)
        or {"cluster_id", "cell_id", "pod_id", "node_id", "runtime_id", "endpoint"} & set(location)
        or location["placement_mode"] == "platform_managed" and not location["region_id"]
    ):
        raise AssertionError("RunManifest contains an invalid or topology-leaking placement decision")
    if manifest["scenario"] != context["scenario"]:
        raise AssertionError("RunManifest scenario does not bind the admitted Scenario definition")
    scenario_definition = context["scenario_definition"]
    validate_self_digest(scenario_definition, "definition_digest")
    scenario_identity = {
        "id": scenario_definition["id"],
        "version": scenario_definition["version"],
        "definition_digest": scenario_definition["definition_digest"],
    }
    if scenario_identity != context["scenario"]:
        raise AssertionError("Run admission context does not bind its complete ScenarioDefinition")
    scenario_requirements = {item["id"]: item for item in scenario_definition["capabilities"]["required"]}
    if {item["id"] for item in context["required_capabilities"]} != set(scenario_requirements):
        raise AssertionError("Run admission capabilities do not exactly cover Scenario required capabilities")
    for item in context["required_capabilities"]:
        required_profiles = scenario_requirements[item["id"]].get("required_profiles", [])
        if required_profiles and item["profile"] not in required_profiles:
            raise AssertionError("Resolved capability profile is not allowed by the Scenario")
    if context["experience_requirements"] != scenario_definition.get("experience_requirements", []):
        raise AssertionError("Run admission Experience requirements differ from the ScenarioDefinition")
    commercial = context["commercial_authorization"]
    validate_self_digest(commercial, "commercial_authorization_digest")
    if commercial["authorized_limits_digest"] != canonical_digest(commercial["authorized_limits"]):
        raise AssertionError("Commercial authorization does not bind its explicit limits")
    expected_commercial = {
        "commercial_authorization_id": commercial["commercial_authorization_id"],
        "commercial_authorization_digest": commercial["commercial_authorization_digest"],
        "expires_at": commercial["expires_at"],
    }
    if manifest["commercial_authorization"] != expected_commercial:
        raise AssertionError("RunManifest does not bind the admitted CommercialAuthorizationSnapshot")
    required_items = [(item["id"], item["version"], item["profile"]) for item in context["required_capabilities"]]
    resolved_items = [(item["capability"]["id"], item["capability"]["version"], item["capability"]["profile"]) for item in manifest["capability_resolutions"]]
    required, resolved = set(required_items), set(resolved_items)
    if len(required_items) != len(required) or len(resolved_items) != len(resolved):
        raise AssertionError("Scenario requirements and CapabilityResolution entries must be unique by id/version/profile")
    if not required <= resolved:
        raise AssertionError(f"Capability resolution must cover every Scenario requirement: required={required}, resolved={resolved}")

    definitions: dict[tuple[str, str, str | None], dict[str, Any]] = {}
    for definition in context["capability_definitions"]:
        key = capability_key(definition)
        if key in definitions:
            raise AssertionError(f"Duplicate admitted CapabilityDefinition: {key}")
        definitions[key] = definition
    if required - set(definitions):
        raise AssertionError("Scenario requirements are missing admitted CapabilityDefinitions")
    runtime_key = capability_key(context["agent_runtime_capability"])
    if definitions.get(runtime_key) != context["agent_runtime_capability"]:
        raise AssertionError("Agent Runtime capability must bind one admitted CapabilityDefinition")

    revisions: dict[str, dict[str, Any]] = {}
    for revision in context["provider_revisions"]:
        validate_self_digest(revision, "provider_revision_digest")
        expected_conformance_digest = canonical_digest(revision["conformance"])
        if revision["conformance_set_digest"] != expected_conformance_digest:
            raise AssertionError("ProviderRevision conformance_set_digest mismatch")
        revision_id = revision["provider_revision_id"]
        if revision_id in revisions:
            raise AssertionError(f"Duplicate ProviderRevision in admission context: {revision_id}")
        revisions[revision_id] = revision

    decisions: dict[str, dict[str, Any]] = {}
    latest: dict[str, dict[str, Any]] = {}
    seen_sequences: set[tuple[str, int]] = set()
    for decision in context["admission_decisions"]:
        validate_self_digest(decision, "decision_digest")
        decision_id = decision["decision_id"]
        if decision_id in decisions:
            raise AssertionError(f"Duplicate AdmissionDecision: {decision_id}")
        key = (decision["provider_revision_id"], decision["decision_sequence"])
        if key in seen_sequences:
            raise AssertionError(f"Duplicate AdmissionDecision sequence: {key}")
        seen_sequences.add(key)
        revision = revisions.get(decision["provider_revision_id"])
        if revision is None or decision["provider_revision_digest"] != revision["provider_revision_digest"]:
            raise AssertionError("AdmissionDecision does not bind a verified ProviderRevision")
        decisions[decision_id] = decision
        current = latest.get(decision["provider_revision_id"])
        if current is None or decision["decision_sequence"] > current["decision_sequence"]:
            latest[decision["provider_revision_id"]] = decision

    for revision_id in revisions:
        chain = sorted(
            (item for item in decisions.values() if item["provider_revision_id"] == revision_id),
            key=lambda item: item["decision_sequence"],
        )
        if not chain:
            continue
        if [item["decision_sequence"] for item in chain] != list(range(1, len(chain) + 1)):
            raise AssertionError(f"AdmissionDecision sequence must be contiguous from one: {revision_id}")
        if "supersedes_decision_id" in chain[0]:
            raise AssertionError(f"First AdmissionDecision cannot supersede another decision: {revision_id}")
        for previous, current in zip(chain, chain[1:]):
            if current.get("supersedes_decision_id") != previous["decision_id"]:
                raise AssertionError(f"AdmissionDecision must supersede the immediate predecessor: {revision_id}")

    by_revision: dict[str, dict[str, Any]] = {}
    for snapshot, provider_instance_id in provider_snapshot_bindings(manifest):
        revision_id = snapshot["provider_revision_id"]
        revision = revisions.get(revision_id)
        decision = decisions.get(snapshot["admission_decision_id"])
        if revision is None or decision is None:
            raise AssertionError("RunManifest snapshot is missing verified Revision/Admission context")
        if provider_instance_id != revision["provider_instance_id"]:
            raise AssertionError("Provider instance binding does not match immutable Revision")
        if decision is not latest[revision_id] or decision["decision"] != "certified":
            raise AssertionError("RunManifest must bind the latest effective certified AdmissionDecision")
        if snapshot != snapshot_fields(revision, decision):
            raise AssertionError(f"Forged or incomplete ProviderRevision snapshot: {revision_id}")
        previous = by_revision.setdefault(revision_id, snapshot)
        if previous != snapshot:
            raise AssertionError(f"Conflicting snapshots for ProviderRevision {revision_id}")

    for resolution in manifest["capability_resolutions"]:
        validate_provider_resolution(resolution)
        key = capability_key(resolution["capability"])
        definition = definitions.get(key)
        revision = revisions[resolution["selected_provider_revision"]["provider_revision_id"]]
        if definition is None or resolution["capability_definition_digest"] != definition["definition_digest"]:
            raise AssertionError(f"CapabilityResolution does not bind the admitted CapabilityDefinition: {key}")
        if revision["provider_kind"] not in definition["allowed_provider_kinds"]:
            raise AssertionError(f"Provider kind {revision['provider_kind']} is not allowed for {key}")
        if not revision_supports(revision, key):
            raise AssertionError(f"ProviderRevision conformance does not cover selected capability: {key}")

    referenced_resolution_ids = {
        manifest["agent_runtime"]["resolution_id"],
        *(sandbox["resolution_id"] for sandbox in manifest["sandboxes"]),
    }
    for resolution in manifest["capability_resolutions"]:
        key = capability_key(resolution["capability"])
        if key not in required and resolution["resolution_id"] not in referenced_resolution_ids:
            raise AssertionError("RunManifest contains an unreferenced non-Scenario ProviderResolution")

    runtime_resolutions = [
        resolution for resolution in manifest["capability_resolutions"]
        if resolution["resolution_id"] == manifest["agent_runtime"]["resolution_id"]
    ]
    if len(runtime_resolutions) != 1:
        raise AssertionError("RunManifest agent_runtime must reference exactly one CapabilityResolution")
    runtime_resolution = runtime_resolutions[0]
    runtime_revision = revisions[runtime_resolution["selected_provider_revision"]["provider_revision_id"]]
    if runtime_revision["provider_kind"] != "agent_runtime" or "agent_runtime" not in context["agent_runtime_capability"]["allowed_provider_kinds"]:
        raise AssertionError("RunManifest agent_runtime must bind an admitted Agent Runtime Provider")
    if not revision_supports(runtime_revision, runtime_key):
        raise AssertionError("Agent Runtime Provider conformance does not cover its governed execution capability")

    for sandbox in manifest["sandboxes"]:
        sandbox_resolutions = [
            resolution for resolution in manifest["capability_resolutions"]
            if resolution["resolution_id"] == sandbox["resolution_id"]
        ]
        if len(sandbox_resolutions) != 1:
            raise AssertionError("Sandbox slot must reference exactly one ProviderResolution")
        sandbox_resolution = sandbox_resolutions[0]
        revision = revisions[sandbox_resolution["selected_provider_revision"]["provider_revision_id"]]
        if revision["provider_kind"] != "sandbox":
            raise AssertionError("Sandbox slot must bind a Sandbox ProviderRevision")
        required_keys = {capability_key(item) for item in sandbox["required_capabilities"]}
        if capability_key(sandbox_resolution["capability"]) not in required_keys:
            raise AssertionError("Sandbox ProviderResolution does not select one of the slot's required capabilities")
        for required_capability in sandbox["required_capabilities"]:
            key = capability_key(required_capability)
            definition = definitions.get(key)
            if definition is None or "sandbox" not in definition["allowed_provider_kinds"] or not revision_supports(revision, key):
                raise AssertionError(f"Sandbox ProviderRevision does not conform to required capability: {key}")

    experience_revisions: dict[str, dict[str, Any]] = {}
    for revision in context["experience_revisions"]:
        validate_self_digest(revision, "revision_digest")
        revision_id = revision["template_revision_id"]
        if revision_id in experience_revisions:
            raise AssertionError(f"Duplicate Experience revision: {revision_id}")
        experience_revisions[revision_id] = revision

    selected_counts: dict[tuple[str, str], int] = {}
    selected_revisions: dict[tuple[str, str], list[dict[str, Any]]] = {}
    authorized_entitlements = set(commercial["authorized_entitlements"])
    for selected in manifest["selected_experiences"]:
        selection = selected["selection"]
        if selection["kind"] != "template":
            raise AssertionError("v1 Experience admission only accepts governed TemplateRevision resources")
        revision = experience_revisions.get(selection["revision_id"])
        if revision is None or revision["revision_digest"] != selection["revision_digest"]:
            raise AssertionError("Selected Experience does not bind an admitted immutable revision")
        if revision["template_id"] != selection["catalog_entry_id"] or revision["capability"]["id"] != selection["capability_id"]:
            raise AssertionError("Selected Experience identity/capability conflicts with its TemplateRevision")
        if revision["provider_revision"] != selected["provider_revision"]:
            raise AssertionError("Selected Experience ProviderRevision snapshot conflicts with Catalog admission")
        provider = revisions[selected["provider_revision"]["provider_revision_id"]]
        capability = capability_key(revision["capability"])
        if provider["provider_kind"] != "template" or not revision_supports(provider, capability):
            raise AssertionError("Selected Template ProviderRevision is not conformant")
        if not set(revision.get("required_entitlements", [])) <= authorized_entitlements:
            raise AssertionError("Selected Experience requires an unauthorized commercial entitlement")
        count_key = (selection["kind"], selection["capability_id"])
        selected_counts[count_key] = selected_counts.get(count_key, 0) + 1
        selected_revisions.setdefault(count_key, []).append(revision)

    for requirement in context["experience_requirements"]:
        count = selected_counts.get((requirement["kind"], requirement["capability_id"]), 0)
        if not requirement["minimum"] <= count <= requirement["maximum"]:
            raise AssertionError("Selected Experience cardinality conflicts with Scenario requirements")
        required_tags = set(requirement.get("required_tags", []))
        if any(not required_tags <= set(revision.get("tags", [])) for revision in selected_revisions.get((requirement["kind"], requirement["capability_id"]), [])):
            raise AssertionError("Selected Experience does not satisfy Scenario required_tags")
    required_keys = {(item["kind"], item["capability_id"]) for item in context["experience_requirements"]}
    if set(selected_counts) - required_keys:
        raise AssertionError("RunManifest contains an Experience not requested by the Scenario")

    slots = [sandbox["sandbox_slot_key"] for sandbox in manifest["sandboxes"]]
    if len(slots) != len(set(slots)):
        raise AssertionError("sandbox_slot_key must be unique")
    if slots:
        if slots.count(manifest.get("primary_sandbox_slot_key")) != 1:
            raise AssertionError("primary_sandbox_slot_key must reference exactly one Sandbox")
    elif "primary_sandbox_slot_key" in manifest:
        raise AssertionError("A Sandbox-free RunManifest cannot declare primary_sandbox_slot_key")
    mark_checks(
        "run_manifest.admission",
        "run_manifest.runtime_resolution",
        "run_manifest.sandbox_resolution",
        "run_manifest.experience_binding",
        "run_manifest.commercial_event_binding",
    )


def validate_run_manifest_request_binding(
    manifest: dict[str, Any], grant: dict[str, Any], request: dict[str, Any],
) -> None:
    expected = {
        "request_contract_id": grant["request_contract_id"],
        "request_digest_profile": grant["request_digest_profile"],
        "request_digest": grant["request_digest"],
    }
    if manifest["request_binding"] != expected:
        raise AssertionError("RunManifest request binding differs from the consumed ExecutionGrant")
    if grant["request_digest"] != canonical_digest({
        key: value for key, value in request.items() if key != "execution_grant"
    }):
        raise AssertionError("RunManifest source ExecutionGrant does not bind the submitted request")
    if (
        manifest["conversation"]["conversation_id"] != grant["conversation_id"]
        or manifest["conversation"]["turn_id"] != grant["turn_id"]
        or manifest["conversation"]["branch_id"] != grant["branch_id"]
        or any(
            resolution["client_app_id"] != grant["client_app_id"]
            or resolution["principal_context_digest"] != grant["principal_context_digest"]
            for resolution in manifest["capability_resolutions"]
        )
    ):
        raise AssertionError("RunManifest source request crosses its admitted execution scope")
    mark_checks("run_manifest.request_binding", "run_manifest.conversation_binding")


def validate_state_machine(machine: dict[str, Any], allowed_states: set[str]) -> None:
    transitions = {(item["from"], item["event"], item["to"]) for item in machine["transitions"]}
    if len(transitions) != len(machine["transitions"]):
        raise AssertionError("Duplicate state transition")
    transition_keys = {(item["from"], item["event"]) for item in machine["transitions"]}
    if len(transition_keys) != len(machine["transitions"]):
        raise AssertionError("State machine is non-deterministic: duplicate (from,event)")
    used = {machine["initial_state"], *machine["terminal_states"]}
    for source, _, target in transitions:
        used.update((source, target))
    if used != allowed_states:
        raise AssertionError(f"State machine/Schema state mismatch: missing={allowed_states-used}, extra={used-allowed_states}")
    terminal = set(machine["terminal_states"])
    if any(source in terminal for source, _, _ in transitions):
        raise AssertionError("Terminal states must not have outgoing transitions")
    reachable = {machine["initial_state"]}
    changed = True
    while changed:
        changed = False
        for source, _, target in transitions:
            if source in reachable and target not in reachable:
                reachable.add(target)
                changed = True
    if allowed_states - reachable:
        raise AssertionError(f"Unreachable states: {allowed_states-reachable}")


def validate_work_order_failure_paths(machine: dict[str, Any]) -> None:
    transitions = {(item["from"], item["event"], item["to"]) for item in machine["transitions"]}
    required = {
        (state, "fail", "failed")
        for state in ("accepted", "queued", "waiting", "paused")
    }
    if not required <= transitions:
        raise AssertionError(
            "WorkOrder lacks a truthful failure path from accepted, queued, waiting or paused"
        )
    mark_checks("work_order.failure_paths")


def validate_artifact_operation_cancellation_paths(machine: dict[str, Any]) -> None:
    transitions = {(item["from"], item["event"], item["to"]) for item in machine["transitions"]}
    active_states = {"accepted", "resolving", "queued", "running", "reconciling"}
    required = {
        (state, "cancellation_intent_recorded", "cancel_requested")
        for state in active_states
    } | {
        ("cancel_requested", "pre_dispatch_absence_confirmed", "cancelled"),
        ("cancel_requested", "provider_cancel_dispatched", "cancelling"),
        ("cancelling", "cancel_outcome_unknown", "cancellation_reconciling"),
        ("cancelling", "invocation_cancelled_committed", "cancelled"),
        ("cancellation_reconciling", "invocation_cancelled_reconciled", "cancelled"),
        ("cancellation_reconciling", "reconciliation_failed", "failed"),
    }
    if not required <= transitions:
        raise AssertionError("ArtifactOperation cancellation lacks a durable intent or reconciliation path")
    unsafe_direct_cancel = active_states
    if any(source in unsafe_direct_cancel and target == "cancelled" for source, _, target in transitions):
        raise AssertionError("Active or unknown ArtifactOperation cannot transition directly to cancelled")
    cancellation_states = {"cancel_requested", "cancelling", "cancellation_reconciling"}
    if any(
        source in cancellation_states and ("retry" in event or target in {"queued", "running", "reconciling"})
        for source, event, target in transitions
    ):
        raise AssertionError("ArtifactOperation cancellation reconciliation cannot redispatch execution")
    if any(
        source in cancellation_states and target == "succeeded"
        and event != "prior_finalization_commit_proven"
        for source, event, target in transitions
    ):
        raise AssertionError("ArtifactOperation cancellation can succeed only from a prior finalization commit")
    mark_checks("artifact_operation.cancellation")


def status_enum(schema_path: str) -> set[str]:
    return set(load(schema_path)["properties"]["status"]["enum"])


work_order_machine = load("state-machines/work-order-v1.json")
validate_state_machine(work_order_machine, status_enum("schemas/work-order-state.schema.json"))
mark_checks("work_order_state.machine")
validate_work_order_failure_paths(work_order_machine)
validate_work_order_control_authority()
validate_state_machine(load("state-machines/conversation-v1.json"), status_enum("schemas/conversation.schema.json"))
validate_state_machine(load("state-machines/agent-runtime-run-v1.json"), status_enum("schemas/agent-runtime-run-status.schema.json"))
validate_state_machine(load("state-machines/runtime-recording-v1.json"), status_enum("schemas/runtime-recording.schema.json"))
invocation_machine = load("state-machines/invocation-v2.json")
validate_state_machine(invocation_machine, status_enum("schemas/invocation-record.schema.json"))
if any(item["from"] in {"executing", "outcome_unknown", "reconciling", "manual_review"} and item["to"] == "cancelled" for item in invocation_machine["transitions"]):
    raise AssertionError("In-flight/unknown Invocation cannot transition directly to cancelled")
if any(item["event"] == "abandon" for item in invocation_machine["transitions"]):
    raise AssertionError("Invocation abandon must explicitly bind risk acceptance")
if any(item["event"] == "retryable_failure" for item in invocation_machine["transitions"]):
    raise AssertionError("Invocation retry transition must distinguish idempotent retry from approved non-idempotent retry")
sandbox_machine = load("state-machines/sandbox-operation-v2.json")
validate_state_machine(sandbox_machine, status_enum("schemas/sandbox-operation-record.schema.json"))
unsafe_direct_cancel = {"running", "reconciling", "manual_review_required"}
if any(item["from"] in unsafe_direct_cancel and item["to"] == "cancelled" for item in sandbox_machine["transitions"]):
    raise AssertionError("In-flight/unknown Sandbox operation cannot transition directly to cancelled")
artifact_operation_machine = load("state-machines/artifact-operation-v1.json")
validate_state_machine(
    artifact_operation_machine,
    status_enum("schemas/artifact-operation.schema.json"),
)
validate_artifact_operation_cancellation_paths(artifact_operation_machine)
validate_state_machine(
    load("state-machines/artifact-ingest-v1.json"),
    status_enum("schemas/artifact-ingest-session.schema.json"),
)
mark_checks("artifact_ingest.lifecycle")

nondeterministic = copy.deepcopy(invocation_machine)
nondeterministic["transitions"].append({"from": "prepared", "event": "dispatch", "to": "failed"})
try:
    validate_state_machine(nondeterministic, status_enum("schemas/invocation-record.schema.json"))
except AssertionError:
    pass
else:
    raise AssertionError("Expected non-deterministic state-machine fixture to fail")
orphaned = copy.deepcopy(invocation_machine)
orphaned["transitions"].append({"from": "orphaned", "event": "remain_orphaned", "to": "orphaned"})
try:
    validate_state_machine(orphaned, status_enum("schemas/invocation-record.schema.json") | {"orphaned"})
except AssertionError:
    pass
else:
    raise AssertionError("Expected unreachable non-terminal state fixture to fail")

work_order_failure_negative = load("tests/semantic-invalid/work-order-failure-path-cases.json")
for case in work_order_failure_negative["cases"]:
    candidate = copy.deepcopy(work_order_machine)
    candidate["transitions"] = [
        transition for transition in candidate["transitions"]
        if not (transition["from"] == case["remove_failure_from"] and transition["event"] == "fail")
    ]
    try:
        validate_work_order_failure_paths(candidate)
    except AssertionError:
        pass
    else:
        raise AssertionError(f"Expected WorkOrder failure-path fixture to fail: {case['id']}")

artifact_operation_cancellation_negative = load(
    "tests/semantic-invalid/artifact-operation-cancellation-cases.json"
)
for case in artifact_operation_cancellation_negative["state_machine_cases"]:
    candidate = copy.deepcopy(artifact_operation_machine)
    mutation = case["mutation"]
    if mutation == "remove_active_cancel_path":
        candidate["transitions"] = [
            transition for transition in candidate["transitions"]
            if not (
                transition["from"] == case["state"]
                and transition["event"] == "cancellation_intent_recorded"
            )
        ]
    elif mutation == "direct_active_cancelled":
        candidate["transitions"].append({
            "from": case["state"], "event": "forced_cancel", "to": "cancelled",
        })
    elif mutation == "cancellation_retry":
        candidate["transitions"].append({
            "from": "cancellation_reconciling", "event": "retry_dispatched", "to": "running",
        })
    elif mutation == "ambiguous_cancellation_success":
        candidate["transitions"].append({
            "from": "cancelling", "event": "provider_reports_success", "to": "succeeded",
        })
    elif mutation == "remove_unknown_reconciliation":
        candidate["transitions"] = [
            transition for transition in candidate["transitions"]
            if not (
                transition["from"] == "cancelling"
                and transition["event"] == "cancel_outcome_unknown"
            )
        ]
    else:
        raise AssertionError(f"Unknown ArtifactOperation cancellation-machine mutation: {mutation}")
    try:
        validate_artifact_operation_cancellation_paths(candidate)
    except AssertionError:
        pass
    else:
        raise AssertionError(
            f"Expected ArtifactOperation cancellation-machine fixture to fail: {case['id']}"
        )

context = load("examples/contracts/run-admission-context.json")
manifest = load("examples/contracts/run-manifest-v2.json")
conversation = load("examples/contracts/conversation.json")
work_session_request = load("examples/contracts/work-session-request.json")
work_session_claims = load("examples/contracts/work-session-claims.json")
service_access_token = load("examples/contracts/service-access-token-claims.json")
plugin_request = load("examples/contracts/plugin-invocation-request.json")
plugin_token = load("examples/contracts/plugin-invocation-token-claims.json")
plugin_status_descriptor = load("examples/contracts/plugin-status-operation-descriptor.json")
plugin_status_token = load("examples/contracts/plugin-status-token-claims.json")
plugin_cancel_request = load("examples/contracts/plugin-cancellation-request.json")
plugin_cancel_token = load("examples/contracts/plugin-cancellation-token-claims.json")
plugin_event_descriptor = load("examples/contracts/plugin-event-read-operation-descriptor.json")
plugin_event_token = load("examples/contracts/plugin-events-token-claims.json")
no_sandbox_manifest = load("examples/contracts/run-manifest-no-sandbox.json")
workflow_run = load("examples/contracts/workflow-run.json")
workflow_root_binding = load("examples/contracts/workflow-run-root-binding.json")
agent_run = load("examples/contracts/agent-run.json")
root_budget_allocation = load("examples/contracts/agent-run-budget-allocation.json")
runtime_start = load("examples/contracts/agent-runtime-start-request.json")
child_spawn_request = load("examples/contracts/child-agent-run-spawn-request.json")
child_admission_decision = load("examples/contracts/child-agent-run-admission-decision.json")
child_agent_run = load("examples/contracts/child-agent-run.json")
child_manifest = load("examples/contracts/child-run-manifest-v2.json")
child_runtime_start = load("examples/contracts/child-agent-runtime-start-request.json")
control_fanout = load("examples/contracts/agent-run-control-fanout.json")
progressed_control_fanout = load(
    "examples/contracts/agent-run-control-fanout-progressed.json"
)
cancel_control_request = load("examples/contracts/work-order-cancel-request.json")
renewed_runtime_authorization = load("examples/contracts/runtime-authorization-renewed.json")
runtime_token = load("examples/contracts/agent-runtime-invocation-token-claims.json")
runtime_command = load("examples/contracts/agent-runtime-command.json")
spawn_decision_command = load(
    "examples/contracts/agent-runtime-subagent-spawn-decision-command.json"
)
runtime_command_token = load("examples/contracts/agent-runtime-command-token-claims.json")
system_safety_control = load("examples/contracts/system-safety-control.json")
system_safety_command = load("examples/contracts/agent-runtime-system-safety-command.json")
system_safety_token = load(
    "examples/contracts/agent-runtime-system-safety-command-token-claims.json"
)
commercial_revocation = load("examples/contracts/commercial-authorization-revocation.json")
commercial_revocation_accepted = load(
    "examples/contracts/commercial-authorization-revocation-accepted.json"
)
control_request = load("examples/contracts/work-order-control-request.json")
cancel_control_grant = load("examples/contracts/execution-grant-cancel-claims.json")
control_runtime_input = load("examples/contracts/work-order-control-runtime-input.json")
runtime_status_descriptor = load("examples/contracts/agent-runtime-status-operation-descriptor.json")
runtime_status_token = load("examples/contracts/agent-runtime-status-token-claims.json")
runtime_event_descriptor = load("examples/contracts/agent-runtime-event-read-operation-descriptor.json")
runtime_event_token = load("examples/contracts/agent-runtime-events-token-claims.json")
sandbox_token = load("examples/contracts/sandbox-operation-token-claims.json")
sandbox_create = load("examples/contracts/sandbox-create-request.json")
sandbox_restore = load("examples/contracts/sandbox-restore-request.json")
sandbox_desired_state = load("examples/contracts/sandbox-desired-state-request.json")
sandbox_lease = load("examples/contracts/sandbox-lease-request.json")
sandbox_exec = load("examples/contracts/sandbox-exec-request.json")
sandbox_cancel_exec = load("examples/contracts/sandbox-cancel-exec-request.json")
sandbox_runtime_session = load("examples/contracts/sandbox-runtime-session-open-request.json")
sandbox_snapshot = load("examples/contracts/sandbox-snapshot-request.json")
sandbox_terminate = load("examples/contracts/sandbox-terminate-request.json")
sandbox_status_descriptor = load("examples/contracts/sandbox-status-operation-descriptor.json")
sandbox_operation_read_descriptor = load("examples/contracts/sandbox-operation-read-operation-descriptor.json")
sandbox_exec_result_descriptor = load("examples/contracts/sandbox-exec-result-operation-descriptor.json")
sandbox_snapshot_manifest_descriptor = load("examples/contracts/sandbox-snapshot-manifest-operation-descriptor.json")
sandbox_event_read_descriptor = load("examples/contracts/sandbox-event-read-operation-descriptor.json")
sandbox_spec = load("examples/contracts/sandbox-spec.json")
child_sandbox_spec = load("examples/contracts/child-sandbox-spec.json")
sandbox_capabilities = load("examples/contracts/sandbox-capabilities.json")
capability_request = load("examples/contracts/capability-invocation-request.json")
capability_token = load("examples/contracts/capability-invocation-token-claims.json")
capability_status_token = load("examples/contracts/capability-invocation-status-token-claims.json")
capability_status_operation = load("examples/contracts/capability-status-operation-descriptor.json")
capability_cancel = load("examples/contracts/capability-cancellation-request.json")
capability_cancel_token = load("examples/contracts/capability-cancellation-token-claims.json")
capability_event_operation = load("examples/contracts/capability-event-read-operation-descriptor.json")
capability_event_token = load("examples/contracts/capability-invocation-events-token-claims.json")
capability_result = load("examples/contracts/capability-invocation-result.json")
artifact_staging_grant = load("examples/contracts/artifact-staging-grant.json")
artifact_staging_object = load("examples/contracts/artifact-staging-object-request.json")
artifact_stage_token = load("examples/contracts/artifact-gateway-stage-token-claims.json")
artifact_staging_commit = load("examples/contracts/artifact-staging-commit-request.json")
artifact_commit_token = load("examples/contracts/artifact-gateway-commit-token-claims.json")
artifact_read_descriptor = load("examples/contracts/artifact-read-operation-descriptor.json")
artifact_read_token = load("examples/contracts/artifact-gateway-read-token-claims.json")
egress_request = load("examples/contracts/egress-http-request.json")
egress_destination = load("examples/contracts/egress-destination-revision.json")
egress_response = load("examples/contracts/egress-http-response.json")
egress_token = load("examples/contracts/egress-invocation-token-claims.json")
workspace_content_manifest = load("examples/contracts/workspace-content-manifest.json")
canonical_event = load("examples/contracts/canonical-event-v2.json")
canonical_runtime_event = load("examples/contracts/canonical-runtime-event-v2.json")
platform_scope_events = [
    load("examples/contracts/canonical-event-conversation-branch-forked.json"),
    load("examples/contracts/canonical-event-artifact-operation-succeeded.json"),
    load("examples/contracts/canonical-event-artifact-operation-cancel-requested.json"),
    load("examples/contracts/canonical-event-artifact-ingest-finalized.json"),
    load("examples/contracts/canonical-event-compatibility-decided.json"),
    load("examples/contracts/canonical-event-secret-grant-issued.json"),
    load("examples/contracts/canonical-event-artifact-operation-secret-grant-issued.json"),
]
semantic_traceability = load("semantic-constraints-v1.json")
event_registry = load("event-types/agent-runtime-core-v1.json")
platform_event_registry = load("event-types/platform-core-v1.json")
meter = load("examples/contracts/meter-definition.json")
usage_entry = load("examples/contracts/technical-usage-entry.json")
usage_report = load("examples/contracts/usage-report.json")
settlement = load("examples/contracts/business-settlement-envelope.json")
artifact_operation_usage_entry = load(
    "examples/contracts/artifact-operation-technical-usage-entry.json"
)
artifact_operation_usage_report = load(
    "examples/contracts/artifact-operation-usage-report.json"
)
artifact_operation_settlement = load(
    "examples/contracts/artifact-operation-business-settlement-envelope.json"
)
policy_decision = load("examples/contracts/policy-decision.json")
execution_budget = load("examples/contracts/execution-budget.json")
gateway_connect = load("examples/contracts/runtime-gateway-frame.json")
gateway_control = load("examples/contracts/runtime-gateway-control-frame.json")
runtime_session_request = load("examples/contracts/runtime-session-request.json")
runtime_session_response = load("examples/contracts/runtime-session-response.json")
runtime_session_route = load("examples/contracts/runtime-session-route.json")
execution_grant = load("examples/contracts/execution-grant-claims.json")
artifact_operation_request = load("examples/contracts/preview-session-request.json")
artifact_operation = load("examples/contracts/artifact-operation.json")
artifact_operation_admission_failed = load(
    "examples/contracts/artifact-operation-admission-failed.json"
)
artifact_operation_cancel_requested = load(
    "examples/contracts/artifact-operation-cancel-requested.json"
)
artifact_operation_cancel_invocation = load(
    "examples/contracts/artifact-operation-cancel-requested-invocation.json"
)
artifact_operation_cancellation_reconciling = load(
    "examples/contracts/artifact-operation-cancellation-reconciling.json"
)
artifact_operation_cancellation_reconciling_invocation = load(
    "examples/contracts/artifact-operation-cancellation-reconciling-invocation.json"
)
artifact_operation_budget = load("examples/contracts/artifact-operation-execution-budget.json")
artifact_operation_policy = load("examples/contracts/artifact-operation-policy-decision.json")
artifact_operation_resolution = load("examples/contracts/artifact-operation-provider-resolution.json")
artifact_operation_invocation = load("examples/contracts/artifact-operation-invocation.json")
artifact_operation_capability_request = load(
    "examples/contracts/artifact-operation-capability-invocation-request.json"
)
artifact_operation_capability_token = load(
    "examples/contracts/artifact-operation-capability-invocation-token-claims.json"
)
artifact_operation_input_grant = load(
    "examples/contracts/artifact-operation-input-artifact-grant.json"
)
artifact_operation_staging_grant = load(
    "examples/contracts/artifact-operation-staging-grant.json"
)
artifact_operation_staging_object = load(
    "examples/contracts/artifact-operation-artifact-staging-object-request.json"
)
artifact_operation_stage_token = load(
    "examples/contracts/artifact-operation-artifact-gateway-stage-token-claims.json"
)
artifact_operation_read_descriptor = load(
    "examples/contracts/artifact-operation-artifact-read-operation-descriptor.json"
)
artifact_operation_read_token = load(
    "examples/contracts/artifact-operation-artifact-gateway-read-token-claims.json"
)
artifact_operation_staging_commit = load(
    "examples/contracts/artifact-operation-artifact-staging-commit-request.json"
)
artifact_operation_commit_token = load(
    "examples/contracts/artifact-operation-artifact-gateway-commit-token-claims.json"
)
edit_operation_request = load("examples/contracts/edit-session-request.json")
edit_operation = load("examples/contracts/edit-session.json")["artifact_operation"]
edit_operation_budget = load("examples/contracts/edit-artifact-operation-capability-invocation-request.json")["execution_budget"]
edit_operation_policy = load("examples/contracts/edit-artifact-operation-capability-invocation-request.json")["policy_decision"]
edit_operation_permissions = load("examples/contracts/edit-artifact-operation-capability-invocation-request.json")["effective_permissions"]
edit_operation_resolution = load("examples/contracts/edit-artifact-operation-provider-resolution.json")
edit_operation_invocation = load("examples/contracts/edit-artifact-operation-invocation.json")
edit_operation_provider_request = load(
    "examples/contracts/edit-artifact-operation-capability-invocation-request.json"
)
conversion_operation_request = load("examples/contracts/conversion-request.json")
conversion_operation = load("examples/contracts/conversion-job.json")["artifact_operation"]
conversion_operation_provider_request = load(
    "examples/contracts/conversion-artifact-operation-capability-invocation-request.json"
)
conversion_operation_budget = conversion_operation_provider_request["execution_budget"]
conversion_operation_policy = conversion_operation_provider_request["policy_decision"]
conversion_operation_permissions = conversion_operation_provider_request["effective_permissions"]
conversion_operation_resolution = load(
    "examples/contracts/conversion-artifact-operation-provider-resolution.json"
)
conversion_operation_invocation = load(
    "examples/contracts/conversion-artifact-operation-invocation.json"
)
branch_create_request = load("examples/contracts/conversation-branch-create-request.json")
branch_created = load("examples/contracts/conversation-branch-created.json")
empty_branch_create_request = load("examples/contracts/conversation-branch-empty-create-request.json")
empty_branch_created = load("examples/contracts/conversation-branch-empty-created.json")
no_usage_attestation = load("examples/contracts/no-usage-attestation.json")
no_usage_delivery = load("examples/contracts/delivery-package-no-usage.json")
no_usage_release = load("examples/contracts/business-settlement-release-envelope.json")
artifact_operation_no_usage = load(
    "examples/contracts/artifact-operation-no-usage-attestation.json"
)
artifact_operation_no_usage_release = load(
    "examples/contracts/artifact-operation-business-settlement-release-envelope.json"
)
runtime_checkpoint = load("examples/contracts/agent-runtime-checkpoint-manifest.json")
runtime_compatibility_decision = load("examples/contracts/runtime-compatibility-decision.json")
sandbox_compatibility_decision = load("examples/contracts/sandbox-compatibility-decision.json")
secret_grant = load("examples/contracts/secret-grant.json")
secret_revocation = load("examples/contracts/secret-grant-revocation.json")
credential_request = load("examples/contracts/credential-access-request.json")
credential_token = load("examples/contracts/credential-operation-token-claims.json")
credential_delivery = load("examples/contracts/credential-delivery.json")
artifact_operation_secret_grant = load("examples/contracts/artifact-operation-secret-grant.json")
artifact_operation_credential_request = load(
    "examples/contracts/artifact-operation-credential-access-request.json"
)
artifact_operation_credential_token = load(
    "examples/contracts/artifact-operation-credential-operation-token-claims.json"
)
artifact_operation_credential_delivery = load(
    "examples/contracts/artifact-operation-credential-delivery.json"
)
artifact_ingest_request = load("examples/contracts/artifact-ingest-request.json")
artifact_ingest_session = load("examples/contracts/artifact-ingest-session.json")
artifact_ingest_budget = load("examples/contracts/artifact-ingest-execution-budget.json")
artifact_ingest_policy = load("examples/contracts/artifact-ingest-policy-decision.json")
artifact_ingest_permissions = load("examples/contracts/artifact-ingest-effective-permissions.json")
artifact_ingest_scan = load("examples/contracts/artifact-ingest-scan-result.json")
artifact_ingest_finalize = load("examples/contracts/artifact-ingest-finalize-command.json")
conformance_suites = [
    load("conformance/agent-access/v1/suite.json"),
    load("conformance/runtime/v1/suite.json"),
    load("conformance/sandbox/v1/suite.json"),
    load("conformance/runtime-gateway/v1/suite.json"),
    load("conformance/capability/v1/suite.json"),
    load("conformance/execution-gateway/v1/suite.json"),
    load("conformance/credential/v1/suite.json"),
]
validate_provider_architecture(context, conformance_suites)
validate_artifact_operation(
    artifact_operation_request, artifact_operation, artifact_operation_budget,
    artifact_operation_policy,
    load("examples/contracts/artifact-operation-effective-permissions.json"),
    artifact_operation_resolution, artifact_operation_invocation,
    artifact_operation_capability_request,
)
validate_artifact_operation_terminal_shape(artifact_operation)
validate_artifact_operation_terminal_shape(artifact_operation_admission_failed)
validate_artifact_operation_cancellation_binding(
    artifact_operation_cancel_requested, commercial_revocation_accepted,
    artifact_operation_cancel_invocation,
)
validate_artifact_operation_cancellation_binding(
    artifact_operation_cancellation_reconciling, commercial_revocation_accepted,
    artifact_operation_cancellation_reconciling_invocation,
)
validate_artifact_operation(
    edit_operation_request, edit_operation, edit_operation_budget,
    edit_operation_policy, edit_operation_permissions, edit_operation_resolution,
    edit_operation_invocation, edit_operation_provider_request,
)
validate_artifact_operation(
    conversion_operation_request, conversion_operation, conversion_operation_budget,
    conversion_operation_policy, conversion_operation_permissions,
    conversion_operation_resolution, conversion_operation_invocation,
    conversion_operation_provider_request,
)
artifact_operation_execution_owner = {
    "artifact_operation": artifact_operation,
    "request_context": artifact_operation_request["operation_context"],
    "execution_budget": artifact_operation_budget,
    "effective_permissions": load("examples/contracts/artifact-operation-effective-permissions.json"),
    "artifact_gateway_binding": artifact_operation_capability_request[
        "output_staging_grant"
    ]["gateway_binding"],
}
validate_capability_invocation(
    artifact_operation_capability_request, artifact_operation_capability_token,
    artifact_operation_resolution, artifact_operation_execution_owner,
)
validate_artifact_gateway(
    artifact_operation_staging_grant, artifact_operation_staging_object,
    artifact_operation_stage_token, artifact_operation_staging_commit,
    artifact_operation_commit_token, artifact_operation_input_grant,
    artifact_operation_read_descriptor, artifact_operation_read_token,
    artifact_operation_capability_request,
    caller_subject=artifact_operation_resolution["selected_provider_audience"],
)
artifact_operation_usage_owner = {
    "operation": artifact_operation,
    "invocation": artifact_operation_invocation,
    "resolution": artifact_operation_resolution,
}
validate_usage_contracts(
    meter, artifact_operation_usage_entry, artifact_operation_usage_report,
    artifact_operation_settlement, artifact_operation_usage_owner,
)
validate_conversation_branch_create(
    branch_create_request, branch_created,
    load("examples/contracts/conversation-branch.json"),
    load("examples/contracts/conversation-message.json"),
    load("examples/contracts/workspace-revision.json"),
)
validate_conversation_branch_create(
    empty_branch_create_request, empty_branch_created, None, None,
    load("examples/contracts/workspace-revision.json"),
)
validate_no_usage_accounting(
    no_usage_attestation, no_usage_delivery, no_usage_release, 0, [],
)
validate_no_usage_accounting(
    artifact_operation_no_usage, None, artifact_operation_no_usage_release,
    0, [], expected_terminal_status="failed",
)
if (
    artifact_operation_no_usage["execution_scope"]["artifact_operation_id"]
    != artifact_operation_admission_failed["artifact_operation_id"]
    or artifact_operation_admission_failed["status"] != "failed"
    or artifact_operation_admission_failed["terminal_stage"] != "admission"
):
    raise AssertionError("ArtifactOperation NoUsageAttestation lacks its admission terminal owner")
validate_compatibility_decision(
    runtime_checkpoint, runtime_compatibility_decision,
    load("conformance/runtime/v1/suite.json"),
)
validate_compatibility_decision(
    sandbox_restore["snapshot"], sandbox_compatibility_decision,
    load("conformance/sandbox/v1/suite.json"), sandbox_restore,
)
validate_secret_mediation(
    secret_grant, credential_request, credential_token, credential_delivery,
    secret_grant["workload_identity"], parse_datetime("2026-07-16T09:08:30Z"),
    {
        "request": sandbox_exec,
        "tenant_id": manifest["tenant_id"],
        "principal_context_digest": execution_grant["principal_context_digest"],
        "execution_scope": {"kind": "work_order", "work_order_id": manifest["work_order_id"]},
        "provider_instance_id": "spi_native_sandbox",
        "provider_revision_id": "spr_01J00000000000000000000000",
        "provider_audience": "urn:agent-platform:provider-instance:spi_native_sandbox",
        "workload_identity": secret_grant["workload_identity"],
        "deadline_at": sandbox_exec["deadline_at"],
    },
)
validate_secret_mediation(
    artifact_operation_secret_grant, artifact_operation_credential_request,
    artifact_operation_credential_token, artifact_operation_credential_delivery,
    artifact_operation_secret_grant["workload_identity"],
    parse_datetime("2026-07-16T09:07:00Z"),
    {
        "request": artifact_operation_capability_request,
        "tenant_id": artifact_operation_capability_request["tenant_id"],
        "principal_context_digest": artifact_operation_capability_request["principal_context_digest"],
        "execution_scope": artifact_operation_capability_request["execution_scope"],
        "provider_instance_id": artifact_operation_capability_request["provider_instance_id"],
        "provider_revision_id": artifact_operation_capability_request["provider_revision_id"],
        "provider_audience": artifact_operation_resolution["selected_provider_audience"],
        "workload_identity": artifact_operation_secret_grant["workload_identity"],
        "deadline_at": artifact_operation_capability_request["deadline_at"],
    },
)
validate_artifact_ingest(
    artifact_ingest_request, artifact_ingest_session,
    artifact_ingest_budget, artifact_ingest_policy, artifact_ingest_permissions,
    artifact_ingest_scan, artifact_ingest_finalize,
)

artifact_operation_negative = load("tests/semantic-invalid/artifact-operation-cases.json")
for case in artifact_operation_negative["cases"]:
    candidate_request = copy.deepcopy(artifact_operation_negative["request"])
    candidate_operation = copy.deepcopy(artifact_operation_negative["operation"])
    candidate_budget = copy.deepcopy(artifact_operation_negative["budget"])
    candidate_policy = copy.deepcopy(artifact_operation_negative["policy"])
    candidate_permissions = copy.deepcopy(artifact_operation_negative["permissions"])
    candidate_resolution = copy.deepcopy(artifact_operation_negative["resolution"])
    candidate_invocation = copy.deepcopy(artifact_operation_negative["invocation"])
    candidate_provider_request = copy.deepcopy(
        artifact_operation_negative["provider_request"]
    )
    mutation = case["mutation"]
    if mutation == "provider_resolution_mismatch":
        candidate_operation["provider_resolution_id"] = "res_wrong_scope"
    elif mutation == "invocation_scope_mismatch":
        candidate_invocation["execution_scope"]["artifact_operation_id"] = "aop_other"
    elif mutation == "invocation_request_digest_mismatch":
        candidate_operation["invocation_request_digest"] = "sha256:" + "f" * 64
    elif mutation == "permissions_scope_mismatch":
        candidate_permissions["execution_scope"]["artifact_operation_id"] = "aop_other"
        candidate_permissions["permissions_digest"] = canonical_digest({
            key: value for key, value in candidate_permissions.items()
            if key != "permissions_digest"
        })
    elif mutation == "provider_revision_mismatch":
        candidate_invocation["provider_revision_id"] = "rpr_other"
    elif mutation == "source_version_digest_mismatch":
        candidate_operation["source_version_digest"] = "sha256:" + "f" * 64
    elif mutation == "terminal_evidence_missing":
        candidate_operation.pop("terminal_evidence_digest")
    elif mutation == "provider_request_owner_digest_mismatch":
        candidate_provider_request["execution_owner_request_digest"] = "sha256:" + "f" * 64
        candidate_provider_request["request_digest"] = canonical_digest({
            key: value for key, value in candidate_provider_request.items()
            if key != "request_digest"
        })
    elif mutation == "platform_policy_binding_mismatch":
        candidate_operation["policy_decision_digest"] = "sha256:" + "f" * 64
    elif mutation == "platform_gateway_binding_mismatch":
        candidate_operation["artifact_gateway_binding_digest"] = "sha256:" + "f" * 64
    try:
        validate_artifact_operation(
            candidate_request, candidate_operation, candidate_budget, candidate_policy,
            candidate_permissions, candidate_resolution, candidate_invocation,
            candidate_provider_request,
        )
    except AssertionError:
        pass
    else:
        raise AssertionError(f"Expected ArtifactOperation semantic fixture to fail: {case['id']}")

for case in artifact_operation_cancellation_negative["binding_cases"]:
    owner = case.get("owner", "cancel_requested")
    candidate_operation = copy.deepcopy(artifact_operation_cancellation_negative[
        f"{owner}_operation"
    ])
    candidate_invocation = copy.deepcopy(artifact_operation_cancellation_negative[
        f"{owner}_invocation"
    ])
    candidate_receipt = copy.deepcopy(artifact_operation_cancellation_negative["receipt"])
    mutation = case["mutation"]
    if mutation == "source_receipt_digest_mismatch":
        candidate_operation["cancellation_source_digest"] = "sha256:" + "f" * 64
    elif mutation == "intent_id_mismatch":
        candidate_operation["cancellation_intent_id"] = "cani_other"
    elif mutation == "outbox_message_mismatch":
        candidate_operation["cancellation_outbox_message_id"] = "out_other"
    elif mutation == "requested_before_receipt":
        candidate_operation["cancellation_requested_at"] = "2026-07-16T09:10:01Z"
    elif mutation == "stale_owner_cas":
        candidate_operation["state_version"] += 1
    elif mutation == "invocation_status_terminal":
        candidate_invocation["status"] = "succeeded"
    elif mutation == "invocation_binding_mismatch":
        candidate_invocation["provider_resolution_id"] = "res_other"
    elif mutation == "reconciliation_case_mismatch":
        candidate_invocation["reconciliation_case_id"] = "irc_other"
    else:
        raise AssertionError(f"Unknown ArtifactOperation cancellation-binding mutation: {mutation}")
    try:
        validate_artifact_operation_cancellation_binding(
            candidate_operation, candidate_receipt, candidate_invocation,
        )
    except AssertionError:
        pass
    else:
        raise AssertionError(
            f"Expected ArtifactOperation cancellation-binding fixture to fail: {case['id']}"
        )

artifact_usage_negative = load(
    "tests/semantic-invalid/artifact-operation-usage-cases.json"
)
for case in artifact_usage_negative["cases"]:
    candidate_entry = copy.deepcopy(artifact_usage_negative["entry"])
    candidate_report = copy.deepcopy(artifact_usage_negative["report"])
    candidate_settlement = copy.deepcopy(artifact_usage_negative["settlement"])
    candidate_owner = {
        "operation": copy.deepcopy(artifact_usage_negative["operation"]),
        "invocation": copy.deepcopy(artifact_usage_negative["invocation"]),
        "resolution": copy.deepcopy(artifact_usage_negative["resolution"]),
    }
    mutation = case["mutation"]
    if mutation == "wrong_invocation":
        candidate_entry["invocation_id"] = "inv_other"
        candidate_report["entries"] = [copy.deepcopy(candidate_entry)]
        candidate_report["usage_report_digest"] = canonical_digest({
            key: value for key, value in candidate_report.items()
            if key != "usage_report_digest"
        })
        candidate_settlement["usage_report"] = copy.deepcopy(candidate_report)
    elif mutation == "wrong_provider_revision":
        candidate_entry["producer"]["provider_revision_id"] = "rpr_other"
        candidate_report["entries"] = [copy.deepcopy(candidate_entry)]
        candidate_report["usage_report_digest"] = canonical_digest({
            key: value for key, value in candidate_report.items()
            if key != "usage_report_digest"
        })
        candidate_settlement["usage_report"] = copy.deepcopy(candidate_report)
    elif mutation == "cross_scope_entry":
        candidate_report["entries"][0]["execution_scope"]["artifact_operation_id"] = "aop_other"
        candidate_report["usage_report_digest"] = canonical_digest({
            key: value for key, value in candidate_report.items()
            if key != "usage_report_digest"
        })
    elif mutation == "settlement_cross_scope":
        candidate_settlement["execution_scope"]["artifact_operation_id"] = "aop_other"
    candidate_settlement["settlement_envelope_digest"] = canonical_digest({
        key: value for key, value in candidate_settlement.items()
        if key != "settlement_envelope_digest"
    })
    try:
        validate_usage_contracts(
            artifact_usage_negative["meter"], candidate_entry, candidate_report,
            candidate_settlement, candidate_owner,
        )
    except AssertionError:
        pass
    else:
        raise AssertionError(
            f"Expected ArtifactOperation usage fixture to fail: {case['id']}"
        )

branch_create_negative = load("tests/semantic-invalid/conversation-branch-create-cases.json")
for case in branch_create_negative["cases"]:
    is_empty_create = case["mutation"].startswith("create_")
    candidate_request = copy.deepcopy(
        branch_create_negative["empty_request" if is_empty_create else "request"]
    )
    candidate_created = copy.deepcopy(
        branch_create_negative["empty_created" if is_empty_create else "created"]
    )
    candidate_source_branch = None if is_empty_create else branch_create_negative["source_branch"]
    candidate_source_message = None if is_empty_create else branch_create_negative["source_message"]
    candidate_source_workspace = copy.deepcopy(branch_create_negative["source_workspace"])
    if case["mutation"] == "message_cas_stale":
        candidate_request["source_message_head_version"] += 1
        candidate_request["request_digest"] = canonical_digest({
            key: value for key, value in candidate_request.items() if key != "request_digest"
        })
    elif case["mutation"] == "workspace_digest_mismatch":
        candidate_request["source_workspace_revision_digest"] = "sha256:" + "f" * 64
        candidate_request["request_digest"] = canonical_digest({
            key: value for key, value in candidate_request.items() if key != "request_digest"
        })
    elif case["mutation"] == "created_wrong_cut":
        candidate_created["branch"]["head_message_sequence"] += 1
    elif case["mutation"] == "create_inherits_message":
        candidate_created["branch"]["head_message_id"] = branch_create_negative["source_message"]["message_id"]
        candidate_created["branch"]["head_message_sequence"] = branch_create_negative["source_message"]["message_sequence"]
    elif case["mutation"] == "create_wrong_workspace":
        candidate_source_workspace["revision_number"] = 2
        candidate_source_workspace["parent_revision_id"] = "wsr_previous"
        candidate_source_workspace["revision_digest"] = canonical_digest({
            key: value for key, value in candidate_source_workspace.items()
            if key != "revision_digest"
        })
    try:
        validate_conversation_branch_create(
            candidate_request, candidate_created,
            candidate_source_branch, candidate_source_message, candidate_source_workspace,
        )
    except AssertionError:
        pass
    else:
        raise AssertionError(f"Expected ConversationBranch create fixture to fail: {case['id']}")

no_usage_negative = load("tests/semantic-invalid/no-usage-cases.json")
for case in no_usage_negative["cases"]:
    try:
        validate_no_usage_accounting(
            no_usage_negative["attestation"], no_usage_delivery, no_usage_release,
            1 if case["mutation"] == "dispatched_attempt_exists" else 0, [],
        )
    except AssertionError:
        pass
    else:
        raise AssertionError(f"Expected NoUsage semantic fixture to fail: {case['id']}")

compatibility_negative = load("tests/semantic-invalid/compatibility-decision-cases.json")
for case in compatibility_negative["cases"]:
    runtime_candidate = copy.deepcopy(compatibility_negative["runtime_decision"])
    sandbox_restore_candidate = copy.deepcopy(compatibility_negative["sandbox_restore"])
    if case["mutation"] == "runtime_failed_evidence":
        runtime_candidate["evidence"][0]["result"] = "failed"
        runtime_candidate["evidence"][0]["evidence_digest"] = canonical_digest({
            key: value for key, value in runtime_candidate["evidence"][0].items()
            if key != "evidence_digest"
        })
        runtime_candidate["decision_digest"] = canonical_digest({
            key: value for key, value in runtime_candidate.items() if key != "decision_digest"
        })
    elif case["mutation"] == "runtime_target_mismatch":
        runtime_candidate["target_runtime_revision"] = "native-runtime-other"
        runtime_candidate["decision_digest"] = canonical_digest({
            key: value for key, value in runtime_candidate.items() if key != "decision_digest"
        })
    elif case["mutation"] == "sandbox_restore_target_mismatch":
        sandbox_restore_candidate["target_runtime_revision"] = "sandbox-runtime-other"
    try:
        if case["mutation"].startswith("runtime_"):
            validate_compatibility_decision(
                compatibility_negative["runtime_subject"], runtime_candidate,
                load("conformance/runtime/v1/suite.json"),
            )
        else:
            validate_compatibility_decision(
                compatibility_negative["sandbox_subject"], compatibility_negative["sandbox_decision"],
                load("conformance/sandbox/v1/suite.json"), sandbox_restore_candidate,
            )
    except AssertionError:
        pass
    else:
        raise AssertionError(f"Expected CompatibilityDecision fixture to fail: {case['id']}")

credential_negative = load("tests/semantic-invalid/credential-mediation-cases.json")
for case in credential_negative["cases"]:
    grant_candidate = copy.deepcopy(credential_negative["secret_grant"])
    request_candidate = copy.deepcopy(credential_negative["request"])
    token_candidate = copy.deepcopy(credential_negative["token"])
    delivery_candidate = copy.deepcopy(credential_negative["delivery"])
    sender = grant_candidate["workload_identity"]
    revocation = None
    if case["mutation"] == "target_digest_mismatch":
        request_candidate["target"]["target_digest"] = "sha256:" + "f" * 64
        request_candidate["request_digest"] = canonical_digest({
            key: value for key, value in request_candidate.items() if key != "request_digest"
        })
    elif case["mutation"] == "sender_mismatch":
        sender = "spiffe://agent-platform/provider/other/workload"
    elif case["mutation"] == "expiry_exceeds_grant":
        token_candidate["exp"] += 1
    elif case["mutation"] == "revoked_before_use":
        revocation = secret_revocation
    try:
        validate_secret_mediation(
            grant_candidate, request_candidate, token_candidate, delivery_candidate,
            sender, parse_datetime("2026-07-16T09:10:00Z"),
            {
                "request": sandbox_exec,
                "tenant_id": manifest["tenant_id"],
                "principal_context_digest": execution_grant["principal_context_digest"],
                "execution_scope": {"kind": "work_order", "work_order_id": manifest["work_order_id"]},
                "provider_instance_id": "spi_native_sandbox",
                "provider_revision_id": "spr_01J00000000000000000000000",
                "provider_audience": "urn:agent-platform:provider-instance:spi_native_sandbox",
                "workload_identity": secret_grant["workload_identity"],
                "deadline_at": sandbox_exec["deadline_at"],
            },
            revocation,
        )
    except AssertionError:
        pass
    else:
        raise AssertionError(f"Expected Credential mediation fixture to fail: {case['id']}")

artifact_credential_negative = load(
    "tests/semantic-invalid/artifact-operation-credential-mediation-cases.json"
)
for case in artifact_credential_negative["cases"]:
    grant_candidate = copy.deepcopy(artifact_credential_negative["secret_grant"])
    request_candidate = copy.deepcopy(artifact_credential_negative["request"])
    token_candidate = copy.deepcopy(artifact_credential_negative["token"])
    delivery_candidate = copy.deepcopy(artifact_credential_negative["delivery"])
    target_request_candidate = copy.deepcopy(artifact_credential_negative["target_request"])
    if case["mutation"] == "execution_scope_mismatch":
        grant_candidate["execution_scope"]["artifact_operation_id"] = "aop_other_01J00000000000000000000"
    elif case["mutation"] == "provider_revision_mismatch":
        grant_candidate["provider_revision_id"] = "rpr_other_01J00000000000000000000"
    elif case["mutation"] == "target_request_digest_mismatch":
        grant_candidate["target"]["target_digest"] = "sha256:" + "f" * 64
        grant_candidate["target_request_digest"] = "sha256:" + "f" * 64
    grant_candidate["secret_grant_digest"] = canonical_digest({
        key: value for key, value in grant_candidate.items() if key != "secret_grant_digest"
    })
    request_candidate["secret_grant_digest"] = grant_candidate["secret_grant_digest"]
    request_candidate["target"] = copy.deepcopy(grant_candidate["target"])
    request_candidate["request_digest"] = canonical_digest({
        key: value for key, value in request_candidate.items() if key != "request_digest"
    })
    token_candidate["secret_grant_digest"] = grant_candidate["secret_grant_digest"]
    token_candidate["request_digest"] = request_candidate["request_digest"]
    try:
        validate_secret_mediation(
            grant_candidate, request_candidate, token_candidate, delivery_candidate,
            grant_candidate["workload_identity"], parse_datetime("2026-07-16T09:07:00Z"),
            {
                "request": target_request_candidate,
                "tenant_id": artifact_operation_capability_request["tenant_id"],
                "principal_context_digest": artifact_operation_capability_request["principal_context_digest"],
                "execution_scope": artifact_operation_capability_request["execution_scope"],
                "provider_instance_id": artifact_operation_capability_request["provider_instance_id"],
                "provider_revision_id": artifact_operation_capability_request["provider_revision_id"],
                "provider_audience": artifact_operation_resolution["selected_provider_audience"],
                "workload_identity": artifact_operation_secret_grant["workload_identity"],
                "deadline_at": artifact_operation_capability_request["deadline_at"],
            },
        )
    except AssertionError:
        pass
    else:
        raise AssertionError(
            f"Expected ArtifactOperation Credential mediation fixture to fail: {case['id']}"
        )

ingest_negative = load("tests/semantic-invalid/artifact-ingest-cases.json")
for case in ingest_negative["cases"]:
    request_candidate = copy.deepcopy(ingest_negative["request"])
    session_candidate = copy.deepcopy(ingest_negative["session"])
    budget_candidate = copy.deepcopy(ingest_negative["budget"])
    policy_candidate = copy.deepcopy(ingest_negative["policy"])
    permissions_candidate = copy.deepcopy(ingest_negative["permissions"])
    scan_candidate = copy.deepcopy(ingest_negative["scan_result"])
    finalize_candidate = copy.deepcopy(ingest_negative["finalize_command"])
    if case["mutation"] == "failed_scan":
        scan_candidate["result"] = "rejected"
        scan_candidate["scan_result_digest"] = canonical_digest({
            key: value for key, value in scan_candidate.items() if key != "scan_result_digest"
        })
    elif case["mutation"] == "scan_digest_mismatch":
        finalize_candidate["scan_result_digest"] = "sha256:" + "f" * 64
        finalize_candidate["command_digest"] = canonical_digest({
            key: value for key, value in finalize_candidate.items() if key != "command_digest"
        })
    elif case["mutation"] == "provider_finalize_authority":
        finalize_candidate["authority"] = "provider"
        finalize_candidate["command_digest"] = canonical_digest({
            key: value for key, value in finalize_candidate.items() if key != "command_digest"
        })
    elif case["mutation"] == "session_policy_binding_mismatch":
        session_candidate["policy_decision_digest"] = "sha256:" + "f" * 64
    elif case["mutation"] == "policy_media_binding_mismatch":
        policy_candidate["evaluations"][0]["rule_digest"] = "sha256:" + "f" * 64
        policy_candidate["decision_digest"] = canonical_digest({
            key: value for key, value in policy_candidate.items() if key != "decision_digest"
        })
        session_candidate["policy_decision_digest"] = policy_candidate["decision_digest"]
    elif case["mutation"] == "permissions_scope_mismatch":
        permissions_candidate["execution_scope"]["artifact_ingest_session_id"] = "ing_other"
        permissions_candidate["permissions_digest"] = canonical_digest({
            key: value for key, value in permissions_candidate.items()
            if key != "permissions_digest"
        })
        policy_candidate["effective_permissions_digest"] = permissions_candidate[
            "permissions_digest"
        ]
        policy_candidate["decision_digest"] = canonical_digest({
            key: value for key, value in policy_candidate.items() if key != "decision_digest"
        })
        session_candidate["effective_permissions_digest"] = permissions_candidate[
            "permissions_digest"
        ]
        session_candidate["policy_decision_digest"] = policy_candidate["decision_digest"]
    try:
        validate_artifact_ingest(
            request_candidate, session_candidate, budget_candidate, policy_candidate,
            permissions_candidate,
            scan_candidate, finalize_candidate,
        )
    except AssertionError:
        pass
    else:
        raise AssertionError(f"Expected Artifact ingest fixture to fail: {case['id']}")

validate_execution_topology(manifest, workflow_run, agent_run, runtime_start)
validate_workflow_root_binding(
    workflow_root_binding, workflow_run, agent_run, manifest
)
validate_agent_run_budget_allocation(
    root_budget_allocation, execution_budget, agent_run
)
validate_child_agent_admission(
    child_spawn_request, child_admission_decision, workflow_run, agent_run, agent_run, manifest,
    child_agent_run, child_manifest, child_runtime_start, execution_budget,
    root_budget_allocation, [agent_run],
)
validate_agent_run_control_fanout(
    control_fanout, [agent_run, child_agent_run],
    {agent_run["runtime_run_id"]: 2, child_agent_run["runtime_run_id"]: 1},
    cancel_control_request,
)
validate_agent_run_control_fanout(
    progressed_control_fanout, [agent_run, child_agent_run],
    {agent_run["runtime_run_id"]: 2, child_agent_run["runtime_run_id"]: 1},
    cancel_control_request, control_fanout,
)
validate_multiagent_terminal(
    "succeeded", [(True, "succeeded")], "completed"
)
renewed_runtime_start = copy.deepcopy(runtime_start)
renewed_runtime_start["invocation_attempt_id"] = renewed_runtime_authorization[
    "artifact_grants"
][0]["invocation_attempt_id"]
renewed_runtime_start["runtime_authorization"] = renewed_runtime_authorization
validate_runtime_authorization(
    renewed_runtime_authorization,
    manifest,
    renewed_runtime_start,
    runtime_start["runtime_authorization"],
)
validate_runtime_token(runtime_token, manifest, agent_run, runtime_start)
validate_runtime_token(runtime_command_token, manifest, agent_run, runtime_start, runtime_command)
validate_runtime_token(runtime_status_token, manifest, agent_run, runtime_start, runtime_status_descriptor)
validate_runtime_token(runtime_event_token, manifest, agent_run, runtime_start, runtime_event_descriptor)
validate_sandbox_spec(sandbox_spec, manifest, sandbox_capabilities)
validate_sandbox_spec(child_sandbox_spec, child_manifest, sandbox_capabilities)
sandbox_resolution = next(
    item for item in manifest["capability_resolutions"]
    if item["resolution_id"] == sandbox_spec["provider_resolution_id"]
)
sandbox_token_cases = [
    (sandbox_token, sandbox_create, sandbox_create["spec"]["sandbox_id"]),
    (load("examples/contracts/sandbox-restore-operation-token-claims.json"), sandbox_restore, sandbox_restore["spec"]["sandbox_id"]),
    (load("examples/contracts/sandbox-desired-state-operation-token-claims.json"), sandbox_desired_state, sandbox_spec["sandbox_id"]),
    (load("examples/contracts/sandbox-lease-operation-token-claims.json"), sandbox_lease, sandbox_spec["sandbox_id"]),
    (load("examples/contracts/sandbox-exec-operation-token-claims.json"), sandbox_exec, sandbox_spec["sandbox_id"]),
    (load("examples/contracts/sandbox-cancel-exec-operation-token-claims.json"), sandbox_cancel_exec, sandbox_spec["sandbox_id"]),
    (load("examples/contracts/sandbox-runtime-session-operation-token-claims.json"), sandbox_runtime_session, sandbox_spec["sandbox_id"]),
    (load("examples/contracts/sandbox-snapshot-operation-token-claims.json"), sandbox_snapshot, sandbox_spec["sandbox_id"]),
    (load("examples/contracts/sandbox-terminate-operation-token-claims.json"), sandbox_terminate, sandbox_spec["sandbox_id"]),
    (load("examples/contracts/sandbox-status-operation-token-claims.json"), sandbox_status_descriptor, sandbox_spec["sandbox_id"]),
    (load("examples/contracts/sandbox-operation-read-token-claims.json"), sandbox_operation_read_descriptor, sandbox_spec["sandbox_id"]),
    (load("examples/contracts/sandbox-exec-result-operation-token-claims.json"), sandbox_exec_result_descriptor, sandbox_spec["sandbox_id"]),
    (load("examples/contracts/sandbox-snapshot-manifest-operation-token-claims.json"), sandbox_snapshot_manifest_descriptor, sandbox_spec["sandbox_id"]),
    (load("examples/contracts/sandbox-event-read-operation-token-claims.json"), sandbox_event_read_descriptor, sandbox_spec["sandbox_id"]),
]
for operation_token, operation_document, target_sandbox_id in sandbox_token_cases:
    validate_sandbox_token(
        operation_token, operation_document, sandbox_resolution, manifest,
        sandbox_id=target_sandbox_id,
    )
validate_service_access_token(
    service_access_token,
    registered_issuer="https://business.example.test",
    authenticated_subject="business-html-product",
    authenticated_client_id="html-product",
    allowed_scopes={"conversation:create", "session:create"},
)
validate_work_session_claims(
    work_session_claims, work_session_request, conversation,
    tenant_id=manifest["tenant_id"],
)
validate_plugin_compatibility_token(
    plugin_request, plugin_token,
    plugin_id="html-to-pptx",
    provider_revision_id="legacypr_html_to_pptx_01",
    audience="urn:agent-platform:provider-instance:legacy-html-to-pptx",
    permissions_digest=manifest["effective_permissions"]["permissions_digest"],
)
for operation_token, operation_document in (
    (plugin_status_token, plugin_status_descriptor),
    (plugin_cancel_token, plugin_cancel_request),
    (plugin_event_token, plugin_event_descriptor),
):
    validate_plugin_compatibility_token(
        plugin_request, operation_token,
        plugin_id="html-to-pptx",
        provider_revision_id="legacypr_html_to_pptx_01",
        audience="urn:agent-platform:provider-instance:legacy-html-to-pptx",
        permissions_digest=manifest["effective_permissions"]["permissions_digest"],
        operation_document=operation_document,
    )
capability_resolution = next(
    item for item in manifest["capability_resolutions"]
    if item["resolution_id"] == capability_request["provider_resolution_id"]
)
validate_capability_invocation(
    capability_request, capability_token, capability_resolution, manifest
)
validate_capability_invocation(
    capability_request, capability_status_token, capability_resolution, manifest,
    capability_status_operation, capability_token,
)
validate_capability_invocation(
    capability_request, capability_cancel_token, capability_resolution, manifest,
    capability_cancel, capability_status_token,
)
validate_capability_invocation(
    capability_request, capability_event_token, capability_resolution, manifest,
    capability_event_operation, capability_cancel_token,
)
validate_artifact_gateway(
    artifact_staging_grant, artifact_staging_object, artifact_stage_token,
    artifact_staging_commit, artifact_commit_token,
    capability_request["input_artifact_grants"][0], artifact_read_descriptor,
    artifact_read_token, capability_request,
    caller_subject=capability_resolution["selected_provider_audience"],
)
runtime_caller_subject = next(
    item["selected_provider_audience"]
    for item in manifest["capability_resolutions"]
    if item["resolution_id"] == manifest["agent_runtime"]["resolution_id"]
)
validate_egress_gateway(
    egress_destination, egress_request, egress_token, egress_response,
    manifest["gateway_bindings"]["egress"]["port"], runtime_start["runtime_authorization"],
    caller_subject=runtime_caller_subject,
)
validate_workspace_content_manifest(workspace_content_manifest)
validate_canonical_event_source(canonical_event)
validate_canonical_event_registry_binding(canonical_event, [platform_event_registry, event_registry])
validate_canonical_event_source(canonical_runtime_event)
validate_canonical_event_registry_binding(canonical_runtime_event, [platform_event_registry, event_registry])
for platform_scope_event in platform_scope_events:
    validate_canonical_event_source(platform_scope_event)
    validate_canonical_event_registry_binding(
        platform_scope_event, [platform_event_registry, event_registry]
    )
validate_artifact_operation_event_binding(platform_scope_events[1], artifact_operation)
validate_artifact_operation_event_binding(
    platform_scope_events[2], artifact_operation_cancel_requested,
)
canonical_core_event_negative = load(
    "tests/semantic-invalid/canonical-core-event-cases.json"
)
for case in canonical_core_event_negative["cases"]:
    mutation = case["mutation"]
    if mutation.startswith("artifact_operation"):
        candidate = copy.deepcopy(canonical_core_event_negative["artifact_operation"])
    elif mutation.startswith("artifact_ingest"):
        candidate = copy.deepcopy(canonical_core_event_negative["artifact_ingest"])
    elif mutation.startswith("compatibility"):
        candidate = copy.deepcopy(canonical_core_event_negative["compatibility"])
    else:
        candidate = copy.deepcopy(canonical_core_event_negative["secret_grant"])
    if mutation in {"artifact_operation_missing_scope", "secret_grant_missing_scope"}:
        candidate.pop("execution_scope")
    elif mutation == "artifact_ingest_cross_scope":
        candidate["execution_scope"]["artifact_ingest_session_id"] = "ing_other"
    elif mutation == "compatibility_with_scope":
        candidate["execution_scope"] = {
            "kind": "artifact_operation",
            "artifact_operation_id": "aop_other",
        }
    try:
        validate_canonical_event_source(candidate)
        validate_canonical_event_registry_binding(
            candidate, [platform_event_registry, event_registry]
        )
    except AssertionError:
        pass
    else:
        raise AssertionError(
            f"Expected Canonical core event fixture to fail: {case['id']}"
        )
validate_gateway_frames(gateway_connect, gateway_control)
validate_runtime_session_request(
    runtime_session_request, manifest, {"runtime:view", "runtime:control"}
)
validate_runtime_session_route(
    runtime_session_route, runtime_session_request, runtime_session_response,
    manifest, execution_grant,
)
validate_event_registry(event_registry)
validate_event_registry(platform_event_registry)
if manifest["event_registry"] != {
    "registry_id": event_registry["registry_id"],
    "registry_version": event_registry["registry_version"],
    "registry_digest": event_registry["registry_digest"],
}:
    raise AssertionError("RunManifest binds a different EventTypeRegistry revision")
validate_usage_contracts(meter, usage_entry, usage_report, settlement)
validate_usage_observations(capability_result, meter, usage_entry)
validate_policy_decision(policy_decision)
for conformance_suite in conformance_suites:
    validate_conformance_suite(conformance_suite)
validate_run_admission(manifest, context)
validate_run_admission(no_sandbox_manifest, context)
validate_run_admission(child_manifest, context)
grant = execution_grant
work_order_grant = load("examples/contracts/execution-grant-work-order-claims.json")
conversation_turn_request = load("examples/contracts/conversation-turn-request.json")
work_order_request = load("examples/contracts/work-order.json")
control_request = load("examples/contracts/work-order-control-request.json")
control_grant = load("examples/contracts/execution-grant-control-claims.json")
validate_execution_grant_request(
    grant,
    conversation_turn_request,
    authenticated_conversation_id=conversation["conversation_id"],
)
validate_run_manifest_request_binding(manifest, grant, conversation_turn_request)
validate_execution_grant_request(
    work_order_grant,
    work_order_request,
    authenticated_conversation_id=work_order_grant["conversation_id"],
)
validate_execution_grant_request(
    control_grant,
    control_request,
    authenticated_conversation_id=control_request["conversation_id"],
)
validate_execution_grant_request(
    cancel_control_grant,
    cancel_control_request,
    authenticated_conversation_id=cancel_control_request["conversation_id"],
)
validate_work_order_control_contract(control_request)
validate_work_order_control_contract(cancel_control_request)
bound_runtime_command = load("examples/contracts/agent-runtime-command.json")
control_runtime_input = load("examples/contracts/work-order-control-runtime-input.json")
if bound_runtime_command["authorized_control_request_id"] != control_request["control_request_id"]:
    raise AssertionError("Agent Runtime command references a different WorkOrderControlRequest")
if bound_runtime_command.get("input_id") != control_runtime_input["input_id"] or bound_runtime_command.get("input_content_digest") != control_runtime_input["content_digest"]:
    raise AssertionError("Agent Runtime command input does not match the authorized control input")
if control_runtime_input["content"] != control_request["content"]["content"]:
    raise AssertionError("Platform RuntimeInputEnvelope changes authorized control content")
commercial = grant["commercial_authorization"]
validate_self_digest(commercial, "commercial_authorization_digest")
validate_self_digest(execution_budget, "budget_digest")
if commercial != context["commercial_authorization"]:
    raise AssertionError("ExecutionGrant and Run admission bind different CommercialAuthorizationSnapshots")
if not set(grant["capabilities"]) <= set(commercial["authorized_capabilities"]):
    raise AssertionError("ExecutionGrant capabilities exceed commercial authorization")
if any(name not in commercial["authorized_limits"] or value > commercial["authorized_limits"][name] for name, value in grant["limits"].items()):
    raise AssertionError("ExecutionGrant limits exceed commercial authorization")
if policy_decision["commercial_authorization_id"] != commercial["commercial_authorization_id"] or policy_decision["commercial_authorization_digest"] != commercial["commercial_authorization_digest"]:
    raise AssertionError("PolicyDecision binds a different CommercialAuthorizationSnapshot")
if policy_decision["execution_budget_id"] != execution_budget["budget_id"] or policy_decision["execution_budget_digest"] != execution_budget["budget_digest"]:
    raise AssertionError("PolicyDecision binds a different ExecutionBudget")
if manifest["policy_decision"] != policy_decision:
    raise AssertionError("RunManifest binds a different PolicyDecision")
if manifest["execution_budget"] != execution_budget:
    raise AssertionError("RunManifest binds a different ExecutionBudget")
if usage_report["commercial_authorization_digest"] != commercial["commercial_authorization_digest"]:
    raise AssertionError("UsageReport binds a different CommercialAuthorizationSnapshot")
if settlement["commercial_authorization_digest"] != commercial["commercial_authorization_digest"]:
    raise AssertionError("Settlement envelope binds a different CommercialAuthorizationSnapshot")
manual = load("examples/contracts/sandbox-manual-review-decision.json")
validate_self_digest(manual, "decision_digest")
invocation_manual = load("examples/contracts/invocation-manual-review-decision.json")
validate_self_digest(invocation_manual, "decision_digest")

grant_binding_negative = load("tests/semantic-invalid/execution-grant-request-binding-cases.json")
for case in grant_binding_negative["cases"]:
    candidate_grant = copy.deepcopy(grant)
    candidate_request = copy.deepcopy(conversation_turn_request)
    authenticated_conversation_id = conversation["conversation_id"]
    if case["mutation"] == "request_digest_mismatch":
        candidate_grant["request_digest"] = "sha256:" + "f" * 64
    elif case["mutation"] == "request_contract_mismatch":
        candidate_grant["request_contract_id"] = "urn:agent-platform:work-order-request:v1"
    elif case["mutation"] == "client_message_mismatch":
        candidate_request["client_message_id"] = "client-msg-other"
        candidate_grant["request_digest"] = canonical_digest({
            key: value for key, value in candidate_request.items() if key != "execution_grant"
        })
    else:
        raise AssertionError(f"Unknown ExecutionGrant binding mutation: {case['mutation']}")
    try:
        validate_execution_grant_request(
            candidate_grant,
            candidate_request,
            authenticated_conversation_id=authenticated_conversation_id,
        )
    except AssertionError:
        pass
    else:
        raise AssertionError(f"Expected ExecutionGrant binding fixture to fail: {case['id']}")

architecture_negative = load("tests/semantic-invalid/architecture-closure-cases.json")
for case in architecture_negative["cases"]:
    mutation = case["mutation"]
    try:
        if mutation == "provider_runtime_wrong_port":
            candidate = copy.deepcopy(context)
            runtime_revision = next(item for item in candidate["provider_revisions"] if item["provider_kind"] == "agent_runtime")
            runtime_revision["port"]["protocol"] = "capability-provider"
            validate_provider_architecture(candidate, conformance_suites)
        elif mutation == "orchestration_digest_mismatch":
            candidate_manifest = copy.deepcopy(manifest)
            candidate_manifest["orchestration_binding"]["binding_digest"] = "sha256:" + "f" * 64
            validate_execution_topology(candidate_manifest, workflow_run, agent_run, runtime_start)
        elif mutation == "agent_run_manifest_mismatch":
            candidate_agent_run = copy.deepcopy(agent_run)
            candidate_agent_run["run_manifest_digest"] = "sha256:" + "f" * 64
            validate_execution_topology(manifest, workflow_run, candidate_agent_run, runtime_start)
        elif mutation == "event_registry_duplicate":
            candidate = copy.deepcopy(event_registry)
            candidate["definitions"].append(copy.deepcopy(candidate["definitions"][0]))
            candidate["registry_digest"] = canonical_digest({key: item for key, item in candidate.items() if key != "registry_digest"})
            validate_event_registry(candidate)
        elif mutation == "usage_final_partial":
            candidate = copy.deepcopy(usage_report)
            candidate["entries"][0]["measurement_status"] = "partial"
            candidate["usage_report_digest"] = canonical_digest({key: item for key, item in candidate.items() if key != "usage_report_digest"})
            validate_usage_contracts(meter, candidate["entries"][0], candidate, settlement)
        elif mutation == "policy_deny_overridden":
            candidate = copy.deepcopy(policy_decision)
            candidate["evaluations"].append({
                "subject_kind": "egress", "subject_id": "forbidden", "action": "deny",
                "source": "platform", "rule_digest": "sha256:" + "f" * 64,
            })
            candidate["decision_digest"] = canonical_digest({key: item for key, item in candidate.items() if key != "decision_digest"})
            validate_policy_decision(candidate)
        elif mutation == "conformance_unknown_dependency":
            candidate = copy.deepcopy(conformance_suites[0])
            candidate["profiles"][0]["depends_on"] = ["missing-profile"]
            candidate["suite_digest"] = canonical_digest({key: item for key, item in candidate.items() if key != "suite_digest"})
            validate_conformance_suite(candidate)
        elif mutation == "execution_topology_cross_tenant":
            candidate_start = copy.deepcopy(runtime_start)
            candidate_start["tenant_id"] = "ten_other"
            candidate_start["request_digest"] = canonical_digest({key: item for key, item in candidate_start.items() if key != "request_digest"})
            validate_execution_topology(manifest, workflow_run, agent_run, candidate_start)
        elif mutation == "workflow_root_mismatch":
            candidate_binding = copy.deepcopy(workflow_root_binding)
            candidate_binding["root_agent_run_id"] = "agr_other"
            candidate_binding["binding_digest"] = canonical_digest({
                key: value for key, value in candidate_binding.items() if key != "binding_digest"
            })
            validate_workflow_root_binding(
                candidate_binding, workflow_run, agent_run, manifest
            )
        elif mutation == "provider_suite_digest_mismatch":
            candidate = copy.deepcopy(context)
            candidate["provider_revisions"][0]["conformance"][0]["suite_digest"] = "sha256:" + "f" * 64
            validate_provider_architecture(candidate, conformance_suites)
        elif mutation == "settlement_usage_binding_mismatch":
            candidate = copy.deepcopy(settlement)
            candidate["usage_report"]["tenant_id"] = "ten_other"
            candidate["settlement_envelope_digest"] = canonical_digest({key: item for key, item in candidate.items() if key != "settlement_envelope_digest"})
            validate_usage_contracts(meter, usage_entry, usage_report, candidate)
        elif mutation == "gateway_duplicate_resume_channel":
            candidate = copy.deepcopy(gateway_connect)
            candidate["resume_cursors"].append({"channel": "terminal", "sequence": 40})
            validate_gateway_frames(candidate, gateway_control)
        elif mutation == "runtime_token_request_digest_mismatch":
            candidate = copy.deepcopy(runtime_token)
            candidate["operation_request_digest"] = "sha256:" + "f" * 64
            validate_runtime_token(candidate, manifest, agent_run, runtime_start)
        elif mutation == "provider_resolution_decision_digest_mismatch":
            candidate = copy.deepcopy(manifest["capability_resolutions"][0])
            candidate["decision_digest"] = "sha256:" + "f" * 64
            validate_provider_resolution(candidate)
        elif mutation == "provider_resolution_multiple_selected":
            candidate = copy.deepcopy(manifest["capability_resolutions"][0])
            duplicate = copy.deepcopy(candidate["candidate_evaluations"][0])
            duplicate["provider_instance_id"] = "provider-other"
            duplicate["provider_revision_id"] = "revision-other"
            duplicate["evidence_digest"] = "sha256:" + "e" * 64
            candidate["candidate_evaluations"].append(duplicate)
            candidate["decision_digest"] = canonical_digest({
                key: value for key, value in candidate.items() if key != "decision_digest"
            })
            validate_provider_resolution(candidate)
        else:
            raise AssertionError(f"Unknown architecture closure mutation: {mutation}")
    except AssertionError:
        pass
    else:
        raise AssertionError(f"Expected architecture closure fixture to fail: {case['id']}")

negative = load("tests/semantic-invalid/run-manifest-cases.json")
for case in negative["cases"]:
    value = copy.deepcopy(manifest)
    registry = copy.deepcopy(context)
    mutation = case["mutation"]
    if mutation == "duplicate_sandbox_slot":
        duplicate = copy.deepcopy(value["sandboxes"][0]); duplicate["sandbox_id"] = "sbx_duplicate"; value["sandboxes"].append(duplicate)
    elif mutation == "missing_primary_slot":
        value["primary_sandbox_slot_key"] = "missing-slot"
    elif mutation == "wrong_run_manifest_digest":
        value["run_manifest_digest"] = "sha256:" + "0" * 64
    elif mutation == "conflicting_revision_snapshot":
        sandbox_resolution = next(
            item for item in value["capability_resolutions"]
            if item["resolution_id"] == value["sandboxes"][0]["resolution_id"]
        )
        sandbox_resolution["selected_provider_revision"]["configuration_digest"] = "sha256:" + "f" * 64
    elif mutation == "unadmitted_experience":
        value["selected_experiences"] = [{
            "selection": {
                "kind": "template",
                "catalog_entry_id": "unadmitted/template",
                "revision_id": "unadmitted-revision",
                "revision_digest": "sha256:" + "9" * 64,
                "capability_id": "template.html.generate",
            },
            "provider_instance_id": value["capability_resolutions"][0]["selected_provider_instance_id"],
            "provider_revision": copy.deepcopy(value["capability_resolutions"][0]["selected_provider_revision"]),
        }]
    elif mutation == "unauthorized_experience_entitlement":
        registry["commercial_authorization"]["authorized_entitlements"] = []
        registry["commercial_authorization"]["commercial_authorization_digest"] = canonical_digest({key: item for key, item in registry["commercial_authorization"].items() if key != "commercial_authorization_digest"})
        value["commercial_authorization"]["commercial_authorization_digest"] = registry["commercial_authorization"]["commercial_authorization_digest"]
    elif mutation == "missing_required_experience_tag":
        registry["experience_requirements"][0]["required_tags"] = ["nonexistent-tag"]
    elif mutation == "commercial_authorization_digest_mismatch":
        value["commercial_authorization"]["commercial_authorization_digest"] = "sha256:" + "7" * 64
    elif mutation == "scenario_definition_mismatch":
        registry["scenario_definition"]["id"] = "other-scenario"
        registry["scenario_definition"]["definition_digest"] = canonical_digest({key: item for key, item in registry["scenario_definition"].items() if key != "definition_digest"})
    else:
        raise AssertionError(f"Unknown mutation: {mutation}")
    if mutation != "wrong_run_manifest_digest":
        for resolution in value["capability_resolutions"]:
            resolution["decision_digest"] = canonical_digest({
                key: item for key, item in resolution.items() if key != "decision_digest"
            })
        value["run_manifest_digest"] = canonical_digest({key: item for key, item in value.items() if key != "run_manifest_digest"})
    try:
        validate_run_admission(value, registry)
    except AssertionError:
        pass
    else:
        raise AssertionError(f"Expected semantic fixture to fail: {case['id']}")

admission_negative = load("tests/semantic-invalid/run-admission-cases.json")
for case in admission_negative["cases"]:
    value = copy.deepcopy(manifest)
    registry = copy.deepcopy(context)
    mutation = case["mutation"]
    if mutation == "forged_provider_revision_digest":
        runtime_resolution = next(item for item in value["capability_resolutions"] if item["resolution_id"] == value["agent_runtime"]["resolution_id"])
        runtime_resolution["selected_provider_revision"]["provider_revision_digest"] = "sha256:" + "f" * 64
    elif mutation == "extraneous_capability_resolution":
        extra = copy.deepcopy(value["capability_resolutions"][0]); extra["resolution_id"] = "res_extra"; extra["capability"] = {"id": "scenario.unrequested", "version": "1.0", "profile": None}; value["capability_resolutions"].append(extra)
    elif mutation == "forged_admission_decision_digest":
        sandbox_resolution = next(
            item for item in value["capability_resolutions"]
            if item["resolution_id"] == value["sandboxes"][0]["resolution_id"]
        )
        sandbox_resolution["selected_provider_revision"]["admission_decision_digest"] = "sha256:" + "e" * 64
    elif mutation == "stale_admission_decision":
        previous = registry["admission_decisions"][0]
        revoked = {"decision_id": "pad_revoked_later", "provider_revision_id": previous["provider_revision_id"], "provider_revision_digest": previous["provider_revision_digest"], "decision_sequence": 2, "decision": "revoked", "reason": "Test revocation", "evidence_digest": "sha256:" + "9" * 64, "decided_by": "principal:test", "decided_at": "2026-07-16T09:30:00Z", "supersedes_decision_id": previous["decision_id"], "decision_digest": "sha256:" + "0" * 64}
        revoked["decision_digest"] = canonical_digest({key: item for key, item in revoked.items() if key != "decision_digest"}); registry["admission_decisions"].append(revoked)
    elif mutation == "forged_capability_definition_digest":
        value["capability_resolutions"][0]["capability_definition_digest"] = "sha256:" + "a" * 64
    elif mutation == "sandbox_unsupported_capability":
        value["sandboxes"][0]["required_capabilities"] = [{"id": "tool.echo", "version": "1.0", "profile": "default"}]
    elif mutation == "agent_runtime_resolution_missing":
        value["agent_runtime"]["resolution_id"] = "res_missing_runtime"
    elif mutation == "capability_incompatible_provider_kind":
        value["capability_resolutions"][1]["selected_provider_revision"] = copy.deepcopy(value["capability_resolutions"][0]["selected_provider_revision"])
        value["capability_resolutions"][1]["selected_provider_instance_id"] = value["capability_resolutions"][0]["selected_provider_instance_id"]
    elif mutation == "missing_admission_predecessor":
        previous = registry["admission_decisions"][0]
        forged = copy.deepcopy(previous)
        forged.update({"decision_id": "pad_sequence_gap", "decision_sequence": 3, "supersedes_decision_id": "pad_missing", "decided_at": "2026-07-16T09:30:00Z"})
        forged["decision_digest"] = canonical_digest({key: item for key, item in forged.items() if key != "decision_digest"})
        registry["admission_decisions"].append(forged)
    elif mutation == "sandbox_resolution_wrong_kind":
        sandbox_resolution = next(
            item for item in value["capability_resolutions"]
            if item["resolution_id"] == value["sandboxes"][0]["resolution_id"]
        )
        runtime_resolution = next(
            item for item in value["capability_resolutions"]
            if item["resolution_id"] == value["agent_runtime"]["resolution_id"]
        )
        sandbox_resolution["selected_provider_instance_id"] = runtime_resolution["selected_provider_instance_id"]
        sandbox_resolution["selected_provider_revision"] = copy.deepcopy(runtime_resolution["selected_provider_revision"])
        sandbox_resolution["candidate_evaluations"] = copy.deepcopy(runtime_resolution["candidate_evaluations"])
        sandbox_resolution["decision_digest"] = canonical_digest({
            key: item for key, item in sandbox_resolution.items() if key != "decision_digest"
        })
    else:
        raise AssertionError(f"Unknown admission mutation: {mutation}")
    for resolution in value["capability_resolutions"]:
        resolution["decision_digest"] = canonical_digest({
            key: item for key, item in resolution.items() if key != "decision_digest"
        })
    value["run_manifest_digest"] = canonical_digest({key: item for key, item in value.items() if key != "run_manifest_digest"})
    try:
        validate_run_admission(value, registry)
    except AssertionError:
        pass
    else:
        raise AssertionError(f"Expected admission fixture to fail: {case['id']}")

def validate_case_decision_binding(
    record: dict[str, Any], case: dict[str, Any], decision: dict[str, Any],
    *, record_id_field: str, case_record_id_field: str,
) -> None:
    status_bindings = {
        "succeeded": ("resolve_success", "succeeded"),
        "failed": ("resolve_failure", "failed"),
        "cancelled": ("resolve_cancelled", "cancelled"),
        "abandoned": ("abandon", "abandoned"),
        "retry_scheduled": ("retry", "retry_approved"),
    }
    binding = status_bindings.get(record.get("status"))
    if binding is None:
        raise AssertionError("Aggregate status cannot carry a terminal/retry ManualReviewDecision binding")
    expected_decision, expected_outcome = binding
    validate_self_digest(case, "case_digest")
    validate_self_digest(decision, "decision_digest")
    if record[record_id_field] != case[case_record_id_field] or record[record_id_field] != decision[case_record_id_field]:
        raise AssertionError("Manual-review aggregate, case and decision bind different records")
    if record.get("reconciliation_case_id") != case["case_id"] or decision["case_id"] != case["case_id"]:
        raise AssertionError("Manual-review case_id reference is not closed")
    if record.get("manual_review_decision_id") != decision["decision_id"]:
        raise AssertionError("Manual-review decision_id reference is not closed")
    if record.get("current_attempt_id") != case["attempt_id"]:
        raise AssertionError("ReconciliationCase does not bind the aggregate's current attempt")
    if decision["case_version"] != case["case_version"] or decision["case_digest"] != case["case_digest"]:
        raise AssertionError("ManualReviewDecision does not bind the exact ReconciliationCase version")
    if case["status"] != "resolved" or case.get("resolved_outcome") != expected_outcome:
        raise AssertionError("ReconciliationCase outcome conflicts with the aggregate terminal/retry status")
    if decision["decision"] != expected_decision:
        raise AssertionError("ManualReviewDecision conflicts with the aggregate terminal/retry status")
    case_evidence, decision_evidence = set(case["evidence_references"]), set(decision["evidence_references"])
    if not case_evidence or not decision_evidence or not decision_evidence.issubset(case_evidence):
        raise AssertionError("Manual review must cite non-empty evidence recorded on the resolved case")
    if expected_decision == "abandon" and decision["risk_accepted"] is not True:
        raise AssertionError("Abandon requires explicit risk acceptance")
    parse_time = lambda value: datetime.fromisoformat(value.replace("Z", "+00:00"))
    opened_at = parse_time(case["opened_at"])
    resolved_at = parse_time(case["resolved_at"])
    decided_at = parse_time(decision["occurred_at"])
    if not opened_at <= resolved_at <= decided_at:
        raise AssertionError("Adjudication timestamps must satisfy opened_at <= resolved_at <= decision.occurred_at")
    for aggregate_field in ("updated_at", "completed_at"):
        if aggregate_field in record and decided_at > parse_time(record[aggregate_field]):
            raise AssertionError(f"Decision occurred after aggregate {aggregate_field}")


operation_schema = load("schemas/sandbox-operation-record.schema.json")
manual_schema = load("schemas/sandbox-manual-review-decision.schema.json")
operation_validator = Draft202012Validator(operation_schema, registry=SCHEMA_REGISTRY, format_checker=FormatChecker())
manual_validator = Draft202012Validator(manual_schema, registry=SCHEMA_REGISTRY, format_checker=FormatChecker())
operation = load("examples/contracts/sandbox-operation.json")
reconciliation = load("examples/contracts/sandbox-reconciliation-case.json")
validate_case_decision_binding(operation, reconciliation, manual, record_id_field="operation_id", case_record_id_field="operation_id")
if operation["current_attempt_number"] > operation["max_attempts"]:
    raise AssertionError("current_attempt_number exceeds max_attempts")
sandbox_negative = load("tests/semantic-invalid/sandbox-operation-cases.json")
for case in sandbox_negative["cases"]:
    candidate_operation = copy.deepcopy(operation)
    candidate_manual = copy.deepcopy(manual)
    if case["mutation"] == "attempt_number_exceeds_max":
        candidate_operation["current_attempt_number"] = candidate_operation["max_attempts"] + 1
        failed = candidate_operation["current_attempt_number"] > candidate_operation["max_attempts"]
    elif case["mutation"] == "running_without_current_attempt":
        candidate_operation["status"] = "running"; candidate_operation.pop("current_attempt_id", None)
        failed = bool(list(operation_validator.iter_errors(candidate_operation)))
    elif case["mutation"] == "abandon_without_risk_acceptance":
        candidate_manual["decision"] = "abandon"; candidate_manual["risk_accepted"] = False
        failed = bool(list(manual_validator.iter_errors(candidate_manual)))
    elif case["mutation"] == "cancelled_effect_completed":
        candidate_operation.update({
            "status": "cancelled", "terminal_reason": "cancelled", "completed_at": "2026-07-16T10:07:00Z",
            "cancellation_confirmation": {"confirmed_by": "provider", "evidence_reference": "evidence://provider/1", "external_effect_status": "effect_completed", "confirmed_at": "2026-07-16T10:07:00Z"},
        })
        failed = bool(list(operation_validator.iter_errors(candidate_operation)))
    elif case["mutation"] == "abandoned_without_manual_decision":
        candidate_operation.pop("manual_review_decision_id", None)
        failed = bool(list(operation_validator.iter_errors(candidate_operation)))
    elif case["mutation"] in {"forged_case_reference", "case_digest_mismatch", "empty_resolved_evidence"}:
        candidate_case = copy.deepcopy(reconciliation)
        if case["mutation"] == "forged_case_reference":
            candidate_operation["reconciliation_case_id"] = "src_forged"
        elif case["mutation"] == "case_digest_mismatch":
            candidate_manual["case_digest"] = "sha256:" + "f" * 64
            candidate_manual["decision_digest"] = canonical_digest({key: item for key, item in candidate_manual.items() if key != "decision_digest"})
        else:
            candidate_case["evidence_references"] = []
            candidate_case["case_digest"] = canonical_digest({key: item for key, item in candidate_case.items() if key != "case_digest"})
        try:
            validate_case_decision_binding(candidate_operation, candidate_case, candidate_manual, record_id_field="operation_id", case_record_id_field="operation_id")
        except AssertionError:
            failed = True
        else:
            failed = False
    else:
        raise AssertionError(f"Unknown Sandbox mutation: {case['mutation']}")
    if not failed:
        raise AssertionError(f"Expected Sandbox semantic fixture to fail: {case['id']}")

invocation_schema = load("schemas/invocation-record.schema.json")
invocation_manual_schema = load("schemas/invocation-manual-review-decision.schema.json")
invocation_validator = Draft202012Validator(invocation_schema, registry=SCHEMA_REGISTRY, format_checker=FormatChecker())
invocation_manual_validator = Draft202012Validator(invocation_manual_schema, registry=SCHEMA_REGISTRY, format_checker=FormatChecker())
invocation = load("examples/contracts/invocation-record.json")
invocation_reconciliation = load("examples/contracts/invocation-reconciliation-case.json")
validate_case_decision_binding(invocation, invocation_reconciliation, invocation_manual, record_id_field="invocation_id", case_record_id_field="invocation_id")
retry_invocation = load("examples/contracts/invocation-non-idempotent-retry.json")
retry_case = load("examples/contracts/invocation-retry-reconciliation-case.json")
retry_decision = load("examples/contracts/invocation-retry-manual-review-decision.json")
validate_case_decision_binding(retry_invocation, retry_case, retry_decision, record_id_field="invocation_id", case_record_id_field="invocation_id")
invocation_negative = load("tests/semantic-invalid/invocation-cases.json")
for case in invocation_negative["cases"]:
    candidate = copy.deepcopy(invocation)
    decision = copy.deepcopy(invocation_manual)
    if case["mutation"] == "attempt_count_exceeds_max":
        candidate["attempt_count"] = candidate["max_attempts"] + 1
        failed = candidate["attempt_count"] > candidate["max_attempts"]
    elif case["mutation"] == "executing_without_current_attempt":
        candidate["status"] = "executing"; candidate.pop("current_attempt_id", None)
        failed = bool(list(invocation_validator.iter_errors(candidate)))
    elif case["mutation"] == "abandoned_without_manual_decision":
        candidate.update({"status": "abandoned", "completed_at": "2026-07-16T10:45:00Z", "terminal_reason": "unknown external outcome"})
        candidate.pop("manual_review_decision_id", None)
        failed = bool(list(invocation_validator.iter_errors(candidate)))
    elif case["mutation"] == "abandon_without_risk_acceptance":
        decision["risk_accepted"] = False
        failed = bool(list(invocation_manual_validator.iter_errors(decision)))
    elif case["mutation"] in {"forged_case_reference", "forged_decision_reference", "case_digest_mismatch", "outcome_mismatch", "empty_resolved_evidence", "aggregate_status_mismatch", "decision_before_case_opened"}:
        candidate_case = copy.deepcopy(invocation_reconciliation)
        if case["mutation"] == "forged_case_reference":
            candidate["reconciliation_case_id"] = "irc_forged"
        elif case["mutation"] == "forged_decision_reference":
            candidate["manual_review_decision_id"] = "imd_forged"
        elif case["mutation"] == "case_digest_mismatch":
            decision["case_digest"] = "sha256:" + "e" * 64
            decision["decision_digest"] = canonical_digest({key: item for key, item in decision.items() if key != "decision_digest"})
        elif case["mutation"] == "outcome_mismatch":
            candidate_case["resolved_outcome"] = "failed"
            candidate_case["case_digest"] = canonical_digest({key: item for key, item in candidate_case.items() if key != "case_digest"})
        elif case["mutation"] == "aggregate_status_mismatch":
            candidate["status"] = "succeeded"
            candidate["result_reference"] = "artifact://result/contradictory"
        elif case["mutation"] == "decision_before_case_opened":
            decision["occurred_at"] = "2026-07-16T09:00:00Z"
            decision["decision_digest"] = canonical_digest({key: item for key, item in decision.items() if key != "decision_digest"})
        else:
            candidate_case["evidence_references"] = []
            candidate_case["case_digest"] = canonical_digest({key: item for key, item in candidate_case.items() if key != "case_digest"})
        try:
            validate_case_decision_binding(candidate, candidate_case, decision, record_id_field="invocation_id", case_record_id_field="invocation_id")
        except AssertionError:
            failed = True
        else:
            failed = False
    elif case["mutation"] == "non_idempotent_retry_without_approval":
        candidate = copy.deepcopy(retry_invocation)
        candidate.pop("reconciliation_case_id", None)
        candidate.pop("manual_review_decision_id", None)
        failed = bool(list(invocation_validator.iter_errors(candidate)))
    else:
        raise AssertionError(f"Unknown Invocation mutation: {case['mutation']}")
    if not failed:
        raise AssertionError(f"Expected Invocation semantic fixture to fail: {case['id']}")


def validate_invocation_attempt_sequence(aggregate: dict[str, Any], attempts: list[dict[str, Any]]) -> None:
    if aggregate["attempt_count"] > aggregate["max_attempts"] or len(attempts) != aggregate["attempt_count"]:
        raise AssertionError("Invocation aggregate attempt_count/max_attempts conflicts with Attempt history")
    if any(item["invocation_id"] != aggregate["invocation_id"] for item in attempts):
        raise AssertionError("InvocationAttempt belongs to a different Invocation")
    if any(item["request_digest"] != aggregate["request_digest"] for item in attempts):
        raise AssertionError("InvocationAttempt request_digest differs from the immutable aggregate request")
    attempt_ids = [item["invocation_attempt_id"] for item in attempts]
    attempt_numbers = [item["attempt_number"] for item in attempts]
    fencing_tokens = [item["fencing_token"] for item in attempts]
    if len(attempt_ids) != len(set(attempt_ids)):
        raise AssertionError("InvocationAttempt IDs must be unique")
    if attempt_numbers != list(range(1, len(attempts) + 1)):
        raise AssertionError("Invocation attempt numbers must be contiguous and start at one")
    if any(current <= previous for previous, current in zip(fencing_tokens, fencing_tokens[1:])):
        raise AssertionError("Invocation fencing tokens must be unique and strictly increasing")
    if aggregate.get("current_attempt_id") != attempt_ids[-1]:
        raise AssertionError("Invocation current_attempt_id must reference the latest Attempt")


invocation_attempt_fixture = load("tests/semantic-invalid/invocation-attempt-sequence.json")
invocation_attempt_aggregate = load(invocation_attempt_fixture["aggregate"])
invocation_attempts = [load(path) for path in invocation_attempt_fixture["attempts"]]
validate_invocation_attempt_sequence(invocation_attempt_aggregate, invocation_attempts)
for case in invocation_attempt_fixture["cases"]:
    candidate_aggregate = copy.deepcopy(invocation_attempt_aggregate)
    candidate_attempts = copy.deepcopy(invocation_attempts)
    if case["mutation"] == "duplicate_fencing_token":
        candidate_attempts[1]["fencing_token"] = candidate_attempts[0]["fencing_token"]
    elif case["mutation"] == "attempt_number_gap":
        candidate_attempts[1]["attempt_number"] = 3
    elif case["mutation"] == "current_attempt_mismatch":
        candidate_aggregate["current_attempt_id"] = candidate_attempts[0]["invocation_attempt_id"]
    else:
        raise AssertionError(f"Unknown InvocationAttempt mutation: {case['mutation']}")
    try:
        validate_invocation_attempt_sequence(candidate_aggregate, candidate_attempts)
    except AssertionError:
        pass
    else:
        raise AssertionError(f"Expected InvocationAttempt sequence fixture to fail: {case['id']}")

attempt_sequence = load("tests/semantic-invalid/sandbox-attempt-sequence.json")
attempts = attempt_sequence["attempts"]
attempt_numbers = [item["attempt_number"] for item in attempts]
fencing_tokens = [item["fencing_token"] for item in attempts]
if attempt_numbers != list(range(1, len(attempts) + 1)):
    raise AssertionError("Sandbox attempt numbers must be contiguous and start at one")
if any(current <= previous for previous, current in zip(fencing_tokens, fencing_tokens[1:])):
    pass
else:
    raise AssertionError("Expected Sandbox fencing-token negative fixture to fail")


def validate_conversation_message_sequence(messages: list[dict[str, Any]]) -> None:
    if not messages:
        return
    conversation_id = messages[0]["conversation_id"]
    identifiers = [item["message_id"] for item in messages]
    if len(identifiers) != len(set(identifiers)):
        raise AssertionError("Conversation message IDs must be unique")
    if [item["message_sequence"] for item in messages] != list(range(1, len(messages) + 1)):
        raise AssertionError("Conversation message_sequence must be contiguous from one")
    if any(item["conversation_id"] != conversation_id for item in messages):
        raise AssertionError("Conversation message history contains a cross-Conversation record")
    prior: set[str] = set()
    for item in messages:
        parent = item.get("parent_message_id")
        if parent is not None and parent not in prior:
            raise AssertionError("Conversation parent_message_id must reference a prior immutable message")
        prior.add(item["message_id"])


conversation_fixture = load("tests/semantic-invalid/conversation-message-sequence.json")
validate_conversation_message_sequence(conversation_fixture["messages"])
for case in conversation_fixture["cases"]:
    candidate = copy.deepcopy(conversation_fixture["messages"])
    if case["mutation"] == "sequence_gap":
        candidate[1]["message_sequence"] = 3
    elif case["mutation"] == "duplicate_message_id":
        candidate[1]["message_id"] = candidate[0]["message_id"]
    elif case["mutation"] == "parent_not_prior":
        candidate[1]["parent_message_id"] = "msg_future"
    elif case["mutation"] == "cross_conversation":
        candidate[1]["conversation_id"] = "conv_other"
    else:
        raise AssertionError(f"Unknown Conversation mutation: {case['mutation']}")
    try:
        validate_conversation_message_sequence(candidate)
    except AssertionError:
        pass
    else:
        raise AssertionError(f"Expected Conversation semantic fixture to fail: {case['id']}")


def validate_runtime_recording_sequence(recording: dict[str, Any], chunks: list[dict[str, Any]]) -> None:
    if recording["chunk_count"] != len(chunks):
        raise AssertionError("RuntimeRecording chunk_count conflicts with persisted chunk history")
    if any(item["recording_id"] != recording["recording_id"] for item in chunks):
        raise AssertionError("RuntimeRecording contains a chunk from another recording")
    by_channel: dict[str, list[dict[str, Any]]] = {}
    for item in chunks:
        by_channel.setdefault(item["channel"], []).append(item)
        start = datetime.fromisoformat(item["started_at"].replace("Z", "+00:00"))
        end = datetime.fromisoformat(item["ended_at"].replace("Z", "+00:00"))
        if start > end or item["start_work_sequence"] > item["end_work_sequence"]:
            raise AssertionError("RuntimeRecording chunk chronology is reversed")
    for channel_chunks in by_channel.values():
        if [item["chunk_sequence"] for item in channel_chunks] != list(range(1, len(channel_chunks) + 1)):
            raise AssertionError("RuntimeRecording chunk_sequence must be contiguous per channel")
        for previous, current in zip(channel_chunks, channel_chunks[1:]):
            if current["start_work_sequence"] < previous["end_work_sequence"]:
                raise AssertionError("RuntimeRecording work_sequence ranges overlap or reverse")


recording_fixture = load("tests/semantic-invalid/runtime-recording-sequence.json")
validate_runtime_recording_sequence(recording_fixture["recording"], recording_fixture["chunks"])
for case in recording_fixture["cases"]:
    candidate = copy.deepcopy(recording_fixture["chunks"])
    if case["mutation"] == "sequence_gap":
        candidate[1]["chunk_sequence"] = 3
    elif case["mutation"] == "cross_recording":
        candidate[1]["recording_id"] = "rec_other"
    elif case["mutation"] == "work_sequence_reversal":
        candidate[1]["start_work_sequence"] = 1
    elif case["mutation"] == "time_reversal":
        candidate[1]["ended_at"] = "2026-07-15T10:04:00Z"
        candidate[1]["started_at"] = "2026-07-15T10:05:00Z"
    else:
        raise AssertionError(f"Unknown RuntimeRecording mutation: {case['mutation']}")
    try:
        validate_runtime_recording_sequence(recording_fixture["recording"], candidate)
    except AssertionError:
        pass
    else:
        raise AssertionError(f"Expected RuntimeRecording semantic fixture to fail: {case['id']}")


def validate_runtime_command_sequence(commands: list[dict[str, Any]]) -> None:
    if not commands:
        return
    runtime_run_id = commands[0]["runtime_run_id"]
    identifiers = [item["command_id"] for item in commands]
    if len(identifiers) != len(set(identifiers)):
        raise AssertionError("Agent Runtime command IDs must be unique")
    if [item["command_sequence"] for item in commands] != list(range(1, len(commands) + 1)):
        raise AssertionError("Agent Runtime command_sequence must be contiguous from one")
    if any(item["runtime_run_id"] != runtime_run_id for item in commands):
        raise AssertionError("Agent Runtime command history contains another run")
    fencing = [item["fencing_token"] for item in commands]
    if any(current <= previous for previous, current in zip(fencing, fencing[1:])):
        raise AssertionError("Agent Runtime command fencing_token must strictly increase")
    mark_checks(
        "runtime_command.sequence",
        "runtime_command.idempotency",
        "runtime_command.fencing",
    )


def validate_system_safety_control(
    control: dict[str, Any], manifest: dict[str, Any], runtime_start: dict[str, Any],
    *, authenticated_issuer: str = "spn_agent_safety_controller",
) -> None:
    validate_self_digest(control, "control_digest")
    if any((
        control["tenant_id"] != manifest["tenant_id"],
        control["work_order_id"] != manifest["work_order_id"],
        control["runtime_run_id"] != runtime_start["runtime_run_id"],
        control["issued_by"] != "platform_safety_controller",
        control["issuer_subject_id"] != authenticated_issuer,
    )):
        raise AssertionError("SystemSafetyControl crosses its active execution scope")
    evidence = control["trigger_evidence"]
    observed_at = parse_datetime(evidence["observed_at"])
    issued_at = parse_datetime(control["issued_at"])
    if observed_at > issued_at:
        raise AssertionError("SystemSafetyControl was issued before its trigger evidence was observed")
    if control["reason"] == "commercial_authorization_expired":
        authorization = runtime_start["runtime_authorization"]
        if any((
            evidence["evidence_id"] != authorization["authorization_id"],
            evidence["evidence_contract_id"] != "urn:agent-platform:runtime-authorization:v1",
            evidence["evidence_digest"] != authorization["authorization_digest"],
            observed_at < parse_datetime(authorization["expires_at"]),
        )):
            raise AssertionError("Expired-authorization safety control lacks matching expiry evidence")
    hard_cancel_reasons = {
        "commercial_authorization_expired",
        "commercial_authorization_revoked",
        "execution_deadline_exceeded",
        "tenant_suspended",
        "provider_admission_revoked",
        "budget_exhausted",
        "platform_shutdown",
    }
    if (
        control["action"] not in {"pause", "cancel"}
        or control["reason"] in hard_cancel_reasons and control["action"] != "cancel"
    ):
        raise AssertionError("SystemSafetyControl can only reduce execution authority")
    mark_checks(
        "system_safety_control.digest",
        "system_safety_control.scope",
        "system_safety_control.evidence",
        "system_safety_control.reduction_only",
    )


def validate_agent_runtime_command(
    command: dict[str, Any], manifest: dict[str, Any], runtime_start: dict[str, Any],
    *, control_request: dict[str, Any] | None = None,
    persisted_input: dict[str, Any] | None = None,
    system_safety_control: dict[str, Any] | None = None,
    child_admission_decision: dict[str, Any] | None = None,
) -> None:
    validate_self_digest(command, "command_digest")
    if command["runtime_run_id"] != runtime_start["runtime_run_id"]:
        raise AssertionError("Agent Runtime command crosses its RuntimeRun")
    user_authorized = "authorized_control_request_id" in command
    system_authorized = "system_safety_control_id" in command
    if user_authorized and system_authorized:
        raise AssertionError("Agent Runtime command mixes user and system control authority")
    if user_authorized:
        if control_request is None:
            raise AssertionError("User Runtime command lacks its persisted WorkOrderControlRequest")
        if any((
            command["authorized_control_request_id"] != control_request["control_request_id"],
            command["type"] != control_request["action"],
            control_request["work_order_id"] != manifest["work_order_id"],
        )):
            raise AssertionError("Agent Runtime command differs from its authorized control request")
        if command["type"] in {"append_input", "interrupt"}:
            if persisted_input is None:
                raise AssertionError("Agent Runtime input command lacks its immutable persisted input")
            if any((
                command["input_id"] != persisted_input["input_id"],
                command["input_content_digest"] != persisted_input["content_digest"],
                control_request["content"]["content_digest"] != persisted_input["content_digest"],
                persisted_input["content_digest"] != canonical_digest(persisted_input["content"]),
            )):
                raise AssertionError("Agent Runtime input command differs from persisted control input")
        mark_checks("runtime_command.user_control_binding")
    elif system_authorized:
        if system_safety_control is None:
            raise AssertionError("System Runtime command lacks its SystemSafetyControl")
        if any((
            command.get("system_safety_control_id") != system_safety_control["safety_control_id"],
            command.get("system_safety_control_digest") != system_safety_control["control_digest"],
            command["runtime_run_id"] != system_safety_control["runtime_run_id"],
            command["type"] != system_safety_control["action"],
            system_safety_control["tenant_id"] != manifest["tenant_id"],
            system_safety_control["work_order_id"] != manifest["work_order_id"],
        )):
            raise AssertionError("Agent Runtime command differs from SystemSafetyControl")
        mark_checks("runtime_command.system_safety_binding")
    elif command["type"] == "subagent_spawn_decision":
        if child_admission_decision is None:
            raise AssertionError("Spawn decision command lacks its Platform admission decision")
        if any((
            command["spawn_request_id"] != child_admission_decision["spawn_request_id"],
            command["child_agent_run_admission_decision_id"] != child_admission_decision["decision_id"],
            command["child_agent_run_admission_decision_digest"] != child_admission_decision["decision_digest"],
            command["spawn_outcome"] != child_admission_decision["outcome"],
            command["spawn_reason_codes"] != child_admission_decision["reason_codes"],
            command.get("child_agent_run_id") != child_admission_decision.get("child_agent_run_id"),
        )):
            raise AssertionError("Spawn decision command differs from its Platform admission decision")
        mark_checks("runtime_command.child_admission_binding")
    elif command["type"] != "checkpoint":
        raise AssertionError("Agent Runtime command lacks an authorized control source")
    mark_checks("runtime_command.digest")


def validate_commercial_authorization_revocation(
    notice: dict[str, Any], manifest: dict[str, Any], grant: dict[str, Any],
    *, authenticated_client_id: str, path_authorization_id: str, received_at: str,
    receipt: dict[str, Any] | None = None,
    expected_execution_scopes: list[dict[str, Any]] | None = None,
) -> None:
    validate_self_digest(notice, "revocation_digest")
    if parse_datetime(notice["effective_at"]) > parse_datetime(notice["issued_at"]):
        raise AssertionError("CommercialAuthorization revocation is not yet effective")
    if parse_datetime(notice["issued_at"]) > parse_datetime(received_at):
        raise AssertionError("CommercialAuthorization revocation exceeds allowed clock skew")
    if any((
        notice["external_tenant_id"] != grant["external_tenant_id"],
        authenticated_client_id != grant["client_app_id"],
    )):
        raise AssertionError("CommercialAuthorization revocation crosses Business sender scope")
    binding = manifest["commercial_authorization"]
    if any((
        notice["commercial_authorization_id"] != path_authorization_id,
        notice["commercial_authorization_id"] != binding["commercial_authorization_id"],
        notice["commercial_authorization_digest"] != binding["commercial_authorization_digest"],
        grant["commercial_authorization"]["commercial_authorization_id"]
        != binding["commercial_authorization_id"],
        grant["commercial_authorization"]["commercial_authorization_digest"]
        != binding["commercial_authorization_digest"],
    )):
        raise AssertionError("CommercialAuthorization revocation binds a different snapshot")
    if receipt is not None:
        validate_self_digest(receipt, "revocation_receipt_digest")
        targets = receipt["execution_cancellation_targets"]
        actual_scopes = {canonical_digest(item["execution_scope"]) for item in targets}
        expected_scopes = {
            canonical_digest(item) for item in (expected_execution_scopes or [])
        }
        work_session_intents = receipt["work_session_revocations"]
        all_outbox_ids = [item["outbox_message_id"] for item in targets + work_session_intents]
        if any((
            receipt["revocation_id"] != notice["revocation_id"],
            receipt["revocation_digest"] != notice["revocation_digest"],
            receipt["tenant_id"] != manifest["tenant_id"],
            receipt["client_app_id"] != authenticated_client_id,
            receipt["commercial_authorization_id"] != binding["commercial_authorization_id"],
            receipt["commercial_authorization_digest"] != binding["commercial_authorization_digest"],
            parse_datetime(receipt["deny_effective_at"]) > parse_datetime(receipt["accepted_at"]),
            actual_scopes != expected_scopes,
            len(actual_scopes) != len(targets),
            any(item["action"] != "cancel" for item in targets),
            len({item["cancellation_intent_id"] for item in targets}) != len(targets),
            len({item["revocation_intent_id"] for item in work_session_intents})
            != len(work_session_intents),
            len(set(all_outbox_ids)) != len(all_outbox_ids),
        )):
            raise AssertionError("CommercialAuthorization revocation receipt or fan-out is not closed")
        if receipt["fanout_status"] == "completed" and (
            any(item["status"] not in {"completed", "already_terminal"} for item in targets)
            or any(
                item["status"] not in {"completed", "already_inactive"}
                for item in work_session_intents
            )
        ):
            raise AssertionError("CommercialAuthorization revocation completed before its fan-out")
        mark_checks("commercial_revocation.fanout")
    mark_checks(
        "commercial_revocation.digest",
        "commercial_revocation.time_order",
        "commercial_revocation.sender_binding",
        "commercial_revocation.authorization_binding",
    )


runtime_command_fixture = load("tests/semantic-invalid/agent-runtime-command-sequence.json")
validate_runtime_command_sequence(runtime_command_fixture["commands"])
for case in runtime_command_fixture["cases"]:
    candidate = copy.deepcopy(runtime_command_fixture["commands"])
    if case["mutation"] == "sequence_gap":
        candidate[1]["command_sequence"] = 3
    elif case["mutation"] == "stale_fencing":
        candidate[1]["fencing_token"] = candidate[0]["fencing_token"]
    elif case["mutation"] == "duplicate_id":
        candidate[1]["command_id"] = candidate[0]["command_id"]
    elif case["mutation"] == "cross_run":
        candidate[1]["runtime_run_id"] = "runtime_other"
    else:
        raise AssertionError(f"Unknown Agent Runtime command mutation: {case['mutation']}")
    try:
        validate_runtime_command_sequence(candidate)
    except AssertionError:
        pass
    else:
        raise AssertionError(f"Expected Agent Runtime command semantic fixture to fail: {case['id']}")

validate_system_safety_control(system_safety_control, manifest, runtime_start)
validate_agent_runtime_command(
    runtime_command,
    manifest,
    runtime_start,
    control_request=control_request,
    persisted_input=control_runtime_input,
)
validate_agent_runtime_command(
    system_safety_command,
    manifest,
    runtime_start,
    system_safety_control=system_safety_control,
)
validate_agent_runtime_command(
    spawn_decision_command,
    manifest,
    runtime_start,
    child_admission_decision=child_admission_decision,
)

for path, validator in (
    (
        "tests/semantic-invalid/child-spawn-input-mismatch.json",
        lambda value: validate_child_agent_admission(
            value, child_admission_decision, workflow_run, agent_run, agent_run, manifest, child_agent_run,
            child_manifest, child_runtime_start, execution_budget,
            root_budget_allocation, [agent_run],
        ),
    ),
    (
        "tests/semantic-invalid/child-budget-allocation-wider.json",
        lambda value: validate_agent_run_budget_allocation(
            value, execution_budget, child_agent_run, root_budget_allocation
        ),
    ),
    (
        "tests/semantic-invalid/child-agent-run-parent-mismatch.json",
        lambda value: validate_child_agent_admission(
            child_spawn_request, child_admission_decision, workflow_run, agent_run, agent_run, manifest, value,
            child_manifest, child_runtime_start, execution_budget,
            root_budget_allocation, [agent_run],
        ),
    ),
    (
        "tests/semantic-invalid/child-admission-provider-mismatch.json",
        lambda value: validate_child_agent_admission(
            child_spawn_request, value, workflow_run, agent_run, agent_run, manifest, child_agent_run,
            child_manifest, child_runtime_start, execution_budget,
            root_budget_allocation, [agent_run],
        ),
    ),
    (
        "tests/semantic-invalid/child-admission-workspace-mismatch.json",
        lambda value: validate_child_agent_admission(
            child_spawn_request, value, workflow_run, agent_run, agent_run, manifest, child_agent_run,
            child_manifest, child_runtime_start, execution_budget,
            root_budget_allocation, [agent_run],
        ),
    ),
):
    try:
        validator(load(path))
    except AssertionError:
        pass
    else:
        raise AssertionError(f"Expected multi-agent semantic fixture to fail: {path}")

try:
    validate_agent_run_control_fanout(
        load("tests/semantic-invalid/agent-run-control-fanout-authority-mismatch.json"),
        [agent_run, child_agent_run],
        {agent_run["runtime_run_id"]: 2, child_agent_run["runtime_run_id"]: 1},
        cancel_control_request,
    )
except AssertionError:
    pass
else:
    raise AssertionError("Expected mismatched fanout authority to fail")

try:
    validate_agent_run_control_fanout(
        load("tests/semantic-invalid/agent-run-control-fanout-state-regression.json"),
        [agent_run, child_agent_run],
        {agent_run["runtime_run_id"]: 2, child_agent_run["runtime_run_id"]: 1},
        cancel_control_request,
        progressed_control_fanout,
    )
except AssertionError:
    pass
else:
    raise AssertionError("Expected fanout progress regression to fail")

try:
    validate_agent_run_control_fanout(
        control_fanout, [agent_run, child_agent_run],
        {agent_run["runtime_run_id"]: 3, child_agent_run["runtime_run_id"]: 1},
        cancel_control_request,
    )
except AssertionError:
    pass
else:
    raise AssertionError("Expected stale fanout fencing to fail")

try:
    validate_multiagent_terminal("succeeded", [(True, "running")], "completed")
except AssertionError:
    pass
else:
    raise AssertionError("Expected active Child to block WorkOrder completion")
validate_runtime_token(
    system_safety_token,
    manifest,
    agent_run,
    runtime_start,
    system_safety_command,
    system_safety_control,
)
validate_commercial_authorization_revocation(
    commercial_revocation,
    manifest,
    grant,
    authenticated_client_id=grant["client_app_id"],
    path_authorization_id=manifest["commercial_authorization"]["commercial_authorization_id"],
    received_at=commercial_revocation_accepted["accepted_at"],
    receipt=commercial_revocation_accepted,
    expected_execution_scopes=[
        {"kind": "work_order", "work_order_id": manifest["work_order_id"]},
        {
            "kind": "artifact_operation",
            "artifact_operation_id": artifact_operation["artifact_operation_id"],
        },
        {
            "kind": "artifact_ingest",
            "artifact_ingest_session_id": artifact_ingest_session["ingest_session_id"],
        },
    ],
)
commercial_revocation_fanout_negative = load(
    "tests/semantic-invalid/commercial-revocation-fanout-cases.json"
)
for case in commercial_revocation_fanout_negative["cases"]:
    candidate = copy.deepcopy(commercial_revocation_fanout_negative["receipt"])
    mutation = case["mutation"]
    if mutation == "digest_mismatch":
        candidate["revocation_receipt_digest"] = "sha256:" + "f" * 64
    elif mutation == "missing_target":
        candidate["execution_cancellation_targets"].pop()
    elif mutation == "duplicate_outbox":
        candidate["execution_cancellation_targets"][1]["outbox_message_id"] = (
            candidate["execution_cancellation_targets"][0]["outbox_message_id"]
        )
    elif mutation == "premature_completed":
        candidate["fanout_status"] = "completed"
    elif mutation == "authorization_mismatch":
        candidate["commercial_authorization_digest"] = "sha256:" + "f" * 64
    if mutation != "digest_mismatch":
        candidate["revocation_receipt_digest"] = canonical_digest({
            key: value for key, value in candidate.items()
            if key != "revocation_receipt_digest"
        })
    try:
        validate_commercial_authorization_revocation(
            commercial_revocation_fanout_negative["notice"], manifest, grant,
            authenticated_client_id=grant["client_app_id"],
            path_authorization_id=manifest["commercial_authorization"]["commercial_authorization_id"],
            received_at=candidate["accepted_at"], receipt=candidate,
            expected_execution_scopes=commercial_revocation_fanout_negative[
                "expected_execution_scopes"
            ],
        )
    except AssertionError:
        pass
    else:
        raise AssertionError(
            f"Expected CommercialAuthorization fan-out fixture to fail: {case['id']}"
        )


def validate_workspace_revision(workspace_revision: dict[str, Any]) -> None:
    validate_self_digest(workspace_revision, "revision_digest")
    if workspace_revision["revision_number"] == 1 and workspace_revision["parent_revision_id"] is not None:
        raise AssertionError("Initial WorkspaceRevision cannot have a parent")
    if workspace_revision["revision_number"] > 1 and workspace_revision["parent_revision_id"] is None:
        raise AssertionError("Later WorkspaceRevision must reference its immediate predecessor")
    mark_checks("workspace_revision.chain")


def validate_conversation_branch(
    branch: dict[str, Any], message: dict[str, Any], work_order: dict[str, Any],
    workspace_revision: dict[str, Any],
) -> None:
    if (branch["head_message_id"] is None) != (branch["head_message_sequence"] == 0):
        raise AssertionError("ConversationBranch head ID and sequence do not represent the same head")
    if branch["head_message_id"] is not None:
        if message["message_id"] != branch["head_message_id"] or message["message_sequence"] != branch["head_message_sequence"]:
            raise AssertionError("ConversationBranch head does not bind the projected ConversationMessage")
        if message["conversation_id"] != branch["conversation_id"] or message["branch_id"] != branch["branch_id"]:
            raise AssertionError("ConversationBranch head belongs to another Conversation or branch")
    if branch["active_work_order_id"] is not None:
        work = work_order["work"]
        if work["conversation_id"] != branch["conversation_id"] or work["branch_id"] != branch["branch_id"]:
            raise AssertionError("ConversationBranch active WorkOrder belongs to another Conversation or branch")
    validate_workspace_revision(workspace_revision)
    if workspace_revision["workspace_revision_id"] != branch["workspace_head_revision_id"]:
        raise AssertionError("ConversationBranch references a different WorkspaceRevision")
    if workspace_revision["revision_digest"] != branch["workspace_head_revision_digest"]:
        raise AssertionError("ConversationBranch Workspace head digest is stale or forged")
    if workspace_revision["branch_id"] != branch["branch_id"]:
        raise AssertionError("ConversationBranch WorkspaceRevision belongs to another branch")
    mark_checks("conversation_branch.head_consistency", "conversation_branch.workspace_binding")


branch_fixture = load("tests/semantic-invalid/conversation-branch-cases.json")
branch = load(branch_fixture["branch"])
branch_message = load(branch_fixture["message"])
branch_work_order = load(branch_fixture["work_order"])
branch_workspace_revision = load("examples/contracts/workspace-revision.json")
validate_conversation_branch(branch, branch_message, branch_work_order, branch_workspace_revision)
for case in branch_fixture["cases"]:
    candidate_branch = copy.deepcopy(branch)
    candidate_message = copy.deepcopy(branch_message)
    candidate_work_order = copy.deepcopy(branch_work_order)
    candidate_workspace_revision = copy.deepcopy(branch_workspace_revision)
    if case["mutation"] == "zero_sequence_with_head":
        candidate_branch["head_message_sequence"] = 0
    elif case["mutation"] == "positive_sequence_without_head":
        candidate_branch["head_message_id"] = None
    elif case["mutation"] == "cross_conversation_message":
        candidate_message["conversation_id"] = "conv_other"
    elif case["mutation"] == "active_work_order_branch_mismatch":
        candidate_work_order["work"]["branch_id"] = "other-branch"
    elif case["mutation"] == "workspace_head_digest_mismatch":
        candidate_branch["workspace_head_revision_digest"] = "sha256:" + "f" * 64
    elif case["mutation"] == "workspace_revision_cross_branch":
        candidate_workspace_revision["branch_id"] = "other-branch"
        candidate_workspace_revision["revision_digest"] = canonical_digest({
            key: item for key, item in candidate_workspace_revision.items() if key != "revision_digest"
        })
        candidate_branch["workspace_head_revision_digest"] = candidate_workspace_revision["revision_digest"]
    elif case["mutation"] == "workspace_first_revision_has_parent":
        candidate_workspace_revision["parent_revision_id"] = "wsr_parent"
        candidate_workspace_revision["revision_digest"] = canonical_digest({
            key: item for key, item in candidate_workspace_revision.items() if key != "revision_digest"
        })
        candidate_branch["workspace_head_revision_digest"] = candidate_workspace_revision["revision_digest"]
    elif case["mutation"] == "workspace_later_revision_missing_parent":
        candidate_workspace_revision["revision_number"] = 2
        candidate_workspace_revision["parent_revision_id"] = None
        candidate_workspace_revision["revision_digest"] = canonical_digest({
            key: item for key, item in candidate_workspace_revision.items() if key != "revision_digest"
        })
        candidate_branch["workspace_head_revision_digest"] = candidate_workspace_revision["revision_digest"]
    else:
        raise AssertionError(f"Unknown ConversationBranch mutation: {case['mutation']}")
    try:
        validate_conversation_branch(
            candidate_branch,
            candidate_message,
            candidate_work_order,
            candidate_workspace_revision,
        )
    except AssertionError:
        pass
    else:
        raise AssertionError(f"Expected ConversationBranch semantic fixture to fail: {case['id']}")


validate_c01_runtime_read_semantics(
    CONTRACT_ROOT, KNOWN_CONTRACT_CHECKS, EXECUTED_CONTRACT_CHECKS,
)
validate_semantic_traceability(semantic_traceability)

phase0_closure_negative = load("tests/semantic-invalid/phase0-closure-cases.json")
for case in phase0_closure_negative["cases"]:
    mutation = case["mutation"]
    try:
        if mutation == "runtime_input_digest_mismatch":
            candidate_manifest = copy.deepcopy(manifest)
            candidate_start = copy.deepcopy(runtime_start)
            candidate_manifest["input"]["content_digest"] = "sha256:" + "f" * 64
            candidate_start["input"] = copy.deepcopy(candidate_manifest["input"])
            candidate_start["request_digest"] = canonical_digest({
                key: value for key, value in candidate_start.items() if key != "request_digest"
            })
            validate_execution_topology(candidate_manifest, workflow_run, agent_run, candidate_start)
        elif mutation == "runtime_context_mismatch":
            candidate_start = copy.deepcopy(runtime_start)
            candidate_start["context_package"]["context_package_id"] = "ctx_other"
            candidate_start["request_digest"] = canonical_digest({
                key: value for key, value in candidate_start.items() if key != "request_digest"
            })
            validate_execution_topology(manifest, workflow_run, agent_run, candidate_start)
        elif mutation == "artifact_grant_tenant_mismatch":
            candidate_start = copy.deepcopy(runtime_start)
            authorization = candidate_start["runtime_authorization"]
            authorization["artifact_grants"][0]["tenant_id"] = "ten_other"
            authorization["authorization_digest"] = canonical_digest({
                key: value for key, value in authorization.items() if key != "authorization_digest"
            })
            candidate_start["request_digest"] = canonical_digest({
                key: value for key, value in candidate_start.items() if key != "request_digest"
            })
            validate_execution_topology(manifest, workflow_run, agent_run, candidate_start)
        elif mutation == "capability_token_tenant_mismatch":
            candidate = copy.deepcopy(capability_token)
            candidate["tenant_id"] = "ten_other"
            validate_capability_invocation(
                capability_request, candidate, capability_resolution, manifest
            )
        elif mutation == "capability_token_request_digest_mismatch":
            candidate = copy.deepcopy(capability_token)
            candidate["invocation_request_digest"] = "sha256:" + "f" * 64
            validate_capability_invocation(
                capability_request, candidate, capability_resolution, manifest
            )
        elif mutation == "provider_resolution_work_order_mismatch":
            candidate_manifest = copy.deepcopy(manifest)
            candidate = candidate_manifest["capability_resolutions"][0]
            candidate["execution_scope"]["work_order_id"] = "wrk_other"
            candidate["decision_digest"] = canonical_digest({
                key: value for key, value in candidate.items() if key != "decision_digest"
            })
            validate_execution_topology(candidate_manifest, workflow_run, agent_run, runtime_start)
        elif mutation == "workspace_manifest_count_mismatch":
            candidate = copy.deepcopy(workspace_content_manifest)
            candidate["entry_count"] += 1
            candidate["manifest_digest"] = canonical_digest({
                key: value for key, value in candidate.items() if key != "manifest_digest"
            })
            validate_workspace_content_manifest(candidate)
        elif mutation == "workspace_manifest_bytes_mismatch":
            candidate = copy.deepcopy(workspace_content_manifest)
            candidate["total_file_bytes"] += 1
            candidate["manifest_digest"] = canonical_digest({
                key: value for key, value in candidate.items() if key != "manifest_digest"
            })
            validate_workspace_content_manifest(candidate)
        elif mutation == "workspace_manifest_symlink_escape":
            candidate = copy.deepcopy(workspace_content_manifest)
            candidate["symlink_policy"] = "allow_relative_within_root"
            candidate["entries"].append({
                "path": "escape-link", "entry_type": "symlink", "mode": "0777", "symlink_target": "../outside",
            })
            candidate["entry_count"] += 1
            candidate["manifest_digest"] = canonical_digest({
                key: value for key, value in candidate.items() if key != "manifest_digest"
            })
            validate_workspace_content_manifest(candidate)
        elif mutation == "canonical_event_dedupe_mismatch":
            candidate = copy.deepcopy(canonical_event)
            candidate["dedupe_key"] = "sha256:" + "f" * 64
            validate_canonical_event_source(candidate)
        elif mutation == "canonical_event_provider_revision_missing":
            candidate = copy.deepcopy(canonical_event)
            candidate["producer_kind"] = "provider"
            candidate["metadata"]["provider_instance_id"] = "provider-instance"
            validate_canonical_event_source(candidate)
        elif mutation == "canonical_event_registry_mismatch":
            candidate = copy.deepcopy(canonical_runtime_event)
            candidate["event_registry"] = canonical_event["event_registry"]
            validate_canonical_event_registry_binding(candidate, [platform_event_registry, event_registry])
        elif mutation == "canonical_event_payload_mismatch":
            candidate = copy.deepcopy(canonical_runtime_event)
            candidate["data"].pop("content_digest")
            validate_canonical_event_registry_binding(candidate, [platform_event_registry, event_registry])
        elif mutation == "canonical_event_registry_owner_mismatch":
            candidate = copy.deepcopy(canonical_runtime_event)
            candidate["producer_kind"] = "platform"
            candidate["provider_revision_id"] = None
            candidate["metadata"].pop("provider_instance_id")
            validate_canonical_event_source(candidate)
            validate_canonical_event_registry_binding(candidate, [platform_event_registry, event_registry])
        elif mutation == "control_grant_work_order_mismatch":
            candidate = copy.deepcopy(control_grant)
            candidate["work_order_id"] = "wrk_other"
            validate_execution_grant_request(
                candidate, control_request, authenticated_conversation_id=control_request["conversation_id"]
            )
        elif mutation == "traceability_missing_constraint":
            candidate = copy.deepcopy(semantic_traceability)
            candidate["constraints"].pop()
            validate_semantic_traceability(candidate)
        elif mutation == "traceability_unknown_check_id":
            candidate = copy.deepcopy(semantic_traceability)
            enforcement = next(
                enforcement
                for entry in candidate["constraints"]
                for enforcement in entry["enforcements"]
                if enforcement["status"] == "contract_gate"
            )
            enforcement["check_id"] = "semantic.unknown"
            validate_semantic_traceability(candidate)
        elif mutation == "traceability_unexecuted_check_id":
            candidate = copy.deepcopy(semantic_traceability)
            enforcement = next(
                enforcement
                for entry in candidate["constraints"]
                for enforcement in entry["enforcements"]
                if enforcement["status"] == "contract_gate"
            )
            enforcement["check_id"] = "semantic_traceability.known_but_unexecuted"
            validate_semantic_traceability(candidate)
        elif mutation == "traceability_missing_markdown_responsibility":
            candidate = copy.deepcopy(semantic_traceability)
            enforcement = next(
                enforcement
                for entry in candidate["constraints"]
                for enforcement in entry["enforcements"]
                if enforcement["status"] == "phase0_implementation_required"
                and enforcement["artifact"].startswith(BLUEPRINT_ARTIFACT_URN_PREFIX)
            )
            enforcement["check_id"] = "undocumented_phase0_responsibility"
            validate_semantic_traceability(candidate)
        elif mutation == "traceability_missing_suite_test_id":
            candidate = copy.deepcopy(semantic_traceability)
            enforcement = next(
                enforcement
                for entry in candidate["constraints"]
                for enforcement in entry["enforcements"]
                if enforcement["status"] == "phase0_implementation_required"
                and enforcement["artifact"].endswith(".json")
            )
            enforcement["check_id"] = "missing-suite-test-id"
            validate_semantic_traceability(candidate)
        elif mutation == "control_grant_stale_turn_binding":
            candidate = copy.deepcopy(control_grant)
            candidate["turn_id"] = "turn_stale"
            validate_execution_grant_request(
                candidate, control_request, authenticated_conversation_id=control_request["conversation_id"]
            )
        elif mutation == "principal_context_digest_mismatch":
            candidate = copy.deepcopy(grant)
            candidate["principal_context_digest"] = "sha256:" + "f" * 64
            validate_execution_grant_request(
                candidate, conversation_turn_request, authenticated_conversation_id=conversation["conversation_id"]
            )
        elif mutation == "execution_grant_snapshot_expired":
            candidate = copy.deepcopy(grant)
            candidate["principal_context"]["expires_at"] = "2026-07-16T08:59:59Z"
            candidate["principal_context"]["principal_context_digest"] = canonical_digest({
                key: value for key, value in candidate["principal_context"].items()
                if key != "principal_context_digest"
            })
            candidate["principal_context_digest"] = candidate["principal_context"]["principal_context_digest"]
            validate_execution_grant_request(
                candidate, conversation_turn_request, authenticated_conversation_id=conversation["conversation_id"]
            )
        elif mutation == "runtime_authorization_widens_permissions":
            candidate_start = copy.deepcopy(runtime_start)
            authorization = candidate_start["runtime_authorization"]
            authorization["authorization_sequence"] = 2
            authorization["predecessor_authorization_digest"] = runtime_start["runtime_authorization"]["authorization_digest"]
            authorization["renewal_reason"] = "adapter_restart"
            authorization["effective_permissions"]["model"]["allowed_model_profiles"].append("forbidden-model")
            authorization["effective_permissions"]["permissions_digest"] = canonical_digest({
                key: value for key, value in authorization["effective_permissions"].items()
                if key != "permissions_digest"
            })
            authorization["policy_decision"]["effective_permissions_digest"] = authorization[
                "effective_permissions"
            ]["permissions_digest"]
            authorization["policy_decision"]["decision_digest"] = canonical_digest({
                key: value for key, value in authorization["policy_decision"].items()
                if key != "decision_digest"
            })
            authorization["authorization_digest"] = canonical_digest({
                key: value for key, value in authorization.items() if key != "authorization_digest"
            })
            validate_runtime_authorization(
                authorization, manifest, candidate_start, runtime_start["runtime_authorization"]
            )
        elif mutation == "runtime_authorization_component_scope_mismatch":
            candidate_start = copy.deepcopy(runtime_start)
            authorization = candidate_start["runtime_authorization"]
            authorization["execution_budget"]["tenant_id"] = "ten_other"
            authorization["execution_budget"]["budget_digest"] = canonical_digest({
                key: value for key, value in authorization["execution_budget"].items()
                if key != "budget_digest"
            })
            authorization["policy_decision"]["execution_budget_digest"] = authorization[
                "execution_budget"
            ]["budget_digest"]
            authorization["policy_decision"]["decision_digest"] = canonical_digest({
                key: value for key, value in authorization["policy_decision"].items()
                if key != "decision_digest"
            })
            authorization["authorization_digest"] = canonical_digest({
                key: value for key, value in authorization.items() if key != "authorization_digest"
            })
            validate_runtime_authorization(authorization, manifest, candidate_start)
        elif mutation == "runtime_authorization_commercial_expiry_exceeded":
            candidate_manifest = copy.deepcopy(manifest)
            candidate_start = copy.deepcopy(runtime_start)
            candidate_manifest["commercial_authorization"]["expires_at"] = "2026-07-16T09:10:00Z"
            candidate_manifest["run_manifest_digest"] = canonical_digest({
                key: value for key, value in candidate_manifest.items() if key != "run_manifest_digest"
            })
            authorization = candidate_start["runtime_authorization"]
            authorization["commercial_authorization"] = copy.deepcopy(
                candidate_manifest["commercial_authorization"]
            )
            authorization["run_manifest_digest"] = candidate_manifest["run_manifest_digest"]
            authorization["authorization_digest"] = canonical_digest({
                key: value for key, value in authorization.items() if key != "authorization_digest"
            })
            validate_runtime_authorization(authorization, candidate_manifest, candidate_start)
        elif mutation == "runtime_artifact_grant_predates_authorization":
            candidate_start = copy.deepcopy(runtime_start)
            authorization = candidate_start["runtime_authorization"]
            authorization["artifact_grants"][0]["issued_at"] = "2026-07-16T09:00:59Z"
            authorization["authorization_digest"] = canonical_digest({
                key: value for key, value in authorization.items() if key != "authorization_digest"
            })
            validate_runtime_authorization(authorization, manifest, candidate_start)
        elif mutation == "capability_artifact_grant_outlives_deadline":
            candidate_request = copy.deepcopy(capability_request)
            candidate_token = copy.deepcopy(capability_token)
            candidate_request["input_artifact_grants"][0]["expires_at"] = "2026-07-16T09:20:01Z"
            candidate_request["input_artifact_grants"][0]["grant_digest"] = canonical_digest({
                key: value for key, value in candidate_request["input_artifact_grants"][0].items()
                if key != "grant_digest"
            })
            candidate_request["request_digest"] = canonical_digest({
                key: value for key, value in candidate_request.items() if key != "request_digest"
            })
            candidate_token["invocation_request_digest"] = candidate_request["request_digest"]
            candidate_token["operation_request_digest"] = candidate_request["request_digest"]
            candidate_token["exp"] = 1784193060
            validate_capability_invocation(
                candidate_request, candidate_token, capability_resolution, manifest
            )
        elif mutation == "required_gateway_disabled":
            candidate_start = copy.deepcopy(runtime_start)
            candidate_start["gateway_bindings"]["model"] = {
                "kind": "model", "mode": "disabled", "reason": "policy_denied",
            }
            validate_gateway_bindings(
                candidate_start["gateway_bindings"],
                candidate_start["runtime_authorization"]["execution_budget"],
                candidate_start["runtime_authorization"]["effective_permissions"],
            )
        elif mutation == "provider_usage_contains_platform_entry":
            candidate = copy.deepcopy(capability_result)
            candidate["usage"][0]["entry_id"] = "platform-owned"
            validate_usage_observations(candidate, meter, usage_entry)
        elif mutation == "capability_request_resolution_mismatch":
            candidate_request = copy.deepcopy(capability_request)
            candidate_request["provider_resolution_id"] = "res_other"
            candidate_request["request_digest"] = canonical_digest({
                key: value for key, value in candidate_request.items() if key != "request_digest"
            })
            validate_capability_invocation(
                candidate_request, capability_token, capability_resolution, manifest
            )
        elif mutation == "capability_token_audience_mismatch":
            candidate = copy.deepcopy(capability_token)
            candidate["aud"] = "urn:agent-platform:provider-instance:other"
            validate_capability_invocation(
                capability_request, candidate, capability_resolution, manifest
            )
        elif mutation == "capability_token_operation_replay":
            candidate = copy.deepcopy(capability_token)
            candidate["operation"] = "cancel"
            validate_capability_invocation(
                capability_request, candidate, capability_resolution, manifest
            )
        elif mutation == "capability_token_lineage_gap":
            candidate = copy.deepcopy(capability_status_token)
            candidate["authorization_sequence"] += 1
            validate_capability_invocation(
                capability_request, candidate, capability_resolution, manifest,
                capability_status_operation, capability_token,
            )
        elif mutation == "run_manifest_request_binding_mismatch":
            candidate = copy.deepcopy(manifest)
            candidate["request_binding"]["request_digest"] = "sha256:" + "f" * 64
            validate_run_manifest_request_binding(candidate, grant, conversation_turn_request)
        elif mutation == "run_manifest_location_digest_mismatch":
            candidate = copy.deepcopy(manifest)
            candidate["location"]["region_id"] = "eu-west-1"
            candidate["run_manifest_digest"] = canonical_digest({
                key: value for key, value in candidate.items() if key != "run_manifest_digest"
            })
            validate_run_admission(candidate, context)
        elif mutation == "staging_grant_gateway_mismatch":
            candidate_request = copy.deepcopy(capability_request)
            candidate_token = copy.deepcopy(capability_token)
            staging = candidate_request["output_staging_grant"]
            staging["gateway_binding"]["route_id"] = "artifact-route-other"
            staging["grant_digest"] = canonical_digest({
                key: value for key, value in staging.items() if key != "grant_digest"
            })
            candidate_request["request_digest"] = canonical_digest({
                key: value for key, value in candidate_request.items() if key != "request_digest"
            })
            candidate_token["staging_grant_digest"] = staging["grant_digest"]
            candidate_token["invocation_request_digest"] = candidate_request["request_digest"]
            candidate_token["operation_request_digest"] = candidate_request["request_digest"]
            validate_capability_invocation(
                candidate_request, candidate_token, capability_resolution, manifest
            )
        elif mutation == "gateway_contract_digest_mismatch":
            candidate = copy.deepcopy(manifest["gateway_bindings"])
            candidate["artifact"]["port"]["contract_digest"] = "sha256:" + "f" * 64
            validate_gateway_bindings(candidate, execution_budget, manifest["effective_permissions"])
        elif mutation == "artifact_gateway_request_digest_mismatch":
            candidate = copy.deepcopy(artifact_stage_token)
            candidate["request_digest"] = "sha256:" + "f" * 64
            validate_artifact_gateway(
                artifact_staging_grant, artifact_staging_object, candidate,
                artifact_staging_commit, artifact_commit_token,
                capability_request["input_artifact_grants"][0], artifact_read_descriptor,
                artifact_read_token, capability_request,
                caller_subject=capability_resolution["selected_provider_audience"],
            )
        elif mutation == "artifact_gateway_read_fencing_mismatch":
            candidate = copy.deepcopy(artifact_read_token)
            candidate["fencing_token"] += 1
            descriptor = copy.deepcopy(artifact_read_descriptor)
            descriptor["fencing_token"] = candidate["fencing_token"]
            candidate["request_digest"] = canonical_digest(descriptor)
            validate_artifact_gateway(
                artifact_staging_grant, artifact_staging_object, artifact_stage_token,
                artifact_staging_commit, artifact_commit_token,
                capability_request["input_artifact_grants"][0], descriptor, candidate,
                capability_request,
                caller_subject=capability_resolution["selected_provider_audience"],
            )
        elif mutation == "egress_token_destination_mismatch":
            candidate = copy.deepcopy(egress_token)
            candidate["destination_id"] = "other-destination"
            validate_egress_gateway(
                egress_destination, egress_request, candidate, egress_response,
                manifest["gateway_bindings"]["egress"]["port"], runtime_start["runtime_authorization"],
                caller_subject=runtime_caller_subject,
            )
        elif mutation == "egress_token_operation_contract_replay":
            candidate = copy.deepcopy(egress_token)
            candidate["operation_contract_id"] = "urn:agent-platform:plugin-invocation-request:v1"
            validate_egress_gateway(
                egress_destination, egress_request, candidate, egress_response,
                manifest["gateway_bindings"]["egress"]["port"], runtime_start["runtime_authorization"],
                caller_subject=runtime_caller_subject,
            )
        elif mutation == "egress_token_operation_profile_replay":
            candidate = copy.deepcopy(egress_token)
            candidate["operation_digest_profile"] = "rfc8785-full-document-v1"
            validate_egress_gateway(
                egress_destination, egress_request, candidate, egress_response,
                manifest["gateway_bindings"]["egress"]["port"], runtime_start["runtime_authorization"],
                caller_subject=runtime_caller_subject,
            )
        elif mutation == "runtime_token_audience_mismatch":
            candidate = copy.deepcopy(runtime_token)
            candidate["aud"] = "urn:agent-platform:provider-instance:other"
            validate_runtime_token(candidate, manifest, agent_run, runtime_start)
        elif mutation == "runtime_token_authorization_expiry_exceeded":
            candidate = copy.deepcopy(runtime_token)
            candidate["exp"] = int(parse_datetime(
                runtime_start["runtime_authorization"]["expires_at"]
            ).timestamp()) + 1
            candidate["iat"] = candidate["exp"] - 300
            candidate["nbf"] = candidate["iat"]
            validate_runtime_token(candidate, manifest, agent_run, runtime_start)
        elif mutation == "runtime_token_operation_contract_replay":
            candidate = copy.deepcopy(runtime_event_token)
            candidate["operation_contract_id"] = (
                "urn:agent-platform:agent-runtime-status-operation-descriptor:v1"
            )
            validate_runtime_token(
                candidate, manifest, agent_run, runtime_start, runtime_event_descriptor,
            )
        elif mutation == "runtime_event_cursor_digest_mismatch":
            candidate = copy.deepcopy(runtime_event_descriptor)
            candidate["after_event_sequence"] += 1
            validate_runtime_token(
                runtime_event_token, manifest, agent_run, runtime_start, candidate,
            )
        elif mutation == "runtime_command_token_digest_mismatch":
            candidate = copy.deepcopy(runtime_command)
            candidate["command_sequence"] += 1
            validate_runtime_token(
                runtime_command_token, manifest, agent_run, runtime_start, candidate,
            )
        elif mutation == "runtime_command_self_digest_mismatch":
            candidate = copy.deepcopy(runtime_command)
            candidate["command_sequence"] += 1
            validate_agent_runtime_command(
                candidate,
                manifest,
                runtime_start,
                control_request=control_request,
                persisted_input=control_runtime_input,
            )
        elif mutation == "runtime_user_command_control_action_mismatch":
            candidate_request = copy.deepcopy(control_request)
            candidate_request["action"] = "interrupt"
            validate_agent_runtime_command(
                runtime_command,
                manifest,
                runtime_start,
                control_request=candidate_request,
                persisted_input=control_runtime_input,
            )
        elif mutation == "system_safety_control_scope_mismatch":
            candidate = copy.deepcopy(system_safety_control)
            candidate["tenant_id"] = "ten_other"
            candidate["control_digest"] = canonical_digest({
                key: value for key, value in candidate.items() if key != "control_digest"
            })
            validate_system_safety_control(candidate, manifest, runtime_start)
        elif mutation == "system_safety_control_issuer_mismatch":
            validate_system_safety_control(
                system_safety_control,
                manifest,
                runtime_start,
                authenticated_issuer="spn_other_workload",
            )
        elif mutation == "system_safety_control_future_evidence":
            candidate = copy.deepcopy(system_safety_control)
            candidate["trigger_evidence"]["observed_at"] = "2026-07-16T09:16:01Z"
            candidate["control_digest"] = canonical_digest({
                key: value for key, value in candidate.items() if key != "control_digest"
            })
            validate_system_safety_control(candidate, manifest, runtime_start)
        elif mutation == "system_safety_control_resume":
            candidate = copy.deepcopy(system_safety_control)
            candidate["action"] = "resume"
            candidate["control_digest"] = canonical_digest({
                key: value for key, value in candidate.items() if key != "control_digest"
            })
            validate_system_safety_control(candidate, manifest, runtime_start)
        elif mutation == "system_safety_control_hard_reason_paused":
            candidate = copy.deepcopy(system_safety_control)
            candidate["action"] = "pause"
            candidate["control_digest"] = canonical_digest({
                key: value for key, value in candidate.items() if key != "control_digest"
            })
            validate_system_safety_control(candidate, manifest, runtime_start)
        elif mutation == "runtime_system_safety_action_mismatch":
            candidate = copy.deepcopy(system_safety_command)
            candidate["type"] = "pause"
            candidate["command_digest"] = canonical_digest({
                key: value for key, value in candidate.items() if key != "command_digest"
            })
            validate_agent_runtime_command(
                candidate,
                manifest,
                runtime_start,
                system_safety_control=system_safety_control,
            )
        elif mutation == "runtime_system_safety_token_binding_mismatch":
            candidate = copy.deepcopy(system_safety_token)
            candidate["system_safety_control_digest"] = "sha256:" + "f" * 64
            validate_runtime_token(
                candidate,
                manifest,
                agent_run,
                runtime_start,
                system_safety_command,
                system_safety_control,
            )
        elif mutation == "runtime_system_safety_token_predates_control":
            candidate = copy.deepcopy(system_safety_token)
            candidate["iat"] = 1784193359
            candidate["nbf"] = 1784193359
            validate_runtime_token(
                candidate,
                manifest,
                agent_run,
                runtime_start,
                system_safety_command,
                system_safety_control,
            )
        elif mutation == "commercial_revocation_digest_mismatch":
            candidate = copy.deepcopy(commercial_revocation)
            candidate["revocation_digest"] = "sha256:" + "f" * 64
            validate_commercial_authorization_revocation(
                candidate,
                manifest,
                grant,
                authenticated_client_id=grant["client_app_id"],
                path_authorization_id=manifest["commercial_authorization"]["commercial_authorization_id"],
                received_at=commercial_revocation_accepted["accepted_at"],
            )
        elif mutation == "commercial_revocation_future_effective":
            candidate = copy.deepcopy(commercial_revocation)
            candidate["effective_at"] = "2026-07-16T09:10:02Z"
            candidate["revocation_digest"] = canonical_digest({
                key: value for key, value in candidate.items() if key != "revocation_digest"
            })
            validate_commercial_authorization_revocation(
                candidate,
                manifest,
                grant,
                authenticated_client_id=grant["client_app_id"],
                path_authorization_id=manifest["commercial_authorization"]["commercial_authorization_id"],
                received_at=commercial_revocation_accepted["accepted_at"],
            )
        elif mutation == "commercial_revocation_future_issued":
            candidate = copy.deepcopy(commercial_revocation)
            candidate["issued_at"] = "2026-07-16T09:20:00Z"
            candidate["revocation_digest"] = canonical_digest({
                key: value for key, value in candidate.items() if key != "revocation_digest"
            })
            validate_commercial_authorization_revocation(
                candidate,
                manifest,
                grant,
                authenticated_client_id=grant["client_app_id"],
                path_authorization_id=manifest["commercial_authorization"]["commercial_authorization_id"],
                received_at=commercial_revocation_accepted["accepted_at"],
            )
        elif mutation == "commercial_revocation_tenant_mismatch":
            candidate = copy.deepcopy(commercial_revocation)
            candidate["external_tenant_id"] = "org-other"
            candidate["revocation_digest"] = canonical_digest({
                key: value for key, value in candidate.items() if key != "revocation_digest"
            })
            validate_commercial_authorization_revocation(
                candidate,
                manifest,
                grant,
                authenticated_client_id=grant["client_app_id"],
                path_authorization_id=manifest["commercial_authorization"]["commercial_authorization_id"],
                received_at=commercial_revocation_accepted["accepted_at"],
            )
        elif mutation == "commercial_revocation_sender_mismatch":
            validate_commercial_authorization_revocation(
                commercial_revocation,
                manifest,
                grant,
                authenticated_client_id="other-client",
                path_authorization_id=manifest["commercial_authorization"]["commercial_authorization_id"],
                received_at=commercial_revocation_accepted["accepted_at"],
            )
        elif mutation == "commercial_revocation_authorization_mismatch":
            candidate = copy.deepcopy(commercial_revocation)
            candidate["commercial_authorization_id"] = "cauth_other"
            candidate["revocation_digest"] = canonical_digest({
                key: value for key, value in candidate.items() if key != "revocation_digest"
            })
            validate_commercial_authorization_revocation(
                candidate,
                manifest,
                grant,
                authenticated_client_id=grant["client_app_id"],
                path_authorization_id="cauth_other",
                received_at=commercial_revocation_accepted["accepted_at"],
            )
        elif mutation == "sandbox_token_request_digest_mismatch":
            candidate = copy.deepcopy(sandbox_token)
            candidate["request_digest"] = "sha256:" + "f" * 64
            validate_sandbox_token(candidate, sandbox_create, sandbox_resolution, manifest)
        elif mutation == "sandbox_token_audience_mismatch":
            candidate = copy.deepcopy(sandbox_token)
            candidate["aud"] = "urn:agent-platform:provider-instance:other"
            validate_sandbox_token(candidate, sandbox_create, sandbox_resolution, manifest)
        elif mutation == "sandbox_token_deadline_exceeded":
            candidate = copy.deepcopy(sandbox_token)
            candidate["exp"] = int(parse_datetime(sandbox_create["deadline_at"]).timestamp()) + 1
            candidate["iat"] = candidate["exp"] - 300
            candidate["nbf"] = candidate["iat"]
            validate_sandbox_token(candidate, sandbox_create, sandbox_resolution, manifest)
        elif mutation == "sandbox_token_predates_policy":
            candidate = copy.deepcopy(sandbox_token)
            candidate["iat"] = int(parse_datetime(manifest["policy_decision"]["decided_at"]).timestamp()) - 1
            candidate["nbf"] = candidate["iat"]
            validate_sandbox_token(candidate, sandbox_create, sandbox_resolution, manifest)
        elif mutation == "sandbox_token_operation_contract_replay":
            candidate = copy.deepcopy(sandbox_token)
            candidate["request_contract_id"] = "urn:agent-platform:sandbox-exec-request:v1"
            validate_sandbox_token(candidate, sandbox_create, sandbox_resolution, manifest)
        elif mutation == "sandbox_token_digest_profile_replay":
            candidate = copy.deepcopy(sandbox_token)
            candidate["request_digest_profile"] = "rfc8785-full-document-v1"
            validate_sandbox_token(candidate, sandbox_create, sandbox_resolution, manifest)
        elif mutation == "sandbox_status_path_mismatch":
            candidate = copy.deepcopy(sandbox_status_descriptor)
            candidate["sandbox_id"] = "sbx_other"
            validate_sandbox_token(
                sandbox_token_cases[9][0], candidate, sandbox_resolution, manifest,
                sandbox_id=sandbox_spec["sandbox_id"],
            )
        elif mutation == "sandbox_event_cursor_digest_mismatch":
            candidate = copy.deepcopy(sandbox_event_read_descriptor)
            candidate["after_sequence"] += 1
            validate_sandbox_token(
                sandbox_token_cases[13][0], candidate, sandbox_resolution, manifest,
                sandbox_id=sandbox_spec["sandbox_id"],
            )
        elif mutation == "sandbox_lease_budget_exceeded":
            candidate = copy.deepcopy(sandbox_spec)
            candidate["lease"]["expires_at"] = "2026-07-16T09:30:00Z"
            candidate["lease"]["max_extension_seconds"] = 1
            validate_sandbox_spec(candidate, manifest, sandbox_capabilities)
        elif mutation == "capability_event_cursor_digest_mismatch":
            candidate = copy.deepcopy(capability_event_operation)
            candidate["after_sequence"] += 1
            validate_capability_invocation(
                capability_request, capability_event_token, capability_resolution, manifest,
                candidate, capability_cancel_token,
            )
        elif mutation == "capability_token_operation_contract_replay":
            candidate = copy.deepcopy(capability_event_token)
            candidate["operation_contract_id"] = (
                "urn:agent-platform:capability-status-operation-descriptor:v1"
            )
            validate_capability_invocation(
                capability_request, candidate, capability_resolution, manifest,
                capability_event_operation, capability_cancel_token,
            )
        elif mutation == "egress_destination_owner_mismatch":
            candidate = copy.deepcopy(egress_destination)
            candidate["owner"]["client_app_id"] = "other-client"
            candidate["destination_revision_digest"] = canonical_digest({
                key: value for key, value in candidate.items()
                if key != "destination_revision_digest"
            })
            validate_egress_gateway(
                candidate, egress_request, egress_token, egress_response,
                manifest["gateway_bindings"]["egress"]["port"],
                runtime_start["runtime_authorization"],
                caller_subject=runtime_caller_subject,
            )
        elif mutation == "egress_destination_digest_mismatch":
            candidate = copy.deepcopy(egress_destination)
            candidate["destination_revision_digest"] = "sha256:" + "f" * 64
            validate_egress_gateway(
                candidate, egress_request, egress_token, egress_response,
                manifest["gateway_bindings"]["egress"]["port"],
                runtime_start["runtime_authorization"],
                caller_subject=runtime_caller_subject,
            )
        elif mutation == "egress_destination_class_not_permitted":
            candidate_destination = copy.deepcopy(egress_destination)
            candidate_destination["destination_class"] = "unapproved_destination"
            candidate_destination["destination_revision_digest"] = canonical_digest({
                key: value for key, value in candidate_destination.items()
                if key != "destination_revision_digest"
            })
            candidate_request = copy.deepcopy(egress_request)
            candidate_request["destination_class"] = candidate_destination["destination_class"]
            candidate_request["destination_revision_digest"] = candidate_destination[
                "destination_revision_digest"
            ]
            candidate_request["request_digest"] = canonical_digest({
                key: value for key, value in candidate_request.items()
                if key != "request_digest"
            })
            candidate_token = copy.deepcopy(egress_token)
            candidate_token["destination_class"] = candidate_request["destination_class"]
            candidate_token["destination_revision_digest"] = candidate_request[
                "destination_revision_digest"
            ]
            candidate_token["request_digest"] = candidate_request["request_digest"]
            validate_egress_gateway(
                candidate_destination, candidate_request, candidate_token, egress_response,
                manifest["gateway_bindings"]["egress"]["port"],
                runtime_start["runtime_authorization"],
                caller_subject=runtime_caller_subject,
            )
        elif mutation == "runtime_session_route_digest_mismatch":
            candidate = copy.deepcopy(runtime_session_route)
            candidate["provider_route_digest"] = "sha256:" + "f" * 64
            validate_runtime_session_route(
                candidate, runtime_session_request, runtime_session_response,
                manifest, execution_grant,
            )
        elif mutation == "runtime_session_route_slot_mismatch":
            candidate = copy.deepcopy(runtime_session_route)
            candidate["sandbox_slot_key"] = "isolated/other"
            validate_runtime_session_route(
                candidate, runtime_session_request, runtime_session_response,
                manifest, execution_grant,
            )
        elif mutation == "service_token_extra_audience":
            candidate = copy.deepcopy(service_access_token)
            candidate["aud"] = [
                "https://agent-api.agent-platform.internal",
                "https://other-service.internal",
            ]
            validate_service_access_token(
                candidate,
                registered_issuer="https://business.example.test",
                authenticated_subject="business-html-product",
                authenticated_client_id="html-product",
                allowed_scopes={"conversation:create", "session:create"},
            )
        elif mutation == "work_session_commercial_expiry_exceeded":
            candidate = copy.deepcopy(work_session_claims)
            candidate_request = copy.deepcopy(work_session_request)
            candidate_request["commercial_authorization"]["expires_at"] = "2026-07-16T09:10:00Z"
            candidate_request["commercial_authorization"]["commercial_authorization_digest"] = canonical_digest({
                key: value for key, value in candidate_request["commercial_authorization"].items()
                if key != "commercial_authorization_digest"
            })
            candidate["commercial_authorization_expires_at"] = "2026-07-16T09:10:00Z"
            candidate["commercial_authorization_digest"] = candidate_request[
                "commercial_authorization"
            ]["commercial_authorization_digest"]
            validate_work_session_claims(
                candidate, candidate_request, conversation,
                tenant_id=manifest["tenant_id"],
            )
        elif mutation == "plugin_token_request_digest_mismatch":
            candidate = copy.deepcopy(plugin_token)
            candidate["operation_request_digest"] = "sha256:" + "f" * 64
            validate_plugin_compatibility_token(
                plugin_request, candidate,
                plugin_id="html-to-pptx",
                provider_revision_id="legacypr_html_to_pptx_01",
                audience="urn:agent-platform:provider-instance:legacy-html-to-pptx",
                permissions_digest=manifest["effective_permissions"]["permissions_digest"],
            )
        elif mutation == "plugin_token_operation_contract_replay":
            candidate = copy.deepcopy(plugin_event_token)
            candidate["operation_contract_id"] = (
                "urn:agent-platform:plugin-status-operation-descriptor:v1"
            )
            validate_plugin_compatibility_token(
                plugin_request, candidate,
                plugin_id="html-to-pptx",
                provider_revision_id="legacypr_html_to_pptx_01",
                audience="urn:agent-platform:provider-instance:legacy-html-to-pptx",
                permissions_digest=manifest["effective_permissions"]["permissions_digest"],
                operation_document=plugin_event_descriptor,
            )
        elif mutation == "plugin_event_cursor_digest_mismatch":
            candidate = copy.deepcopy(plugin_event_descriptor)
            candidate["after_sequence"] += 1
            validate_plugin_compatibility_token(
                plugin_request, plugin_event_token,
                plugin_id="html-to-pptx",
                provider_revision_id="legacypr_html_to_pptx_01",
                audience="urn:agent-platform:provider-instance:legacy-html-to-pptx",
                permissions_digest=manifest["effective_permissions"]["permissions_digest"],
                operation_document=candidate,
            )
        elif mutation == "plugin_cancel_token_digest_mismatch":
            candidate = copy.deepcopy(plugin_cancel_request)
            candidate["reason"] = "different reason"
            validate_plugin_compatibility_token(
                plugin_request, plugin_cancel_token,
                plugin_id="html-to-pptx",
                provider_revision_id="legacypr_html_to_pptx_01",
                audience="urn:agent-platform:provider-instance:legacy-html-to-pptx",
                permissions_digest=manifest["effective_permissions"]["permissions_digest"],
                operation_document=candidate,
            )
        elif mutation == "runtime_token_caller_mismatch":
            candidate = copy.deepcopy(runtime_token)
            candidate["sub"] = "spn_other_workload"
            validate_runtime_token(candidate, manifest, agent_run, runtime_start)
        elif mutation == "runtime_safety_token_authorizes_append":
            candidate = copy.deepcopy(runtime_command_token)
            candidate["authority_mode"] = "safety_control"
            validate_runtime_token(candidate, manifest, agent_run, runtime_start, runtime_command)
        elif mutation == "runtime_command_token_deadline_exceeded":
            candidate = copy.deepcopy(runtime_command_token)
            candidate["exp"] = int(parse_datetime(runtime_command["deadline_at"]).timestamp()) + 1
            validate_runtime_token(candidate, manifest, agent_run, runtime_start, runtime_command)
        elif mutation == "runtime_token_predates_authorization":
            candidate = copy.deepcopy(runtime_token)
            candidate["iat"] = int(parse_datetime(runtime_start["runtime_authorization"]["issued_at"]).timestamp()) - 1
            candidate["nbf"] = candidate["iat"]
            validate_runtime_token(candidate, manifest, agent_run, runtime_start)
        elif mutation == "capability_token_predates_authority":
            candidate = copy.deepcopy(capability_token)
            candidate["iat"] = int(parse_datetime(capability_request["policy_decision"]["decided_at"]).timestamp()) - 1
            candidate["nbf"] = candidate["iat"]
            validate_capability_invocation(
                capability_request, candidate, capability_resolution, manifest,
            )
        elif mutation == "artifact_token_predates_grant":
            candidate = copy.deepcopy(artifact_stage_token)
            candidate["iat"] = int(parse_datetime(artifact_staging_grant["issued_at"]).timestamp()) - 1
            candidate["nbf"] = candidate["iat"]
            validate_artifact_gateway(
                artifact_staging_grant, artifact_staging_object, candidate,
                artifact_staging_commit, artifact_commit_token,
                capability_request["input_artifact_grants"][0], artifact_read_descriptor,
                artifact_read_token, capability_request,
                caller_subject=capability_resolution["selected_provider_audience"],
            )
        elif mutation == "egress_token_predates_authorization":
            candidate = copy.deepcopy(egress_token)
            candidate["iat"] = int(parse_datetime(runtime_start["runtime_authorization"]["issued_at"]).timestamp()) - 1
            candidate["nbf"] = candidate["iat"]
            validate_egress_gateway(
                egress_destination, egress_request, candidate, egress_response,
                manifest["gateway_bindings"]["egress"]["port"],
                runtime_start["runtime_authorization"], caller_subject=runtime_caller_subject,
            )
        elif mutation == "sandbox_token_caller_mismatch":
            candidate = copy.deepcopy(sandbox_token)
            candidate["sub"] = "spn_other_workload"
            validate_sandbox_token(candidate, sandbox_create, sandbox_resolution, manifest)
        elif mutation == "capability_token_caller_mismatch":
            candidate = copy.deepcopy(capability_token)
            candidate["sub"] = "spn_other_workload"
            validate_capability_invocation(
                capability_request, candidate, capability_resolution, manifest
            )
        elif mutation == "artifact_token_caller_mismatch":
            candidate = copy.deepcopy(artifact_stage_token)
            candidate["sub"] = "spn_other_workload"
            validate_artifact_gateway(
                artifact_staging_grant, artifact_staging_object, candidate,
                artifact_staging_commit, artifact_commit_token,
                capability_request["input_artifact_grants"][0], artifact_read_descriptor,
                artifact_read_token, capability_request,
                caller_subject=capability_resolution["selected_provider_audience"],
            )
        elif mutation == "egress_token_caller_mismatch":
            candidate = copy.deepcopy(egress_token)
            candidate["sub"] = "spn_other_workload"
            validate_egress_gateway(
                egress_destination, egress_request, candidate, egress_response,
                manifest["gateway_bindings"]["egress"]["port"],
                runtime_start["runtime_authorization"],
                caller_subject=runtime_caller_subject,
            )
        elif mutation == "egress_token_authorization_expiry_exceeded":
            candidate = copy.deepcopy(egress_token)
            candidate["exp"] = int(parse_datetime(
                runtime_start["runtime_authorization"]["expires_at"]
            ).timestamp()) + 1
            candidate["iat"] = candidate["exp"] - 300
            candidate["nbf"] = candidate["iat"]
            validate_egress_gateway(
                egress_destination, egress_request, candidate, egress_response,
                manifest["gateway_bindings"]["egress"]["port"], runtime_start["runtime_authorization"],
                caller_subject=runtime_caller_subject,
            )
        else:
            raise AssertionError(f"Unknown Phase 0 closure mutation: {mutation}")
    except AssertionError:
        pass
    else:
        raise AssertionError(f"Expected Phase 0 closure fixture to fail: {case['id']}")


negative_fixture_count = 0
for path in (CONTRACT_ROOT / "tests/semantic-invalid").glob("*.json"):
    negative_fixture = json.loads(path.read_text(encoding="utf-8"))
    negative_fixture_count += len(negative_fixture["cases"]) if "cases" in negative_fixture else 1
enforcements = [
    enforcement
    for constraint in semantic_traceability["constraints"]
    for enforcement in constraint["enforcements"]
]
evidence_dir = SCRIPT_ROOT / "build/validation"
evidence_dir.mkdir(parents=True, exist_ok=True)
(evidence_dir / "semantics.json").write_text(json.dumps({
    "state_machines": len(list((CONTRACT_ROOT / "state-machines").glob("*.json"))),
    "state_machine_and_safety_checks": "deterministic_reachable_terminal_safe_and_schema_aligned",
    "invalid_semantic_fixtures": negative_fixture_count,
    "platform_core_event_types": len(platform_event_registry["definitions"]),
    "agent_runtime_core_event_types": len(event_registry["definitions"]),
    "critical_semantic_schemas": len(semantic_traceability["critical_schema_ids"]),
    "semantic_constraints": len(semantic_traceability["constraints"]),
    "semantic_contract_gate_mappings": sum(
        item["status"] == "contract_gate" for item in enforcements
    ),
    "semantic_executed_unique_check_ids": len(EXECUTED_CONTRACT_CHECKS),
    "semantic_phase0_implementation_mappings": sum(
        item["status"] == "phase0_implementation_required" for item in enforcements
    ),
}, indent=2) + "\n", encoding="utf-8")
print(f"Semantic validation passed with deterministic state-machine/safety checks and {negative_fixture_count} negative invariant fixtures.")
