#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import re
import copy
import hashlib
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any, Iterable

import yaml

SCRIPT_ROOT = Path(__file__).resolve().parents[2]
CONTRACT_ROOT = Path(
    os.environ.get("AGENT_CONTRACT_ROOT", SCRIPT_ROOT.parent / "contract")
).resolve()

_C01_HISTORICAL_OPENAPI = "agent-runtime-provider-v1.0.0.snapshot.yaml"
_C01_ACTIVE_OPENAPI = "agent-runtime-provider-v1.yaml"
_C01_HISTORICAL_OPENAPI_SHA256 = (
    "f75bd9484d9059435021f65147cab1a22b4cb0376ea47ce6e165fde0494f5811"
)
_C01_HISTORICAL_EXTERNAL_REFS = {
    "agent-runtime-capabilities.schema.json": (1, "02fd8a0c2176539a0807fe88aaf11b915eca7484d56ca0eb8973467614b85872"),
    "agent-runtime-command.schema.json": (1, "0800078291c1b2544e188c6279d6febde27da7564dbb192babdfdb7f3eb1f930"),
    "agent-runtime-event-page.schema.json": (1, "450346bec4ccd9dccffaf9cf3d452f6461ed6581e3c3f864076ce66dd419070c"),
    "agent-runtime-run-status.schema.json": (3, "d43ec7fcd43a7f6690b861aa0f88f2534444dc90a1f456b4e32d2a692ba6ba26"),
    "agent-runtime-start-request.schema.json": (1, "47d15ab457e9d070a0246b078fbd2bcbf11f9a3d61072db2a04fb4d874f54704"),
    "standard-error.schema.json": (11, "1d24ba4f5bd8887603cf23bfcf2eef9e2dfc11292c87353682ef106a9d4bdf49"),
}


def source_files(patterns: Iterable[str]) -> list[Path]:
    paths: set[Path] = set()
    for pattern in patterns:
        paths.update(CONTRACT_ROOT.rglob(pattern))
    return sorted(path for path in paths if path.is_file())


class _NoDuplicateSafeLoader(yaml.SafeLoader):
    pass


def _construct_unique_mapping(
    loader: _NoDuplicateSafeLoader, node: yaml.MappingNode, deep: bool = False,
) -> dict[Any, Any]:
    result: dict[Any, Any] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in result:
            raise yaml.constructor.ConstructorError(
                "while constructing a mapping", node.start_mark,
                f"found duplicate key {key!r}", key_node.start_mark,
            )
        result[key] = loader.construct_object(value_node, deep=deep)
    return result


_NoDuplicateSafeLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _construct_unique_mapping,
)


def load_yaml(path: Path) -> Any:
    documents = list(yaml.load_all(
        path.read_text(encoding="utf-8"), Loader=_NoDuplicateSafeLoader,
    ))
    return documents[0] if len(documents) == 1 else documents


def _c01_external_schema_refs(value: Any) -> list[str]:
    references: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            if key == "$ref" and isinstance(child, str) and child.startswith("../schemas/"):
                if "#" in child or "?" in child:
                    raise AssertionError("C01 Runtime OpenAPI external Schema reference is not a plain relative path")
                references.append(Path(child).name)
            else:
                references.extend(_c01_external_schema_refs(child))
    elif isinstance(value, list):
        for child in value:
            references.extend(_c01_external_schema_refs(child))
    return references


def _c01_validate_runtime_openapi_registry(root: Path) -> None:
    openapi_root = root / "openapi"
    historical_path = openapi_root / _C01_HISTORICAL_OPENAPI
    active_path = openapi_root / _C01_ACTIVE_OPENAPI
    if not historical_path.is_file() or not active_path.is_file():
        raise AssertionError("C01 Runtime active/historical OpenAPI registry is incomplete")

    historical_bytes = historical_path.read_bytes()
    if hashlib.sha256(historical_bytes).hexdigest() != _C01_HISTORICAL_OPENAPI_SHA256:
        raise AssertionError("C01 historical Runtime OpenAPI snapshot byte drift")
    historical = load_yaml(historical_path)
    active = load_yaml(active_path)
    if historical.get("info", {}).get("version") != "1.0.0":
        raise AssertionError("C01 historical Runtime OpenAPI version drift")
    if active.get("info", {}).get("version") != "1.0.1":
        raise AssertionError("C01 active Runtime OpenAPI version drift")

    historical_refs = _c01_external_schema_refs(historical)
    historical_counts = {name: historical_refs.count(name) for name in set(historical_refs)}
    expected_counts = {name: count for name, (count, _digest) in _C01_HISTORICAL_EXTERNAL_REFS.items()}
    if len(historical_refs) != 18 or historical_counts != expected_counts:
        raise AssertionError("C01 historical Runtime OpenAPI external refs must be exactly 18/6")
    for name, (_count, expected_digest) in _C01_HISTORICAL_EXTERNAL_REFS.items():
        target = root / "schemas" / name
        if not target.is_file() or hashlib.sha256(target.read_bytes()).hexdigest() != expected_digest:
            raise AssertionError(f"C01 historical external Schema target drift: {name}")

    active_refs = _c01_external_schema_refs(active)
    if len(active_refs) != 20 or len(set(active_refs)) != 8:
        raise AssertionError("C01 active Runtime OpenAPI external refs must be exactly 20/8")
    for name in active_refs:
        if not (root / "schemas" / name).is_file():
            raise AssertionError(f"C01 active Runtime OpenAPI external Schema target is unresolved: {name}")

    registry: dict[tuple[str, str, str], Path] = {}
    for path in sorted(openapi_root.glob("agent-runtime-provider*.yaml")):
        document = load_yaml(path)
        version = document.get("info", {}).get("version")
        if version not in {"1.0.0", "1.0.1"}:
            raise AssertionError(f"C01 Runtime OpenAPI registry contains an unsupported version: {path.name}")
        key = ("agent-runtime-provider", "v1", "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest())
        if key in registry:
            raise AssertionError("C01 Runtime Port registry contains a duplicate tuple/digest")
        registry[key] = path
    expected_paths = {historical_path.resolve(), active_path.resolve()}
    if {path.resolve() for path in registry.values()} != expected_paths:
        raise AssertionError("C01 Runtime Port registry active/snapshot path set drift")


def _c01_snapshot_protected_state() -> dict[str, str]:
    roots = [CONTRACT_ROOT, SCRIPT_ROOT / "evidence", SCRIPT_ROOT / "build"]
    snapshot: dict[str, str] = {}
    for root in roots:
        if not root.exists():
            continue
        for path in sorted(item for item in root.rglob("*") if item.is_file()):
            key = f"{root}:{path.relative_to(root).as_posix()}"
            snapshot[key] = __import__("hashlib").sha256(path.read_bytes()).hexdigest()
    return snapshot


def _c01_expected_runtime_read_authority() -> dict[str, dict[str, Any]]:
    shared_recognition = {
        "method": "GET",
        "match": "exact",
        "unknown-route": "c01-out-of-scope",
        "pre-operation-parser-failure": "c01-out-of-scope",
    }
    runtime_run_id = {
        "segment-count": 1,
        "min-length": 1,
        "max-length": 200,
        "case-fold": "forbidden",
        "unicode-normalization": "forbidden",
        "slash-collapse": "forbidden",
        "dot-segment-processing": "forbidden",
        "encoded-path-separator-equivalence": "forbidden",
    }
    body = {
        "mode": "forbidden",
        "nonzero-content-length": "reject-400",
        "ambiguous-content-length": "reject-400",
        "transfer-encoding": "reject-400",
        "expect": "reject-400",
    }
    admission = {
        "operation-recognition-required": True,
        "caller-token-descriptor-binding-required": True,
        "before-provider-state-read": True,
        "independent-of-run-existence": True,
        "listener-saturation-eligible": False,
    }
    retry_shared = {
        "authority-version": "runtime-read-retry-authority-v1",
        "durable-caller-minimum-wait": "at-least-retry-after",
        "attempt": "fresh-authorized-read-attempt",
        "token": "fresh",
        "fencing": "non-stale",
        "descriptor-digest": "recompute-for-new-attempt-token-fencing",
        "adapter-auto-retry": "forbidden",
        "mutation-replay": "forbidden",
    }
    return {
        "getAgentRuntimeRun": {
            "route": "/v1/runs/{runtime_run_id}",
            "http": {
                "authority-version": "runtime-read-http-authority-v1",
                "operation-recognition": {
                    **shared_recognition,
                    "path-shape": "/v1/runs/{runtime_run_id}",
                },
                "runtime-run-id": runtime_run_id,
                "query": {
                    "mode": "forbidden",
                    "empty-marker": "reject-400",
                    "unknown-parameter": "reject-400",
                    "repeated-parameter": "reject-400",
                },
                "body": body,
                "descriptor-digest-mismatch": "reject-403",
            },
            "precedence": ["400", "401", "403", "429", "404", "200"],
            "admission": admission,
            "retry": {
                **retry_shared,
                "logical-status-target": "unchanged",
                "event-cursor-limit": "not-applicable",
                "event-cursor-advance-on-429": "not-applicable",
            },
        },
        "readAgentRuntimeEvents": {
            "route": "/v1/runs/{runtime_run_id}/events",
            "http": {
                "authority-version": "runtime-read-http-authority-v1",
                "operation-recognition": {
                    **shared_recognition,
                    "path-shape": "/v1/runs/{runtime_run_id}/events",
                },
                "runtime-run-id": runtime_run_id,
                "query": {
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
                },
                "body": body,
                "descriptor-digest-mismatch": "reject-403",
            },
            "precedence": ["400", "401", "403", "429", "404", "410", "200"],
            "admission": admission,
            "retry": {
                **retry_shared,
                "logical-status-target": "not-applicable",
                "event-cursor-limit": "unchanged",
                "event-cursor-advance-on-429": "forbidden",
            },
        },
    }


def _c01_operation(document: dict[str, Any], operation_id: str) -> tuple[str, dict[str, Any]]:
    matches = [
        (route, operation)
        for route, path_item in document.get("paths", {}).items()
        for method, operation in path_item.items()
        if method == "get" and isinstance(operation, dict)
        and operation.get("operationId") == operation_id
    ]
    if len(matches) != 1:
        raise AssertionError(f"C01 requires exactly one GET operation {operation_id}")
    return matches[0]


def _c01_validate_error_schema(root: Path, filename: str, expected: dict[str, Any]) -> None:
    schema = json.loads((root / "schemas" / filename).read_text(encoding="utf-8"))
    if set(schema) != {
        "$schema", "$id", "title", "description", "allOf", "unevaluatedProperties",
    }:
        raise AssertionError(f"C01 error Schema has an open or unexpected top-level shape: {filename}")
    if schema["$id"] != expected["$id"] or schema.get("unevaluatedProperties") is not False:
        raise AssertionError(f"C01 error Schema identity/closure drift: {filename}")
    if not isinstance(schema.get("allOf"), list) or len(schema["allOf"]) != 2:
        raise AssertionError(f"C01 error Schema composition drift: {filename}")
    if schema["allOf"][0] != {"$ref": "urn:agent-platform:standard-error:v1"}:
        raise AssertionError(f"C01 error Schema no longer narrows StandardError: {filename}")
    if schema["allOf"][1] != {"type": "object", "properties": expected["properties"]}:
        raise AssertionError(f"C01 error Schema operation-specific constraints drift: {filename}")


def validate_c01_runtime_read_authority(root: Path) -> None:
    _c01_validate_runtime_openapi_registry(root)
    document = load_yaml(root / "openapi" / "agent-runtime-provider-v1.yaml")
    if document.get("info", {}).get("version") != "1.0.1":
        raise AssertionError("C01 Runtime OpenAPI version must be 1.0.1")
    expected = _c01_expected_runtime_read_authority()
    for operation_id, authority in expected.items():
        route, operation = _c01_operation(document, operation_id)
        if route != authority["route"]:
            raise AssertionError(f"C01 operation route drift: {operation_id}")
        if operation.get("x-runtime-read-http-authority") != authority["http"]:
            raise AssertionError(f"C01 closed HTTP authority drift: {operation_id}")
        if operation.get("x-runtime-read-response-precedence") != authority["precedence"]:
            raise AssertionError(f"C01 response precedence drift: {operation_id}")
        if operation.get("x-runtime-read-admission") != authority["admission"]:
            raise AssertionError(f"C01 read admission drift: {operation_id}")
        if operation.get("x-runtime-read-retry") != authority["retry"]:
            raise AssertionError(f"C01 retry authority drift: {operation_id}")
        expected_refs = {
            "400": "#/components/responses/RuntimeReadBadRequest",
            "429": "#/components/responses/RuntimeReadTooManyRequests",
        }
        for status, reference in expected_refs.items():
            if operation.get("responses", {}).get(status) != {"$ref": reference}:
                raise AssertionError(f"C01 {operation_id} response {status} reference drift")

    responses = document.get("components", {}).get("responses", {})
    bad_request = responses.get("RuntimeReadBadRequest", {})
    if bad_request.get("x-runtime-read-header-authority") != {
        "authority-version": "runtime-read-header-authority-v1",
        "retry-after": {"presence": "forbidden"},
    }:
        raise AssertionError("C01 400 Retry-After authority drift")
    if "headers" in bad_request:
        raise AssertionError("C01 400 response must not declare Retry-After")
    if bad_request.get("content", {}).get("application/json", {}).get("schema") != {
        "$ref": "../schemas/agent-runtime-read-bad-request-error.schema.json"
    }:
        raise AssertionError("C01 400 error body Schema reference drift")

    throttled = responses.get("RuntimeReadTooManyRequests", {})
    expected_header_authority = {
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
    }
    if throttled.get("x-runtime-read-header-authority") != expected_header_authority:
        raise AssertionError("C01 429 raw Retry-After authority drift")
    retry_after = throttled.get("headers", {}).get("Retry-After", {})
    if retry_after.get("required") is not True or retry_after.get("schema") != {
        "type": "integer", "minimum": 1,
    }:
        raise AssertionError("C01 429 parsed Retry-After Header Object drift")
    if throttled.get("content", {}).get("application/json", {}).get("schema") != {
        "$ref": "../schemas/agent-runtime-read-throttled-error.schema.json"
    }:
        raise AssertionError("C01 429 error body Schema reference drift")

    _c01_validate_error_schema(root, "agent-runtime-read-bad-request-error.schema.json", {
        "$id": "urn:agent-platform:agent-runtime-read-bad-request-error:v1",
        "properties": {
            "code": {"const": "RUNTIME_READ_REQUEST_INVALID"},
            "message": {"const": "Runtime read request is invalid."},
            "retryable": {"const": False},
            "trace_id": {"type": "string", "minLength": 1},
        },
    })
    _c01_validate_error_schema(root, "agent-runtime-read-throttled-error.schema.json", {
        "$id": "urn:agent-platform:agent-runtime-read-throttled-error:v1",
        "properties": {
            "code": {"const": "RUNTIME_READ_THROTTLED"},
            "message": {"type": "string", "minLength": 1, "maxLength": 2000},
            "retryable": {"const": True},
            "trace_id": {"type": "string", "minLength": 1},
        },
    })


def self_test_c01_runtime_read() -> None:
    protected_before = _c01_snapshot_protected_state()
    with tempfile.TemporaryDirectory(prefix="c01-offline-static-") as temporary:
        root = Path(temporary) / "contract"
        shutil.copytree(CONTRACT_ROOT / "openapi", root / "openapi")
        shutil.copytree(CONTRACT_ROOT / "schemas", root / "schemas")
        openapi_path = root / "openapi" / "agent-runtime-provider-v1.yaml"
        original_bytes = openapi_path.read_bytes()
        original = load_yaml(openapi_path)
        validate_c01_runtime_read_authority(root)

        def status(document: dict[str, Any]) -> dict[str, Any]:
            return document["paths"]["/v1/runs/{runtime_run_id}"]["get"]

        def events(document: dict[str, Any]) -> dict[str, Any]:
            return document["paths"]["/v1/runs/{runtime_run_id}/events"]["get"]

        mutations = [
            lambda value: status(value)["x-runtime-read-http-authority"].pop("body"),
            lambda value: status(value)["x-runtime-read-http-authority"].update({"unexpected": "open"}),
            lambda value: status(value)["x-runtime-read-http-authority"]["query"].update({"mode": "allowlist"}),
            lambda value: status(value)["x-runtime-read-response-precedence"].__setitem__(0, "401"),
            lambda value: value["components"]["responses"]["RuntimeReadTooManyRequests"]
                ["x-runtime-read-header-authority"]["retry-after"].update({"lexical-pattern": "^[0-9]+$"}),
            lambda value: events(value)["x-runtime-read-http-authority"]["operation-recognition"]
                .update({"unknown-route": "reject-400"}),
            lambda value: events(value)["x-runtime-read-http-authority"]["operation-recognition"]
                .update({"pre-operation-parser-failure": "reject-400"}),
        ]
        for index, mutate in enumerate(mutations):
            candidate = copy.deepcopy(original)
            mutate(candidate)
            openapi_path.write_text(yaml.safe_dump(candidate, sort_keys=False), encoding="utf-8")
            try:
                validate_c01_runtime_read_authority(root)
            except AssertionError:
                pass
            else:
                raise AssertionError(f"C01 offline mutation did not fail closed: {index}")
        openapi_path.write_text(yaml.safe_dump(original, sort_keys=False), encoding="utf-8")
        validate_c01_runtime_read_authority(root)
        openapi_path.write_bytes(original_bytes + b"\nopenapi: 3.1.1\n")
        try:
            validate_c01_runtime_read_authority(root)
        except yaml.YAMLError:
            pass
        else:
            raise AssertionError("C01 duplicate YAML mapping key did not fail closed")

        openapi_path.write_bytes(original_bytes)
        historical_path = root / "openapi" / _C01_HISTORICAL_OPENAPI
        historical_bytes = historical_path.read_bytes()
        target_path = root / "schemas" / "standard-error.schema.json"
        target_bytes = target_path.read_bytes()
        registry_mutations: list[tuple[str, Any]] = [
            ("snapshot-missing", lambda: historical_path.unlink()),
            ("snapshot-byte-drift", lambda: historical_path.write_bytes(historical_bytes + b"\n")),
            ("external-target-byte-drift", lambda: target_path.write_bytes(target_bytes + b"\n")),
            (
                "active-snapshot-swap",
                lambda: (
                    historical_path.write_bytes(original_bytes),
                    openapi_path.write_bytes(historical_bytes),
                ),
            ),
            (
                "duplicate-port-tuple",
                lambda: (root / "openapi" / "agent-runtime-provider-v1.0.0.duplicate.yaml")
                    .write_bytes(historical_bytes),
            ),
        ]
        for label, mutate in registry_mutations:
            openapi_path.write_bytes(original_bytes)
            historical_path.write_bytes(historical_bytes)
            target_path.write_bytes(target_bytes)
            duplicate = root / "openapi" / "agent-runtime-provider-v1.0.0.duplicate.yaml"
            if duplicate.exists():
                duplicate.unlink()
            mutate()
            try:
                validate_c01_runtime_read_authority(root)
            except (AssertionError, FileNotFoundError):
                pass
            else:
                raise AssertionError(f"C01 Runtime OpenAPI registry mutation did not fail closed: {label}")
        openapi_path.write_bytes(original_bytes)
        historical_path.write_bytes(historical_bytes)
        target_path.write_bytes(target_bytes)
        duplicate = root / "openapi" / "agent-runtime-provider-v1.0.0.duplicate.yaml"
        if duplicate.exists():
            duplicate.unlink()
        validate_c01_runtime_read_authority(root)
    if _c01_snapshot_protected_state() != protected_before:
        raise AssertionError("C01 offline self-test changed protected Contract/build/evidence state")


if "--self-test-c01-runtime-read" in sys.argv:
    if sys.argv[1:] != ["--self-test-c01-runtime-read"]:
        raise SystemExit("--self-test-c01-runtime-read cannot be combined with other arguments")
    self_test_c01_runtime_read()
    print("C01 Runtime read offline static audit self-test passed.")
    raise SystemExit(0)
if len(sys.argv) != 1:
    raise SystemExit(f"Unknown arguments: {sys.argv[1:]}")

validate_c01_runtime_read_authority(CONTRACT_ROOT)


json_files = source_files(["*.json"])
yaml_files = source_files(["*.yaml", "*.yml"])
for path in json_files:
    json.loads(path.read_text(encoding="utf-8"))
for path in yaml_files:
    load_yaml(path)

openapi_files = sorted((CONTRACT_ROOT / "openapi").glob("*.yaml"))
operation_profiles = {
    ("capability-provider-v1.yaml", "createCapabilityInvocation"): (
        "invoke", "urn:agent-platform:capability-invocation-request:v1",
        "rfc8785-request-excluding-request-digest-v1", None,
    ),
    ("capability-provider-v1.yaml", "getCapabilityInvocation"): (
        "status", "urn:agent-platform:capability-status-operation-descriptor:v1",
        "rfc8785-full-document-v1", "../schemas/capability-status-operation-descriptor.schema.json",
    ),
    ("capability-provider-v1.yaml", "cancelCapabilityInvocation"): (
        "cancel", "urn:agent-platform:capability-cancellation-request:v1",
        "rfc8785-request-excluding-request-digest-v1", None,
    ),
    ("capability-provider-v1.yaml", "readCapabilityInvocationEvents"): (
        "read_events", "urn:agent-platform:capability-event-read-operation-descriptor:v1",
        "rfc8785-full-document-v1", "../schemas/capability-event-read-operation-descriptor.schema.json",
    ),
    ("artifact-gateway-v1.yaml", "readArtifactVersionContent"): (
        "read_content", "urn:agent-platform:artifact-read-operation-descriptor:v1",
        "rfc8785-full-document-v1", "../schemas/artifact-read-operation-descriptor.schema.json",
    ),
    ("artifact-gateway-v1.yaml", "stageArtifactObject"): (
        "stage_object", "urn:agent-platform:artifact-staging-object-request:v1",
        "rfc8785-artifact-stage-metadata-excluding-content-and-request-digest-v1", None,
    ),
    ("artifact-gateway-v1.yaml", "commitArtifactStagingSession"): (
        "commit_staging", "urn:agent-platform:artifact-staging-commit-request:v1",
        "rfc8785-request-excluding-request-digest-v1", None,
    ),
    ("sandbox-provider-v1.yaml", "createSandbox"): (
        "create", "urn:agent-platform:sandbox-create-request:v1",
        "rfc8785-request-excluding-request-digest-v1", None,
    ),
    ("sandbox-provider-v1.yaml", "restoreSandbox"): (
        "restore", "urn:agent-platform:sandbox-restore-request:v1",
        "rfc8785-request-excluding-request-digest-v1", None,
    ),
    ("sandbox-provider-v1.yaml", "getSandbox"): (
        "read_sandbox", "urn:agent-platform:sandbox-status-operation-descriptor:v1",
        "rfc8785-full-document-v1", "../schemas/sandbox-status-operation-descriptor.schema.json",
    ),
    ("sandbox-provider-v1.yaml", "setSandboxDesiredState"): (
        "set_desired_state", "urn:agent-platform:sandbox-desired-state-request:v1",
        "rfc8785-request-excluding-request-digest-v1", None,
    ),
    ("sandbox-provider-v1.yaml", "extendSandboxLease"): (
        "extend_lease", "urn:agent-platform:sandbox-lease-request:v1",
        "rfc8785-request-excluding-request-digest-v1", None,
    ),
    ("sandbox-provider-v1.yaml", "executeInSandbox"): (
        "exec", "urn:agent-platform:sandbox-exec-request:v1",
        "rfc8785-request-excluding-request-digest-v1", None,
    ),
    ("sandbox-provider-v1.yaml", "cancelSandboxExec"): (
        "cancel_exec", "urn:agent-platform:sandbox-cancel-exec-request:v1",
        "rfc8785-request-excluding-request-digest-v1", None,
    ),
    ("sandbox-provider-v1.yaml", "openSandboxRuntimeSession"): (
        "open_runtime_session", "urn:agent-platform:sandbox-runtime-session-open-request:v1",
        "rfc8785-request-excluding-request-digest-v1", None,
    ),
    ("sandbox-provider-v1.yaml", "createSandboxSnapshot"): (
        "snapshot", "urn:agent-platform:sandbox-snapshot-request:v1",
        "rfc8785-request-excluding-request-digest-v1", None,
    ),
    ("sandbox-provider-v1.yaml", "terminateSandbox"): (
        "terminate", "urn:agent-platform:sandbox-terminate-request:v1",
        "rfc8785-request-excluding-request-digest-v1", None,
    ),
    ("sandbox-provider-v1.yaml", "getSandboxOperation"): (
        "read_operation", "urn:agent-platform:sandbox-operation-read-operation-descriptor:v1",
        "rfc8785-full-document-v1", "../schemas/sandbox-operation-read-operation-descriptor.schema.json",
    ),
    ("sandbox-provider-v1.yaml", "getSandboxExecResult"): (
        "read_result", "urn:agent-platform:sandbox-exec-result-operation-descriptor:v1",
        "rfc8785-full-document-v1", "../schemas/sandbox-exec-result-operation-descriptor.schema.json",
    ),
    ("sandbox-provider-v1.yaml", "getSandboxSnapshotManifest"): (
        "read_snapshot_manifest", "urn:agent-platform:sandbox-snapshot-manifest-operation-descriptor:v1",
        "rfc8785-full-document-v1", "../schemas/sandbox-snapshot-manifest-operation-descriptor.schema.json",
    ),
    ("sandbox-provider-v1.yaml", "streamSandboxEvents"): (
        "read_events", "urn:agent-platform:sandbox-event-read-operation-descriptor:v1",
        "rfc8785-full-document-v1", "../schemas/sandbox-event-read-operation-descriptor.schema.json",
    ),
    ("agent-runtime-provider-v1.yaml", "startAgentRuntimeRun"): (
        "start", "urn:agent-platform:agent-runtime-start-request:v1",
        "rfc8785-request-excluding-request-digest-v1", None,
    ),
    ("agent-runtime-provider-v1.yaml", "getAgentRuntimeRun"): (
        "read_status", "urn:agent-platform:agent-runtime-status-operation-descriptor:v1",
        "rfc8785-full-document-v1", "../schemas/agent-runtime-status-operation-descriptor.schema.json",
    ),
    ("agent-runtime-provider-v1.yaml", "submitAgentRuntimeCommand"): (
        "submit_command", "urn:agent-platform:agent-runtime-command:v1",
        "rfc8785-command-excluding-command-digest-v1", None,
    ),
    ("agent-runtime-provider-v1.yaml", "readAgentRuntimeEvents"): (
        "read_events", "urn:agent-platform:agent-runtime-event-read-operation-descriptor:v1",
        "rfc8785-full-document-v1", "../schemas/agent-runtime-event-read-operation-descriptor.schema.json",
    ),
    ("plugin-invocation-v1.yaml", "createPluginInvocation"): (
        "invoke", "urn:agent-platform:plugin-invocation-request:v1",
        "rfc8785-request-excluding-request-digest-v1", None,
    ),
    ("plugin-invocation-v1.yaml", "getPluginInvocation"): (
        "status", "urn:agent-platform:plugin-status-operation-descriptor:v1",
        "rfc8785-full-document-v1", "../schemas/plugin-status-operation-descriptor.schema.json",
    ),
    ("plugin-invocation-v1.yaml", "cancelPluginInvocation"): (
        "cancel", "urn:agent-platform:plugin-cancellation-request:v1",
        "rfc8785-request-excluding-request-digest-v1", None,
    ),
    ("plugin-invocation-v1.yaml", "streamPluginInvocationEvents"): (
        "read_events", "urn:agent-platform:plugin-event-read-operation-descriptor:v1",
        "rfc8785-full-document-v1", "../schemas/plugin-event-read-operation-descriptor.schema.json",
    ),
    ("egress-gateway-v1.yaml", "createGovernedHttpExchange"): (
        "http_exchange", "urn:agent-platform:egress-http-request:v1",
        "rfc8785-request-excluding-request-digest-v1", None,
    ),
    ("credential-gateway-v1.yaml", "accessCredentialForOperation"): (
        "credential_access", "urn:agent-platform:credential-access-request:v1",
        "rfc8785-request-excluding-request-digest-v1", None,
    ),
}
path_body_binding_profiles = {
    ("agent-access-v1.yaml", "revokeCommercialAuthorization"): [
        {"path_parameter": "commercial_authorization_id", "body_json_pointer": "/commercial_authorization_id"},
    ],
    ("agent-access-v1.yaml", "confirmArtifactIngestUpload"): [
        {"path_parameter": "ingest_session_id", "body_json_pointer": "/ingest_session_id"},
    ],
    ("agent-access-v1.yaml", "controlWorkOrder"): [
        {"path_parameter": "work_order_id", "body_json_pointer": "/work_order_id"},
    ],
    ("agent-access-v1.yaml", "createArtifactPreviewSession"): [
        {"path_parameter": "artifact_id", "body_json_pointer": "/operation_context/artifact_id"},
    ],
    ("agent-access-v1.yaml", "createArtifactEditSession"): [
        {"path_parameter": "artifact_id", "body_json_pointer": "/operation_context/artifact_id"},
    ],
    ("agent-access-v1.yaml", "createArtifactConversion"): [
        {"path_parameter": "artifact_id", "body_json_pointer": "/operation_context/artifact_id"},
    ],
    ("agent-access-v1.yaml", "createConversationBranch"): [
        {"path_parameter": "conversation_id", "body_json_pointer": "/conversation_id"},
    ],
}
token_extensions = {
    "capability-provider-v1.yaml": "x-required-capability-token-operation",
    "artifact-gateway-v1.yaml": "x-required-artifact-token-operation",
    "sandbox-provider-v1.yaml": "x-required-sandbox-token-operation",
    "agent-runtime-provider-v1.yaml": "x-required-runtime-token-operation",
    "plugin-invocation-v1.yaml": "x-required-plugin-token-operation",
    "egress-gateway-v1.yaml": "x-required-egress-token-operation",
    "credential-gateway-v1.yaml": "x-required-credential-token-operation",
}
seen_operation_profiles: set[tuple[str, str]] = set()
seen_path_body_binding_profiles: set[tuple[str, str]] = set()
for path in openapi_files:
    document = load_yaml(path)
    assert document["openapi"] == "3.1.1", path
    assert document.get("servers"), path
    assert document.get("security") is not None, path
    for route, path_item in document["paths"].items():
        for method, operation in path_item.items():
            if method not in {"get", "post", "put", "patch", "delete"}:
                continue
            assert operation.get("operationId"), f"{path}: {method} {route}"
            profile_key = (path.name, operation["operationId"])
            if profile_key in path_body_binding_profiles:
                bindings = operation.get("x-path-body-bindings")
                assert bindings == path_body_binding_profiles[profile_key], profile_key
                route_parameters = set(re.findall(r"\{([^{}]+)\}", route))
                assert operation.get("requestBody"), profile_key
                assert all(
                    binding["path_parameter"] in route_parameters
                    and binding["body_json_pointer"].startswith("/")
                    for binding in bindings
                ), profile_key
                seen_path_body_binding_profiles.add(profile_key)
            else:
                assert "x-path-body-bindings" not in operation, profile_key
            if profile_key in operation_profiles:
                token_operation, contract_id, digest_profile, descriptor_schema = operation_profiles[profile_key]
                token_extension = token_extensions[path.name]
                assert operation.get(token_extension) == token_operation, profile_key
                assert operation.get("x-operation-contract-id") == contract_id, profile_key
                assert operation.get("x-operation-digest-profile") == digest_profile, profile_key
                assert operation.get("x-operation-descriptor-schema") == descriptor_schema, profile_key
                schema_ref = descriptor_schema
                if schema_ref is None:
                    schema_ref = operation["requestBody"]["content"]["application/json"]["schema"]["$ref"]
                contract_path = (path.parent / schema_ref).resolve()
                contract = json.loads(contract_path.read_text(encoding="utf-8"))
                assert contract["$id"] == contract_id, profile_key
                seen_operation_profiles.add(profile_key)
            security = operation.get("security", document.get("security"))
            if path.name == "sandbox-provider-v1.yaml":
                requires_sandbox_token = any(
                    "SandboxInvocationBearer" in requirement for requirement in security
                )
                if requires_sandbox_token:
                    assert profile_key in operation_profiles, f"Ungoverned Sandbox token operation: {profile_key}"
                else:
                    assert operation["operationId"] == "getSandboxCapabilities", profile_key
            if path.name == "agent-runtime-provider-v1.yaml":
                requires_runtime_token = any(
                    "RuntimeInvocationBearer" in requirement for requirement in security
                )
                if requires_runtime_token:
                    assert profile_key in operation_profiles, f"Ungoverned Runtime token operation: {profile_key}"
                else:
                    assert operation["operationId"] == "getAgentRuntimeCapabilities", profile_key
            if path.name == "plugin-invocation-v1.yaml":
                requires_plugin_token = any(
                    "InvocationBearer" in requirement for requirement in security
                )
                if requires_plugin_token:
                    assert profile_key in operation_profiles, f"Ungoverned Plugin token operation: {profile_key}"
            if path.name == "credential-gateway-v1.yaml":
                requires_credential_token = any(
                    "CredentialOperationBearer" in requirement for requirement in security
                )
                if requires_credential_token:
                    assert profile_key in operation_profiles, f"Ungoverned Credential token operation: {profile_key}"
            responses = set(operation.get("responses", {}))
            assert any(code.startswith("2") for code in responses), f"{path}: {method} {route}: missing success"
            assert "500" in responses, f"{path}: {method} {route}: missing 500"
            if method in {"post", "put", "patch", "delete"} and operation.get("requestBody"):
                body_limit = operation.get("x-max-encoded-body-bytes")
                assert isinstance(body_limit, int) and 1 <= body_limit <= 16 * 1024 * 1024, (
                    f"{path}: {method} {route}: invalid or missing encoded-body limit"
                )
                assert "413" in responses, f"{path}: {method} {route}: missing pre-parse 413"
            if method in {"post", "put", "patch", "delete"} and security:
                missing = {"401", "500"} - responses
                assert not missing, f"{path}: {method} {route}: missing {missing}"
    for match in re.finditer(r"\$ref:\s+([^\s]+)", path.read_text(encoding="utf-8")):
        ref = match.group(1).strip("'\"")
        if ref.startswith("#") or "://" in ref or ref.startswith("urn:"):
            continue
        assert (path.parent / ref.split("#", 1)[0]).resolve().exists(), f"Missing ref: {path}: {ref}"
assert seen_operation_profiles == set(operation_profiles), "Missing governed operation digest profile"
assert seen_path_body_binding_profiles == set(path_body_binding_profiles), "Missing path/body binding profile"

jws_header_profiles = {
    "service-access-token-jws-header.schema.json": "at+jwt",
    "execution-grant-jws-header.schema.json": "agent-execution-grant+jwt",
    "work-session-jws-header.schema.json": "agent-work-session+jwt",
    "plugin-invocation-jws-header.schema.json": "agent-plugin-invocation+jwt",
    "capability-invocation-jws-header.schema.json": "agent-capability-invocation+jwt",
    "artifact-gateway-jws-header.schema.json": "agent-artifact-operation+jwt",
    "egress-invocation-jws-header.schema.json": "agent-egress-invocation+jwt",
    "agent-runtime-invocation-jws-header.schema.json": "agent-runtime-invocation+jwt",
    "sandbox-operation-jws-header.schema.json": "agent-sandbox-operation+jwt",
    "sandbox-operation-jws-header-v2.schema.json": "agent-sandbox-operation-admission+jwt",
    "credential-operation-jws-header.schema.json": "agent-credential-operation+jwt",
}
assert len(set(jws_header_profiles.values())) == len(jws_header_profiles)
for schema_name, token_type in jws_header_profiles.items():
    header = json.loads((CONTRACT_ROOT / "schemas" / schema_name).read_text(encoding="utf-8"))
    assert set(header["required"]) == {"alg", "kid", "typ"}, schema_name
    assert header.get("additionalProperties") is False, schema_name
    assert header["properties"]["typ"] == {"const": token_type}, schema_name
    assert header["properties"]["kid"].get("minLength", 0) > 0, schema_name
    assert header["properties"]["alg"].get("enum"), schema_name

jwt_security_profiles = {
    ("agent-access-v1.yaml", "ServiceOAuth"): (
        "service-access-token-jws-header.schema.json", "service-access-token-claims.schema.json",
    ),
    ("agent-access-v1.yaml", "WorkSessionCookie"): (
        "work-session-jws-header.schema.json", "work-session-claims.schema.json",
    ),
    ("agent-access-v1.yaml", "WorkSessionBearer"): (
        "work-session-jws-header.schema.json", "work-session-claims.schema.json",
    ),
    ("plugin-invocation-v1.yaml", "InvocationBearer"): (
        "plugin-invocation-jws-header.schema.json", "plugin-invocation-token-claims.schema.json",
    ),
    ("capability-provider-v1.yaml", "CapabilityInvocationBearer"): (
        "capability-invocation-jws-header.schema.json", "capability-invocation-token-claims.schema.json",
    ),
    ("artifact-gateway-v1.yaml", "ArtifactOperationBearer"): (
        "artifact-gateway-jws-header.schema.json", "artifact-gateway-token-claims.schema.json",
    ),
    ("egress-gateway-v1.yaml", "EgressInvocationBearer"): (
        "egress-invocation-jws-header.schema.json", "egress-invocation-token-claims.schema.json",
    ),
    ("agent-runtime-provider-v1.yaml", "RuntimeInvocationBearer"): (
        "agent-runtime-invocation-jws-header.schema.json", "agent-runtime-invocation-token-claims.schema.json",
    ),
    ("sandbox-provider-v1.yaml", "SandboxInvocationBearer"): (
        "sandbox-operation-jws-header-v2.schema.json", "sandbox-operation-token-claims-v2.schema.json",
    ),
    ("credential-gateway-v1.yaml", "CredentialOperationBearer"): (
        "credential-operation-jws-header.schema.json", "credential-operation-token-claims.schema.json",
    ),
}
for (openapi_name, scheme_name), (header_name, claims_name) in jwt_security_profiles.items():
    document = load_yaml(CONTRACT_ROOT / "openapi" / openapi_name)
    scheme = document["components"]["securitySchemes"][scheme_name]
    header = json.loads((CONTRACT_ROOT / "schemas" / header_name).read_text(encoding="utf-8"))
    claims = json.loads((CONTRACT_ROOT / "schemas" / claims_name).read_text(encoding="utf-8"))
    assert scheme.get("x-jws-header-contract-id") == header["$id"], (openapi_name, scheme_name)
    assert scheme.get("x-jwt-claims-contract-id") == claims["$id"], (openapi_name, scheme_name)

sandbox_provider_openapi = load_yaml(CONTRACT_ROOT / "openapi/sandbox-provider-v1.yaml")
admission_context = sandbox_provider_openapi.get("x-protected-operation-admission-context")
assert admission_context == {
    "header": "X-Agent-Sandbox-Admission-Context",
    "schema_contract_id": "urn:agent-platform:sandbox-provider-admission-context:v1",
    "encoding": "unpadded-base64url-utf8-rfc8785-jcs-v1",
    "max_encoded_bytes": 16384,
    "carrier_schema": {
        "type": "string", "minLength": 1, "maxLength": 16384,
        "pattern": "^[A-Za-z0-9_-]+$",
    },
    "rejection": [
        "whitespace", "padding", "duplicate_header", "duplicate_json_member",
        "unknown_context_member", "multiple_json_value", "malformed_or_oversized_value",
    ],
    "required_for_operation_ids": [
        "createSandbox", "restoreSandbox", "getSandbox", "setSandboxDesiredState",
        "extendSandboxLease", "executeInSandbox", "cancelSandboxExec",
        "openSandboxRuntimeSession", "createSandboxSnapshot", "terminateSandbox",
        "getSandboxOperation", "getSandboxExecResult", "getSandboxSnapshotManifest",
        "streamSandboxEvents",
    ],
    "excluded_operation_ids": ["getSandboxCapabilities"],
}, "Sandbox Admission Context carrier mapping drift"

sandbox_status = json.loads((CONTRACT_ROOT / "schemas/sandbox-status.schema.json").read_text(encoding="utf-8"))
forbidden_sandbox_status_fields = {
    "runtime_id", "region_id", "cluster_id", "cell_id", "node_id",
    "pod_id", "pod_name", "namespace", "container_id", "vm_id", "endpoint",
}
assert not forbidden_sandbox_status_fields.intersection(sandbox_status["properties"]), (
    "Public SandboxStatus leaks Provider topology or raw runtime identity"
)
provider_health = json.loads((CONTRACT_ROOT / "schemas/provider-health.schema.json").read_text(encoding="utf-8"))
assert not {"cluster_id", "cell_id", "pod_id", "node_id", "namespace"}.intersection(
    provider_health["properties"]
), "ProviderHealth leaks mutable deployment topology into Resolution evidence"
run_manifest_schema = json.loads((CONTRACT_ROOT / "schemas/run-manifest-v2.schema.json").read_text(encoding="utf-8"))
assert not {"cluster_id", "cell_id", "runtime_id", "endpoint"}.intersection(
    run_manifest_schema["properties"]["location"]["properties"]
), "RunManifest location exposes mutable Provider topology"
sandbox_spec_schema = json.loads((CONTRACT_ROOT / "schemas/sandbox-spec.schema.json").read_text(encoding="utf-8"))
assert not {"cluster_id", "cell_id", "node_id", "runtime_id", "endpoint"}.intersection(
    sandbox_spec_schema["properties"]["placement_constraints"]["properties"]
), "SandboxSpec exposes Provider-private topology"
canonical_event_schema = json.loads((CONTRACT_ROOT / "schemas/canonical-event-v2.schema.json").read_text(encoding="utf-8"))
assert not {"runtime_id", "endpoint", "cluster_id", "cell_id", "node_id", "pod_id", "vm_id"}.intersection(
    canonical_event_schema["properties"]["metadata"]["properties"]
), "CanonicalEvent metadata exposes Provider-private runtime or topology identity"

for metadata_schema_path in (
    "schemas/conversation-create-request.schema.json",
    "schemas/conversation-turn-request.schema.json",
    "schemas/work-order-request.schema.json",
    "schemas/work-order-control-request.schema.json",
):
    metadata_schema = json.loads((CONTRACT_ROOT / metadata_schema_path).read_text(encoding="utf-8"))[
        "properties"
    ]["metadata"]
    assert metadata_schema.get("maxProperties", 0) > 0, metadata_schema_path
    assert metadata_schema.get("additionalProperties", {}).get("type") == "string", metadata_schema_path

def assert_bounded_details(value: Any, path: str) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if key == "details":
                assert child == {"$ref": "urn:agent-platform:bounded-details:v1"}, path
            else:
                assert_bounded_details(child, path)
    elif isinstance(value, list):
        for child in value:
            assert_bounded_details(child, path)

for schema_path in sorted((CONTRACT_ROOT / "schemas").glob("*.json")):
    if schema_path.name != "bounded-details.schema.json":
        assert_bounded_details(json.loads(schema_path.read_text(encoding="utf-8")), str(schema_path))

markdown_files = source_files(["*.md"])
link_pattern = re.compile(r"\[[^\]]+\]\(([^)]+)\)")
missing_links: list[str] = []
for path in markdown_files:
    for target in link_pattern.findall(path.read_text(encoding="utf-8")):
        target = target.split("#", 1)[0]
        if not target or "://" in target or target.startswith("mailto:"):
            continue
        if not (path.parent / target).resolve().exists():
            missing_links.append(f"{path.relative_to(CONTRACT_ROOT)} -> {target}")
assert not missing_links, "Missing Markdown links:\n" + "\n".join(missing_links)

evidence_dir = SCRIPT_ROOT / "build/validation"
evidence_dir.mkdir(parents=True, exist_ok=True)
(evidence_dir / "static.json").write_text(json.dumps({
    "json_documents": len(json_files),
    "yaml_documents": len(yaml_files),
    "openapi_documents": len(openapi_files),
    "markdown_documents": len(markdown_files),
}, indent=2) + "\n", encoding="utf-8")
print(f"Offline static audit passed: {len(json_files)} JSON, {len(yaml_files)} YAML, {len(openapi_files)} OpenAPI, {len(markdown_files)} Markdown source files.")
