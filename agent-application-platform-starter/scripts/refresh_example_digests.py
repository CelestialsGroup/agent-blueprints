#!/usr/bin/env python3
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any

import rfc8785
import yaml

ROOT = Path(__file__).resolve().parents[1]


def read(relative: str) -> dict[str, Any]:
    return json.loads((ROOT / relative).read_text(encoding="utf-8"))


def write(relative: str, value: dict[str, Any]) -> None:
    (ROOT / relative).write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def read_yaml(relative: str) -> dict[str, Any]:
    return yaml.safe_load((ROOT / relative).read_text(encoding="utf-8"))


def write_yaml(relative: str, value: dict[str, Any]) -> None:
    (ROOT / relative).write_text(
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
    return "sha256:" + hashlib.sha256((ROOT / relative).read_bytes()).hexdigest()


def bytes_digest(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


suite_paths = {
    "agent_runtime": "contracts/conformance/runtime/v1/suite.json",
    "sandbox": "contracts/conformance/sandbox/v1/suite.json",
    "runtime_gateway": "contracts/conformance/runtime-gateway/v1/suite.json",
    "capability_provider": "contracts/conformance/capability/v1/suite.json",
    "execution_gateway": "contracts/conformance/execution-gateway/v1/suite.json",
}
suites: dict[str, dict[str, Any]] = {}
for target_kind, path in suite_paths.items():
    suite = read(path)
    suite["suite_digest"] = digest_without(suite, "suite_digest")
    suites[target_kind] = suite
    write(path, suite)

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


revision_paths = [
    "examples/contracts/sandbox-provider-revision.json",
    "examples/contracts/agent-runtime-provider-revision.json",
    "examples/contracts/tool-provider-revision.json",
    "examples/contracts/html-skill-provider-revision.json",
    "examples/contracts/renderer-provider-revision.json",
    "examples/contracts/template-provider-revision.json",
]
decision_paths = [
    "examples/contracts/provider-admission-decision.json",
    "examples/contracts/agent-runtime-admission-decision.json",
    "examples/contracts/tool-provider-admission-decision.json",
    "examples/contracts/html-skill-provider-admission-decision.json",
    "examples/contracts/renderer-provider-admission-decision.json",
    "examples/contracts/template-provider-admission-decision.json",
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
            "agent_runtime": "contracts/openapi/agent-runtime-provider-v1.yaml",
            "sandbox": "contracts/openapi/sandbox-provider-v1.yaml",
        }.get(revision["provider_kind"], "contracts/openapi/capability-provider-v1.yaml")
        revision["port"] = {
            "protocol": protocol,
            "protocol_version": "v1",
            "contract_digest": file_digest(contract_path),
            "binding_digest": legacy_binding_digest or digest({"binding": revision["provider_revision_id"]}),
        }
    contract_path = {
        "agent_runtime": "contracts/openapi/agent-runtime-provider-v1.yaml",
        "sandbox": "contracts/openapi/sandbox-provider-v1.yaml",
    }.get(revision["provider_kind"], "contracts/openapi/capability-provider-v1.yaml")
    revision["port"]["contract_digest"] = file_digest(contract_path)
    if revision["provider_kind"] == "agent_runtime":
        suite = suites["agent_runtime"]
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
) -> dict[str, Any]:
    revision = revisions[revision_id]
    provider_audience = f"urn:agent-platform:provider-instance:{revision['provider_instance_id']}"
    resolution_input = {
        "tenant_id": "ten_01J00000000000000000000000",
        "client_app_id": "html-product",
        "work_order_id": "wrk_01J00000000000000000000000",
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
        "work_order_id": "wrk_01J00000000000000000000000",
        "execution_scope": "work_order",
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
workspace_revision["content_manifest_artifact"]["size_bytes"] = (ROOT / workspace_manifest_path).stat().st_size
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
write("examples/contracts/sandbox-spec.json", sandbox_spec)
sandbox_create = read("examples/contracts/sandbox-create-request.json")
sandbox_create["spec"] = copy.deepcopy(sandbox_spec)
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
sandbox_restore["request_digest"] = digest_without(sandbox_restore, "request_digest")
write("examples/contracts/sandbox-restore-request.json", sandbox_restore)
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
budget["work_order_id"] = "wrk_01J00000000000000000000000"
budget["limits"] = copy.deepcopy(commercial["authorized_limits"])
budget["budget_digest"] = digest_without(budget, "budget_digest")
write(budget_path, budget)

permissions_path = "examples/contracts/effective-permissions.json"
permissions = read(permissions_path)
permissions["tenant_id"] = budget["tenant_id"]
permissions["work_order_id"] = budget["work_order_id"]
legacy_artifact_permissions = permissions["artifact"]
permissions["artifact"] = {
    "read": legacy_artifact_permissions["read"],
    "stage_new_version": legacy_artifact_permissions.get(
        "stage_new_version", legacy_artifact_permissions.get("write", False)
    ),
}
if "public-docs-origin" not in permissions["egress"]["allowed_destination_classes"]:
    permissions["egress"]["allowed_destination_classes"].append("public-docs-origin")
permissions["permissions_digest"] = digest_without(permissions, "permissions_digest")
write(permissions_path, permissions)

runtime_input_path = "examples/contracts/runtime-input-envelope.json"
runtime_input = read(runtime_input_path)
runtime_input["content_digest"] = digest(runtime_input["content"])
write(runtime_input_path, runtime_input)

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
        "contracts/openapi/capability-provider-v1.yaml",
    ),
    "tool": (
        "urn:agent-platform:openapi:capability-provider:v1",
        "contracts/openapi/capability-provider-v1.yaml",
    ),
    "artifact": (
        "urn:agent-platform:openapi:artifact-gateway:v1",
        "contracts/openapi/artifact-gateway-v1.yaml",
    ),
    "egress": (
        "urn:agent-platform:openapi:egress-gateway:v1",
        "contracts/openapi/egress-gateway-v1.yaml",
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
artifact_grant.pop("runtime_run_id", None)
artifact_grant["execution_scope"] = {
    "kind": "runtime_invocation",
    "runtime_run_id": "rtr_01J00000000000000000000000",
    "invocation_id": "inv_runtime_start_01J000000000000",
    "invocation_attempt_id": "iat_runtime_start_01J00000000000",
}
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
for field in ("tenant_id", "work_order_id", "artifact_id", "version_id", "artifact_digest"):
    artifact_requirement[field] = artifact_grant[field]
artifact_requirement["allowed_permissions"] = copy.deepcopy(artifact_grant["permissions"])
write(artifact_requirement_path, artifact_requirement)

usage_entry_path = "examples/contracts/technical-usage-entry.json"
usage_entry = read(usage_entry_path)
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
write("contracts/tests/invalid/usage-report-first-correction.json", first_correction)

settlement_path = "examples/contracts/business-settlement-envelope.json"
settlement = read(settlement_path)
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
write("contracts/tests/invalid/settlement-reconcile-final-report.json", reconcile_with_final)

policy_path = "examples/contracts/policy-decision.json"
policy = read(policy_path)
policy["decision_point"] = "run_admission"
policy["commercial_authorization_id"] = commercial["commercial_authorization_id"]
policy["commercial_authorization_digest"] = commercial["commercial_authorization_digest"]
policy["execution_budget_id"] = budget["budget_id"]
policy["execution_budget_digest"] = budget["budget_digest"]
policy["effective_permissions_digest"] = permissions["permissions_digest"]
policy["decision_digest"] = digest_without(policy, "decision_digest")
write(policy_path, policy)

event_data_schema = read("contracts/schemas/agent-runtime-event-data.schema.json")
event_registry_path = "contracts/event-types/agent-runtime-core-v1.json"
event_registry = read(event_registry_path)
event_dependencies = sorted(
    [
        read("contracts/schemas/capability-error.schema.json"),
        read("contracts/schemas/usage-observation.schema.json"),
    ],
    key=lambda schema: schema["$id"],
)
event_data_digest = digest({"root": event_data_schema, "dependencies": event_dependencies})
for definition in event_registry["definitions"]:
    definition["data_schema"]["digest"] = event_data_digest
    definition["data_schema"]["digest_profile"] = "rfc8785-schema-closure-v1"
event_registry["registry_digest"] = digest_without(event_registry, "registry_digest")
write(event_registry_path, event_registry)

platform_event_schema = read("contracts/schemas/platform-core-event-data.schema.json")
platform_event_dependencies = [read("contracts/schemas/work-order-state.schema.json")]
platform_event_schema_digest = digest({
    "root": platform_event_schema,
    "dependencies": sorted(platform_event_dependencies, key=lambda schema: schema["$id"]),
})
platform_registry_path = "contracts/event-types/platform-core-v1.json"
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


manifest_path = "examples/contracts/run-manifest-v2.json"
manifest = read(manifest_path)
manifest["agent_run_id"] = manifest.pop("run_id", "agr_01J00000000000000000000000")
manifest["workflow_run_id"] = "wfr_01J00000000000000000000000"
manifest["tenant_id"] = "ten_01J00000000000000000000000"
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
turn_request_for_manifest = read("examples/contracts/conversation-turn-request.json")
manifest.pop("request_digest", None)
manifest["request_binding"] = {
    "request_contract_id": "urn:agent-platform:conversation-turn-request:v1",
    "request_digest_profile": "rfc8785-request-excluding-execution-grant-v1",
    "request_digest": digest_without(turn_request_for_manifest, "execution_grant"),
}
manifest["run_manifest_digest"] = digest_without(manifest, "run_manifest_digest")
write(manifest_path, manifest)

missing_sandbox_resolution = copy.deepcopy(manifest)
missing_sandbox_resolution["sandboxes"][0].pop("resolution_id")
write("contracts/tests/invalid/run-manifest-missing-sandbox-resolution.json", missing_sandbox_resolution)

empty_execution = copy.deepcopy(manifest)
empty_execution["capability_resolutions"] = []
write("contracts/tests/invalid/run-manifest-empty-execution.json", empty_execution)

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
    "kind": "runtime_invocation",
    "runtime_run_id": runtime_start["runtime_run_id"],
    "invocation_id": runtime_start["invocation_id"],
    "invocation_attempt_id": runtime_start["invocation_attempt_id"],
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
        "policy_decision": copy.deepcopy(manifest_value["policy_decision"]),
        "effective_permissions": copy.deepcopy(manifest_value["effective_permissions"]),
        "artifact_grants": [copy.deepcopy(artifact_grant)],
        "issued_at": "2026-07-16T09:01:00Z",
        "expires_at": "2026-07-16T09:15:00Z",
    })
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
renewed_authorization["artifact_grants"][0]["execution_scope"]["invocation_attempt_id"] = (
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
    "input", "context_package", "gateway_bindings", "admission_limits",
):
    runtime_start[field] = copy.deepcopy(manifest[field])
runtime_start["runtime_authorization"] = copy.deepcopy(runtime_authorization)
runtime_start["request_digest"] = digest_without(runtime_start, "request_digest")
write("examples/contracts/agent-runtime-start-request.json", runtime_start)

no_sandbox_runtime_start = copy.deepcopy(runtime_start)
no_sandbox_runtime_start["run_manifest_digest"] = no_sandbox_manifest["run_manifest_digest"]
no_sandbox_runtime_start["sandbox_bindings"] = []
for field in (
    "input", "context_package", "gateway_bindings", "admission_limits",
):
    no_sandbox_runtime_start[field] = copy.deepcopy(no_sandbox_manifest[field])
no_sandbox_runtime_start["runtime_authorization"] = make_runtime_authorization(
    no_sandbox_manifest,
    no_sandbox_runtime_start,
    "rauth_no_sandbox_01J000000000000000",
)
no_sandbox_runtime_start["request_digest"] = digest_without(no_sandbox_runtime_start, "request_digest")
write("examples/contracts/agent-runtime-start-no-sandbox.json", no_sandbox_runtime_start)

runtime_status = read("examples/contracts/agent-runtime-run-status.json")
runtime_status["tenant_id"] = manifest["tenant_id"]
runtime_status["workflow_run_id"] = manifest["workflow_run_id"]
runtime_status["agent_run_id"] = manifest["agent_run_id"]
write("examples/contracts/agent-runtime-run-status.json", runtime_status)

runtime_command = read("examples/contracts/agent-runtime-command.json")
runtime_command["authorized_control_request_id"] = control_request["control_request_id"]
control_runtime_input = read("examples/contracts/work-order-control-runtime-input.json")
control_runtime_input["content"] = copy.deepcopy(control_request["content"]["content"])
control_runtime_input["content_digest"] = control_request["content"]["content_digest"]
write("examples/contracts/work-order-control-runtime-input.json", control_runtime_input)
runtime_command["input_id"] = control_runtime_input["input_id"]
runtime_command["input_content_digest"] = control_runtime_input["content_digest"]
runtime_command["command_digest"] = digest_without(runtime_command, "command_digest")
write("examples/contracts/agent-runtime-command.json", runtime_command)

runtime_capabilities = read("examples/contracts/agent-runtime-capabilities.json")
runtime_capabilities.pop("event_schema_versions", None)
runtime_capabilities["event_registries"] = [{
    "registry_id": event_registry["registry_id"],
    "registry_version": event_registry["registry_version"],
    "registry_digest": event_registry["registry_digest"],
}]
write("examples/contracts/agent-runtime-capabilities.json", runtime_capabilities)

runtime_token = read("examples/contracts/agent-runtime-invocation-token-claims.json")
runtime_token.update({
    "tenant_id": manifest["tenant_id"],
    "provider_revision_id": revisions["apr_01J00000000000000000000000"]["provider_revision_id"],
    "runtime_run_id": runtime_start["runtime_run_id"],
    "agent_run_id": manifest["agent_run_id"],
    "workflow_run_id": manifest["workflow_run_id"],
    "work_order_id": manifest["work_order_id"],
    "run_manifest_digest": manifest["run_manifest_digest"],
    "runtime_authorization_digest": runtime_authorization["authorization_digest"],
    "request_digest": runtime_start["request_digest"],
    "invocation_id": runtime_start["invocation_id"],
    "invocation_attempt_id": runtime_start["invocation_attempt_id"],
    "fencing_token": runtime_start["fencing_token"],
    "policy_decision_digest": runtime_authorization["policy_decision"]["decision_digest"],
    "execution_budget_digest": runtime_authorization["execution_budget"]["budget_digest"],
    "effective_permissions_digest": runtime_authorization["effective_permissions"]["permissions_digest"],
})
write("examples/contracts/agent-runtime-invocation-token-claims.json", runtime_token)

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
    "work_order_id": manifest["work_order_id"],
    "provider_resolution_id": capability_resolution["resolution_id"],
    "provider_instance_id": capability_resolution["selected_provider_instance_id"],
    "provider_revision_id": capability_resolution["selected_provider_revision"]["provider_revision_id"],
    "deadline_at": "2026-07-16T09:20:00Z",
    "commercial_authorization": copy.deepcopy(commercial_binding),
    "execution_budget": copy.deepcopy(budget),
    "policy_decision": capability_policy,
    "effective_permissions": copy.deepcopy(permissions),
})
for legacy_field in (
    "output_staging_session_id", "policy_decision_digest",
    "execution_budget_digest", "permissions_digest",
):
    capability_request.pop(legacy_field, None)
capability_artifact_grant = copy.deepcopy(artifact_grant)
capability_artifact_grant["grant_id"] = "artg_cap_01J0000000000000000000"
capability_artifact_grant["execution_scope"] = {
    "kind": "capability_invocation",
    "invocation_id": capability_request["invocation_id"],
    "invocation_attempt_id": capability_request["invocation_attempt_id"],
}
capability_artifact_grant["expires_at"] = capability_request["deadline_at"]
capability_artifact_grant["grant_digest"] = digest_without(
    capability_artifact_grant, "grant_digest"
)
capability_request["input_artifact_grants"] = [capability_artifact_grant]
staging_grant = {
    "staging_grant_id": "stgg_01J0000000000000000000000",
    "tenant_id": capability_request["tenant_id"],
    "work_order_id": capability_request["work_order_id"],
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
    "aud": capability_resolution["selected_provider_audience"],
    "iat": 1784192470,
    "nbf": 1784192470,
    "exp": 1784192770,
    "operation": "invoke",
    "authorization_sequence": 1,
    "predecessor_jti": None,
    "renewal_reason": "initial_dispatch",
    "tenant_id": capability_request["tenant_id"],
    "client_app_id": capability_request["client_app_id"],
    "principal_context_digest": capability_request["principal_context_digest"],
    "work_order_id": capability_request["work_order_id"],
    "provider_resolution_id": capability_request["provider_resolution_id"],
    "provider_instance_id": capability_request["provider_instance_id"],
    "provider_revision_id": capability_request["provider_revision_id"],
    "capability_id": capability_request["capability"]["id"],
    "capability_version": capability_request["capability"]["version"],
    "invocation_id": capability_request["invocation_id"],
    "invocation_attempt_id": capability_request["invocation_attempt_id"],
    "fencing_token": capability_request["fencing_token"],
    "invocation_request_digest": capability_request["request_digest"],
    "operation_request_digest": capability_request["request_digest"],
    "policy_decision_digest": capability_request["policy_decision"]["decision_digest"],
    "execution_budget_digest": capability_request["execution_budget"]["budget_digest"],
    "permissions_digest": permissions["permissions_digest"],
    "staging_grant_digest": staging_grant["grant_digest"],
}
write("examples/contracts/capability-invocation-token-claims.json", capability_token)

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
capability_status_token = copy.deepcopy(capability_token)
capability_status_token.update({
    "jti": "cit_01J00000000000000000000001",
    "iat": 1784193010,
    "nbf": 1784193010,
    "exp": 1784193310,
    "operation": "status",
    "authorization_sequence": 2,
    "predecessor_jti": capability_token["jti"],
    "renewal_reason": "status_query",
    "provider_operation_id": status_operation["provider_operation_id"],
    "operation_request_digest": digest(status_operation),
})
write("examples/contracts/capability-invocation-status-token-claims.json", capability_status_token)

capability_cancel_token = copy.deepcopy(capability_status_token)
capability_cancel_token.update({
    "jti": "cit_01J00000000000000000000002",
    "iat": 1784193320,
    "nbf": 1784193320,
    "exp": 1784193600,
    "operation": "cancel",
    "authorization_sequence": 3,
    "predecessor_jti": capability_status_token["jti"],
    "renewal_reason": "cancellation",
    "operation_request_digest": capability_cancel["request_digest"],
})
write("examples/contracts/capability-cancellation-token-claims.json", capability_cancel_token)

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
    "aud": staging_grant["gateway_binding"]["audience"],
    "iat": 1784192470,
    "nbf": 1784192470,
    "exp": 1784192770,
    "operation": "stage_object",
    "tenant_id": capability_request["tenant_id"],
    "work_order_id": capability_request["work_order_id"],
    "invocation_id": capability_request["invocation_id"],
    "invocation_attempt_id": capability_request["invocation_attempt_id"],
    "fencing_token": capability_request["fencing_token"],
    "gateway_binding_digest": staging_grant["gateway_binding"]["binding_digest"],
    "request_digest": staging_object["request_digest"],
    "staging_grant_digest": staging_grant["grant_digest"],
}
write("examples/contracts/artifact-gateway-stage-token-claims.json", artifact_stage_token)

artifact_read_descriptor = {
    "operation": "read_content",
    "tenant_id": capability_request["tenant_id"],
    "work_order_id": capability_request["work_order_id"],
    "invocation_id": capability_request["invocation_id"],
    "invocation_attempt_id": capability_request["invocation_attempt_id"],
    "fencing_token": capability_request["fencing_token"],
    "artifact_id": capability_artifact_grant["artifact_id"],
    "version_id": capability_artifact_grant["version_id"],
}
artifact_read_token = {
    "jti": "agt_01J00000000000000000000002",
    "iss": "agent-platform",
    "aud": capability_artifact_grant["gateway_binding"]["audience"],
    "iat": 1784193070,
    "nbf": 1784193070,
    "exp": 1784193370,
    "operation": "read_content",
    "tenant_id": capability_request["tenant_id"],
    "work_order_id": capability_request["work_order_id"],
    "invocation_id": capability_request["invocation_id"],
    "invocation_attempt_id": capability_request["invocation_attempt_id"],
    "fencing_token": capability_request["fencing_token"],
    "gateway_binding_digest": capability_artifact_grant["gateway_binding"]["binding_digest"],
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
    "request_digest": staging_commit["request_digest"],
})
write("examples/contracts/artifact-gateway-commit-token-claims.json", artifact_commit_token)

egress_request = {
    "tenant_id": manifest["tenant_id"],
    "work_order_id": manifest["work_order_id"],
    "runtime_run_id": runtime_start["runtime_run_id"],
    "invocation_id": "inv_egress_01J0000000000000000000",
    "invocation_attempt_id": "iat_egress_01J000000000000000000",
    "fencing_token": 1,
    "destination_id": "public-docs-origin",
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
    "aud": gateway_bindings["egress"]["port"]["audience"],
    "iat": 1784192470,
    "nbf": 1784192470,
    "exp": 1784192770,
    "tenant_id": egress_request["tenant_id"],
    "work_order_id": egress_request["work_order_id"],
    "runtime_run_id": egress_request["runtime_run_id"],
    "invocation_id": egress_request["invocation_id"],
    "invocation_attempt_id": egress_request["invocation_attempt_id"],
    "fencing_token": egress_request["fencing_token"],
    "destination_id": egress_request["destination_id"],
    "gateway_binding_digest": gateway_bindings["egress"]["port"]["binding_digest"],
    "request_digest": egress_request["request_digest"],
    "policy_decision_digest": runtime_authorization["policy_decision"]["decision_digest"],
    "execution_budget_digest": runtime_authorization["execution_budget"]["budget_digest"],
    "permissions_digest": runtime_authorization["effective_permissions"]["permissions_digest"],
}
write("examples/contracts/egress-invocation-token-claims.json", egress_token)

missing_runtime_input = copy.deepcopy(runtime_start)
missing_runtime_input.pop("input")
write("contracts/tests/invalid/runtime-start-missing-executable-input.json", missing_runtime_input)

missing_control_grant = copy.deepcopy(control_request)
missing_control_grant.pop("execution_grant")
write("contracts/tests/invalid/work-order-control-missing-grant.json", missing_control_grant)

pause_with_message_cas = copy.deepcopy(control_request)
pause_with_message_cas["action"] = "pause"
pause_with_message_cas.pop("content", None)
write("contracts/tests/invalid/work-order-control-pause-with-message-cas.json", pause_with_message_cas)

control_grant_with_turn = copy.deepcopy(control_grant)
control_grant_with_turn["turn_id"] = "turn_forbidden_on_control"
write("contracts/tests/invalid/execution-grant-control-with-turn-binding.json", control_grant_with_turn)

artifact_finalize_grant = copy.deepcopy(artifact_grant)
artifact_finalize_grant["permissions"] = ["read", "finalize"]
write("contracts/tests/invalid/artifact-grant-provider-finalize.json", artifact_finalize_grant)

authorization_with_first_predecessor = copy.deepcopy(runtime_authorization)
authorization_with_first_predecessor["predecessor_authorization_digest"] = "sha256:" + "f" * 64
write(
    "contracts/tests/invalid/runtime-authorization-first-with-predecessor.json",
    authorization_with_first_predecessor,
)

disabled_gateway_with_route = copy.deepcopy(gateway_bindings)
disabled_gateway_with_route["egress"]["mode"] = "disabled"
disabled_gateway_with_route["egress"]["reason"] = "policy_denied"
write("contracts/tests/invalid/runtime-gateway-disabled-with-route.json", disabled_gateway_with_route)

missing_capability_digest = copy.deepcopy(capability_token)
missing_capability_digest.pop("invocation_request_digest")
write("contracts/tests/invalid/capability-token-missing-request-digest.json", missing_capability_digest)

missing_capability_budget = copy.deepcopy(capability_request)
missing_capability_budget.pop("execution_budget")
write("contracts/tests/invalid/capability-request-missing-execution-budget.json", missing_capability_budget)

first_token_for_status = copy.deepcopy(capability_token)
first_token_for_status["operation"] = "status"
first_token_for_status["provider_operation_id"] = "provider-op-html-0001"
write("contracts/tests/invalid/capability-token-first-authorizes-status.json", first_token_for_status)

renewed_token_without_predecessor = copy.deepcopy(capability_status_token)
renewed_token_without_predecessor["predecessor_jti"] = None
write("contracts/tests/invalid/capability-token-renewed-without-predecessor.json", renewed_token_without_predecessor)

manifest_without_request_binding = copy.deepcopy(manifest)
manifest_without_request_binding.pop("request_binding")
write("contracts/tests/invalid/run-manifest-missing-request-binding.json", manifest_without_request_binding)

artifact_read_with_staging_grant = copy.deepcopy(artifact_stage_token)
artifact_read_with_staging_grant["operation"] = "read_content"
write("contracts/tests/invalid/artifact-gateway-read-with-staging-grant.json", artifact_read_with_staging_grant)

egress_with_raw_origin = copy.deepcopy(egress_request)
egress_with_raw_origin["origin"] = "https://unregistered.example"
write("contracts/tests/invalid/egress-request-with-raw-origin.json", egress_with_raw_origin)

unsafe_workspace_manifest = copy.deepcopy(workspace_manifest)
unsafe_workspace_manifest["entries"][1]["path"] = "../escape.txt"
write("contracts/tests/invalid/workspace-manifest-unsafe-path.json", unsafe_workspace_manifest)

open_event_metadata = copy.deepcopy(canonical_event)
open_event_metadata["metadata"]["provider_private"] = "forbidden"
write("contracts/tests/invalid/canonical-event-open-metadata.json", open_event_metadata)

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
write("contracts/tests/invalid/runtime-gateway-control-extra-fields.json", gateway_control_extra)

port_forward_recording = read("examples/contracts/runtime-session-request.json")
port_forward_recording["runtime_type"] = "port_forward"
write("contracts/tests/invalid/runtime-session-port-forward-recording.json", port_forward_recording)

runtime_event = read("examples/contracts/agent-runtime-event.json")
runtime_event_page = read("examples/contracts/agent-runtime-event-page.json")
runtime_event_page["events"] = [runtime_event]
runtime_event_page["next_event_sequence"] = runtime_event["event_sequence"]
write("examples/contracts/agent-runtime-event-page.json", runtime_event_page)

workflow_run = {
    "workflow_run_id": manifest["workflow_run_id"],
    "tenant_id": manifest["tenant_id"],
    "work_order_id": manifest["work_order_id"],
    "root_agent_run_id": manifest["agent_run_id"],
    "workflow": manifest["workflow"],
    "orchestration_binding": manifest["orchestration_binding"],
    "created_at": "2026-07-16T09:01:00Z",
}
write("examples/contracts/workflow-run.json", workflow_run)

agent_run = {
    "agent_run_id": manifest["agent_run_id"],
    "tenant_id": manifest["tenant_id"],
    "runtime_run_id": runtime_start["runtime_run_id"],
    "workflow_run_id": manifest["workflow_run_id"],
    "work_order_id": manifest["work_order_id"],
    "root_agent_run_id": manifest["agent_run_id"],
    "run_kind": "root",
    "agent_role": "general",
    "runtime_provider_resolution_id": manifest["agent_runtime"]["resolution_id"],
    "run_manifest_digest": manifest["run_manifest_digest"],
    "created_at": "2026-07-16T09:01:00Z",
}
write("examples/contracts/agent-run.json", agent_run)

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
        "contract_digest": file_digest("contracts/openapi/capability-provider-v1.yaml"),
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
    return [("semantic_validator", "scripts/validate_semantics.py", check_id, "contract_gate")]


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
        contract_check("run_manifest.gateway_binding"),
        contract_check("run_manifest.commercial_event_binding"),
        contract_check("run_manifest.orchestration_binding"),
    ],
    "agent-runtime-start-request.schema.json": [
        contract_check("runtime_start.execution_topology"),
        contract_check("runtime_start.workspace_binding"),
        contract_check("runtime_start.sandbox_binding"),
        contract_check("runtime_start.request_digest"),
        contract_check("runtime_start.input_binding"),
        contract_check("runtime_start.immutable_context_binding") + contract_check("runtime_authorization.ceiling"),
        contract_check("runtime_authorization.scope") + contract_check("runtime_authorization.expiry") + contract_check("runtime_authorization.artifact_coverage"),
        implementation_check("conformance_test", "contracts/conformance/runtime/v1/suite.json", "start-encoded-body-limit"),
        contract_check("runtime_token.binding"),
    ],
    "work-order-control-request.schema.json": [
        contract_check("work_order_control.grant_binding"),
        contract_check("work_order_control.conditional_cas"),
        implementation_check("ddl_responsibility", "docs/26_DATA_MODEL_INVARIANTS.md", "work_order_control_input_allocation_and_outbox"),
    ],
    "conversation-branch.schema.json": [
        contract_check("conversation_branch.head_consistency"),
        implementation_check("ddl_responsibility", "docs/26_DATA_MODEL_INVARIANTS.md", "branch_fork_prior_message_fk"),
        implementation_check("ddl_responsibility", "docs/26_DATA_MODEL_INVARIANTS.md", "branch_one_active_work_order"),
        implementation_check("ddl_responsibility", "docs/26_DATA_MODEL_INVARIANTS.md", "message_workspace_active_work_split_cas"),
        implementation_check("ddl_responsibility", "docs/26_DATA_MODEL_INVARIANTS.md", "branch_etag_not_write_cas"),
        contract_check("conversation_branch.workspace_binding") + implementation_check("ddl_responsibility", "docs/26_DATA_MODEL_INVARIANTS.md", "branch_workspace_revision_fk"),
    ],
    "provider-resolution.schema.json": [
        contract_check("provider_resolution.decision_digest"),
        implementation_check("ddl_responsibility", "docs/26_DATA_MODEL_INVARIANTS.md", "provider_resolution_complete_input_evidence"),
        contract_check("provider_resolution.execution_scope") + implementation_check("ddl_responsibility", "docs/26_DATA_MODEL_INVARIANTS.md", "tenant_client_work_order_provider_resolution"),
        contract_check("provider_resolution.identity_dependency"),
        contract_check("provider_resolution.selected_candidate"),
        implementation_check("ddl_responsibility", "docs/26_DATA_MODEL_INVARIANTS.md", "provider_resolution_immutable_evidence_lookup"),
    ],
    "capability-invocation-request.schema.json": [
        contract_check("capability_invocation.request_digest"),
        implementation_check("conformance_test", "contracts/conformance/capability/v1/suite.json", "request-schema-boundaries"),
        contract_check("capability_invocation.resolution_binding") + implementation_check("conformance_test", "contracts/conformance/capability/v1/suite.json", "token-binding"),
        contract_check("capability_invocation.execution_context") + implementation_check("conformance_test", "contracts/conformance/capability/v1/suite.json", "budget-policy-enforced"),
        contract_check("capability_invocation.token_binding") + implementation_check("conformance_test", "contracts/conformance/capability/v1/suite.json", "token-binding"),
        contract_check("capability_invocation.artifact_grant_expiry") + contract_check("capability_invocation.staging_grant") + implementation_check("conformance_test", "contracts/conformance/capability/v1/suite.json", "artifact-contract"),
    ],
    "capability-invocation-token-claims.schema.json": [
        contract_check("capability_invocation.token_lifetime"),
        contract_check("capability_invocation.token_lineage"),
        contract_check("capability_invocation.operation_binding"),
        contract_check("capability_invocation.token_binding"),
    ],
    "capability-cancellation-request.schema.json": [
        contract_check("capability_invocation.operation_binding"),
        contract_check("capability_invocation.operation_binding"),
        implementation_check("conformance_test", "contracts/conformance/capability/v1/suite.json", "timeout-cancel-status"),
    ],
    "workspace-content-manifest.schema.json": [
        contract_check("workspace_manifest.digest"),
        contract_check("workspace_manifest.path_policy"),
        contract_check("workspace_manifest.counts"),
        contract_check("workspace_manifest.symlink_policy"),
    ],
    "runtime-session-request.schema.json": [
        contract_check("runtime_session.requested_scope_subset") + implementation_check("conformance_test", "contracts/conformance/runtime-gateway/v1/suite.json", "session-scope-enforced"),
        contract_check("runtime_session.sandbox_slot_binding") + implementation_check("conformance_test", "contracts/conformance/runtime-gateway/v1/suite.json", "slot-scoped-runtime-session"),
        contract_check("runtime_session.scope_class"),
        implementation_check("conformance_test", "contracts/conformance/runtime-gateway/v1/suite.json", "platform-managed-recording-authority"),
        contract_check("runtime_session.channel_policy"),
    ],
    "canonical-event-v2.schema.json": [
        implementation_check("ddl_responsibility", "docs/26_DATA_MODEL_INVARIANTS.md", "conversation_event_omits_work_scope"),
        contract_check("canonical_event.work_binding"),
        implementation_check("ddl_responsibility", "docs/26_DATA_MODEL_INVARIANTS.md", "aggregate_and_work_sequence_ledgers"),
        contract_check("canonical_event.source_dedupe"),
        implementation_check("ddl_responsibility", "docs/26_DATA_MODEL_INVARIANTS.md", "canonical_event_inbox_source_uniqueness"),
        contract_check("canonical_event.producer_binding"),
        contract_check("canonical_event.registry_binding"),
    ],
    "idempotency-record.schema.json": [
        implementation_check("ddl_responsibility", "docs/26_DATA_MODEL_INVARIANTS.md", "idempotency_scope_unique_index"),
        implementation_check("ddl_responsibility", "docs/26_DATA_MODEL_INVARIANTS.md", "idempotency_digest_conflict"),
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
    "runtime-authorization.schema.json": [
        contract_check("runtime_authorization.digest"),
        contract_check("runtime_authorization.lineage"),
        contract_check("runtime_authorization.ceiling"),
        contract_check("runtime_authorization.internal_binding"),
        contract_check("runtime_authorization.scope"),
        contract_check("runtime_authorization.expiry"),
        contract_check("runtime_authorization.artifact_coverage") + implementation_check("conformance_test", "contracts/conformance/runtime/v1/suite.json", "authorization-renewal"),
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
        contract_check("artifact_staging_grant.permissions") + implementation_check("conformance_test", "contracts/conformance/execution-gateway/v1/suite.json", "artifact-no-provider-finalize"),
    ],
    "artifact-gateway-token-claims.schema.json": [
        contract_check("artifact_gateway.token_binding"),
        contract_check("artifact_gateway.operation_binding"),
        contract_check("artifact_gateway.token_binding") + implementation_check("conformance_test", "contracts/conformance/execution-gateway/v1/suite.json", "artifact-operation-token-binding"),
    ],
    "artifact-staging-object-request.schema.json": [
        contract_check("artifact_gateway.operation_binding"),
        contract_check("artifact_gateway.operation_binding") + implementation_check("conformance_test", "contracts/conformance/execution-gateway/v1/suite.json", "artifact-staging-byte-digest"),
    ],
    "artifact-staging-commit-request.schema.json": [
        contract_check("artifact_gateway.operation_binding"),
        contract_check("artifact_gateway.operation_binding") + implementation_check("conformance_test", "contracts/conformance/execution-gateway/v1/suite.json", "artifact-staging-limits"),
        contract_check("artifact_staging_grant.permissions") + implementation_check("conformance_test", "contracts/conformance/execution-gateway/v1/suite.json", "artifact-no-provider-finalize"),
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
        implementation_check("conformance_test", "contracts/conformance/execution-gateway/v1/suite.json", "egress-address-revalidation"),
        implementation_check("conformance_test", "contracts/conformance/execution-gateway/v1/suite.json", "egress-header-and-body-limits"),
    ],
    "egress-invocation-token-claims.schema.json": [
        contract_check("egress_gateway.token_binding"),
        contract_check("egress_gateway.token_binding") + implementation_check("conformance_test", "contracts/conformance/execution-gateway/v1/suite.json", "egress-operation-token-binding"),
        contract_check("egress_gateway.request_binding") + implementation_check("conformance_test", "contracts/conformance/execution-gateway/v1/suite.json", "egress-registered-destination-only"),
    ],
    "capability-invocation-result.schema.json": [
        implementation_check("conformance_test", "contracts/conformance/capability/v1/suite.json", "request-schema-boundaries"),
        implementation_check("conformance_test", "contracts/conformance/capability/v1/suite.json", "artifact-contract"),
        contract_check("usage_observation.provider_boundary"),
    ],
    "usage-observation.schema.json": [
        contract_check("usage_observation.observation_identity"),
        contract_check("usage_observation.meter_and_evidence"),
        contract_check("usage_observation.incomplete_status"),
    ],
}
traceability_constraints = []
for schema_filename, constraint_enforcements in traceability_profiles.items():
    schema = read(f"contracts/schemas/{schema_filename}")
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
        read(f"contracts/schemas/{filename}")["$id"] for filename in traceability_profiles
    ],
    "constraints": traceability_constraints,
}
write("contracts/semantic-constraints-v1.json", traceability)
print("Refreshed v0.9.0 Provider, Scenario, Experience, execution, Recording and reconciliation digests.")
