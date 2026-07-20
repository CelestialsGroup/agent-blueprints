#!/usr/bin/env python3
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Iterable

import yaml

ROOT = Path(__file__).resolve().parents[1]
SOURCE_DIRS = ["contracts", "deploy", "docs", "examples", "prompts", "tasks", "scripts"]


def source_files(patterns: Iterable[str]) -> list[Path]:
    paths: set[Path] = set()
    for directory in SOURCE_DIRS:
        base = ROOT / directory
        if base.exists():
            for pattern in patterns:
                paths.update(base.rglob(pattern))
    for pattern in patterns:
        paths.update(ROOT.glob(pattern))
    return sorted(path for path in paths if path.is_file())


def load_yaml(path: Path) -> Any:
    documents = list(yaml.safe_load_all(path.read_text(encoding="utf-8")))
    return documents[0] if len(documents) == 1 else documents


json_files = source_files(["*.json"])
yaml_files = source_files(["*.yaml", "*.yml"])
for path in json_files:
    json.loads(path.read_text(encoding="utf-8"))
for path in yaml_files:
    list(yaml.safe_load_all(path.read_text(encoding="utf-8")))

openapi_files = sorted((ROOT / "contracts/openapi").glob("*.yaml"))
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
}
token_extensions = {
    "capability-provider-v1.yaml": "x-required-capability-token-operation",
    "artifact-gateway-v1.yaml": "x-required-artifact-token-operation",
    "sandbox-provider-v1.yaml": "x-required-sandbox-token-operation",
    "agent-runtime-provider-v1.yaml": "x-required-runtime-token-operation",
    "plugin-invocation-v1.yaml": "x-required-plugin-token-operation",
    "egress-gateway-v1.yaml": "x-required-egress-token-operation",
}
seen_operation_profiles: set[tuple[str, str]] = set()
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
}
assert len(set(jws_header_profiles.values())) == len(jws_header_profiles)
for schema_name, token_type in jws_header_profiles.items():
    header = json.loads((ROOT / "contracts/schemas" / schema_name).read_text(encoding="utf-8"))
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
        "sandbox-operation-jws-header.schema.json", "sandbox-operation-token-claims.schema.json",
    ),
}
for (openapi_name, scheme_name), (header_name, claims_name) in jwt_security_profiles.items():
    document = load_yaml(ROOT / "contracts/openapi" / openapi_name)
    scheme = document["components"]["securitySchemes"][scheme_name]
    header = json.loads((ROOT / "contracts/schemas" / header_name).read_text(encoding="utf-8"))
    claims = json.loads((ROOT / "contracts/schemas" / claims_name).read_text(encoding="utf-8"))
    assert scheme.get("x-jws-header-contract-id") == header["$id"], (openapi_name, scheme_name)
    assert scheme.get("x-jwt-claims-contract-id") == claims["$id"], (openapi_name, scheme_name)

sandbox_status = json.loads((ROOT / "contracts/schemas/sandbox-status.schema.json").read_text(encoding="utf-8"))
forbidden_sandbox_status_fields = {
    "runtime_id", "region_id", "cluster_id", "cell_id", "node_id",
    "pod_id", "pod_name", "namespace", "container_id", "vm_id", "endpoint",
}
assert not forbidden_sandbox_status_fields.intersection(sandbox_status["properties"]), (
    "Public SandboxStatus leaks Provider topology or raw runtime identity"
)
provider_health = json.loads((ROOT / "contracts/schemas/provider-health.schema.json").read_text(encoding="utf-8"))
assert not {"cluster_id", "cell_id", "pod_id", "node_id", "namespace"}.intersection(
    provider_health["properties"]
), "ProviderHealth leaks mutable deployment topology into Resolution evidence"
run_manifest_schema = json.loads((ROOT / "contracts/schemas/run-manifest-v2.schema.json").read_text(encoding="utf-8"))
assert not {"cluster_id", "cell_id", "runtime_id", "endpoint"}.intersection(
    run_manifest_schema["properties"]["location"]["properties"]
), "RunManifest location exposes mutable Provider topology"
sandbox_spec_schema = json.loads((ROOT / "contracts/schemas/sandbox-spec.schema.json").read_text(encoding="utf-8"))
assert not {"cluster_id", "cell_id", "node_id", "runtime_id", "endpoint"}.intersection(
    sandbox_spec_schema["properties"]["placement_constraints"]["properties"]
), "SandboxSpec exposes Provider-private topology"
canonical_event_schema = json.loads((ROOT / "contracts/schemas/canonical-event-v2.schema.json").read_text(encoding="utf-8"))
assert not {"runtime_id", "endpoint", "cluster_id", "cell_id", "node_id", "pod_id", "vm_id"}.intersection(
    canonical_event_schema["properties"]["metadata"]["properties"]
), "CanonicalEvent metadata exposes Provider-private runtime or topology identity"

for metadata_schema_path in (
    "contracts/schemas/conversation-create-request.schema.json",
    "contracts/schemas/conversation-turn-request.schema.json",
    "contracts/schemas/work-order-request.schema.json",
    "contracts/schemas/work-order-control-request.schema.json",
):
    metadata_schema = json.loads((ROOT / metadata_schema_path).read_text(encoding="utf-8"))[
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

for schema_path in sorted((ROOT / "contracts/schemas").glob("*.json")):
    if schema_path.name != "bounded-details.schema.json":
        assert_bounded_details(json.loads(schema_path.read_text(encoding="utf-8")), str(schema_path))

kustomization_path = ROOT / "deploy/k8s/base/kustomization.yaml"
for resource in load_yaml(kustomization_path).get("resources", []):
    assert (kustomization_path.parent / resource).resolve().exists(), f"Missing Kustomize resource: {resource}"

namespace_docs = load_yaml(ROOT / "deploy/k8s/base/namespace.yaml")
namespace_names = {doc["metadata"]["name"] for doc in namespace_docs if doc and doc.get("kind") == "Namespace"}
assert {"agent-platform", "agent-runtime"}.issubset(namespace_names)

network_docs = load_yaml(ROOT / "deploy/k8s/base/network-policy.yaml")
policy_names = {doc["metadata"]["name"] for doc in network_docs if doc and doc.get("kind") == "NetworkPolicy"}
assert {
    "default-deny-control-plane", "default-deny-runtime", "allow-control-plane-dns",
    "allow-runtime-dns", "allow-runtime-to-egress-gateway"
}.issubset(policy_names)

runtime_docs = load_yaml(ROOT / "deploy/k8s/base/runtime-gateway.yaml")
deployment = next(doc for doc in runtime_docs if doc.get("kind") == "Deployment")
pod_spec = deployment["spec"]["template"]["spec"]
assert pod_spec["securityContext"]["runAsNonRoot"] is True
security = pod_spec["containers"][0]["securityContext"]
assert security["allowPrivilegeEscalation"] is False
assert security["readOnlyRootFilesystem"] is True
assert security["capabilities"]["drop"] == ["ALL"]

markdown_files = source_files(["*.md"])
link_pattern = re.compile(r"\[[^\]]+\]\(([^)]+)\)")
missing_links: list[str] = []
for path in markdown_files:
    for target in link_pattern.findall(path.read_text(encoding="utf-8")):
        target = target.split("#", 1)[0]
        if not target or "://" in target or target.startswith("mailto:"):
            continue
        if not (path.parent / target).resolve().exists():
            missing_links.append(f"{path.relative_to(ROOT)} -> {target}")
assert not missing_links, "Missing Markdown links:\n" + "\n".join(missing_links)

evidence_dir = ROOT / "build/validation"
evidence_dir.mkdir(parents=True, exist_ok=True)
(evidence_dir / "static.json").write_text(json.dumps({
    "json_documents": len(json_files),
    "yaml_documents": len(yaml_files),
    "openapi_documents": len(openapi_files),
    "markdown_documents": len(markdown_files),
}, indent=2) + "\n", encoding="utf-8")
print(f"Offline static audit passed: {len(json_files)} JSON, {len(yaml_files)} YAML, {len(openapi_files)} OpenAPI, {len(markdown_files)} Markdown source files.")
