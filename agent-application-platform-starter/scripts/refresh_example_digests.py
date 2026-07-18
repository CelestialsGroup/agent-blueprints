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


suite_paths = {
    "agent_runtime": "contracts/conformance/runtime/v1/suite.json",
    "sandbox": "contracts/conformance/sandbox/v1/suite.json",
    "runtime_gateway": "contracts/conformance/runtime-gateway/v1/suite.json",
    "capability_provider": "contracts/conformance/capability/v1/suite.json",
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
        }.get(revision["provider_kind"], "contracts/openapi/plugin-invocation-v1.yaml")
        revision["port"] = {
            "protocol": protocol,
            "protocol_version": "v1",
            "contract_digest": file_digest(contract_path),
            "binding_digest": legacy_binding_digest or digest({"binding": revision["provider_revision_id"]}),
        }
    contract_path = {
        "agent_runtime": "contracts/openapi/agent-runtime-provider-v1.yaml",
        "sandbox": "contracts/openapi/sandbox-provider-v1.yaml",
    }.get(revision["provider_kind"], "contracts/openapi/plugin-invocation-v1.yaml")
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


def resolution(
    resolution_id: str, capability: dict[str, Any], revision_id: str,
    decision_id: str, resolved_at: str,
) -> dict[str, Any]:
    revision = revisions[revision_id]
    resolution_input = {
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
        "capability": capability,
        "selected_provider_instance_id": revision["provider_instance_id"],
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
grant["request_contract_id"] = "urn:agent-platform:conversation-turn-request:v1"
grant["request_digest_profile"] = "rfc8785-request-excluding-execution-grant-v1"
commercial_path = "examples/contracts/commercial-authorization-snapshot.json"
commercial = read(commercial_path)
commercial["commercial_authorization_id"] = commercial.pop(
    "authorization_id", commercial.get("commercial_authorization_id")
)
commercial.pop("authorization_digest", None)
commercial["authorized_entitlements"] = ["experience.html.premium"]
commercial["authorized_capabilities"] = grant["capabilities"]
commercial["authorized_limits"] = grant["limits"]
commercial["authorized_limits_digest"] = digest(commercial["authorized_limits"])
commercial["commercial_authorization_digest"] = digest_without(commercial, "commercial_authorization_digest")
write(commercial_path, commercial)
grant["commercial_authorization"] = commercial
write(grant_path, grant)

workspace_revision_path = "examples/contracts/workspace-revision.json"
workspace_revision = read(workspace_revision_path)
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
sandbox_spec["workspace"]["base_branch_version"] = conversation_branch["branch_version"]
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
sandbox_restore["spec"]["workspace"]["base_branch_version"] = conversation_branch["branch_version"]
sandbox_restore["spec"]["workspace"]["commit_mode"] = "cas_new_revision"
sandbox_restore["request_digest"] = digest_without(sandbox_restore, "request_digest")
write("examples/contracts/sandbox-restore-request.json", sandbox_restore)
work_session = read("examples/contracts/work-session-request.json")
work_session["commercial_authorization"] = commercial
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
policy["decision_digest"] = digest_without(policy, "decision_digest")
write(policy_path, policy)

event_data_schema = read("contracts/schemas/agent-runtime-event-data.schema.json")
event_registry_path = "contracts/event-types/agent-runtime-core-v1.json"
event_registry = read(event_registry_path)
event_dependencies = sorted(
    [
        read("contracts/schemas/capability-error.schema.json"),
        read("contracts/schemas/technical-usage-entry.schema.json"),
    ],
    key=lambda schema: schema["$id"],
)
event_data_digest = digest({"root": event_data_schema, "dependencies": event_dependencies})
for definition in event_registry["definitions"]:
    definition["data_schema"]["digest"] = event_data_digest
    definition["data_schema"]["digest_profile"] = "rfc8785-schema-closure-v1"
event_registry["registry_digest"] = digest_without(event_registry, "registry_digest")
write(event_registry_path, event_registry)


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
}
manifest["execution_budget"] = {
    "budget_id": budget["budget_id"],
    "budget_digest": budget["budget_digest"],
}
manifest["policy_decision"] = {
    "decision_id": policy["decision_id"],
    "decision_digest": policy["decision_digest"],
}
manifest["event_registry"] = {
    "registry_id": event_registry["registry_id"],
    "registry_version": event_registry["registry_version"],
    "registry_digest": event_registry["registry_digest"],
}
manifest["conversation"]["workspace_revision_id"] = workspace_revision["workspace_revision_id"]
manifest["conversation"]["workspace_revision_digest"] = workspace_revision["revision_digest"]
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
grant["request_contract_id"] = "urn:agent-platform:conversation-turn-request:v1"
grant["request_digest_profile"] = "rfc8785-request-excluding-execution-grant-v1"
grant["request_digest"] = digest_without(conversation_turn_request, "execution_grant")
write(grant_path, grant)

work_order_grant = copy.deepcopy(grant)
work_order_grant["jti"] = "grant_work_order_01J0000000000000000"
work_order_grant["nonce"] = "nonce-work-order-0123456789"
work_order_grant["request_contract_id"] = "urn:agent-platform:work-order-request:v1"
work_order_grant["request_digest"] = digest_without(read("examples/contracts/work-order.json"), "execution_grant")
write("examples/contracts/execution-grant-work-order-claims.json", work_order_grant)

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
runtime_start["request_digest"] = digest_without(runtime_start, "request_digest")
write("examples/contracts/agent-runtime-start-request.json", runtime_start)

no_sandbox_runtime_start = copy.deepcopy(runtime_start)
no_sandbox_runtime_start["run_manifest_digest"] = no_sandbox_manifest["run_manifest_digest"]
no_sandbox_runtime_start["sandbox_bindings"] = []
no_sandbox_runtime_start["request_digest"] = digest_without(no_sandbox_runtime_start, "request_digest")
write("examples/contracts/agent-runtime-start-no-sandbox.json", no_sandbox_runtime_start)

runtime_status = read("examples/contracts/agent-runtime-run-status.json")
runtime_status["tenant_id"] = manifest["tenant_id"]
runtime_status["workflow_run_id"] = manifest["workflow_run_id"]
runtime_status["agent_run_id"] = manifest["agent_run_id"]
write("examples/contracts/agent-runtime-run-status.json", runtime_status)

runtime_command = read("examples/contracts/agent-runtime-command.json")
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
    "request_digest": runtime_start["request_digest"],
    "invocation_id": runtime_start["invocation_id"],
    "invocation_attempt_id": runtime_start["invocation_attempt_id"],
    "fencing_token": runtime_start["fencing_token"],
    "policy_decision_digest": policy["decision_digest"],
    "execution_budget_digest": budget["budget_digest"],
    "effective_permissions_digest": policy["effective_permissions_digest"],
})
write("examples/contracts/agent-runtime-invocation-token-claims.json", runtime_token)

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
        "contract_digest": file_digest("contracts/openapi/plugin-invocation-v1.yaml"),
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
print("Refreshed v0.9.0 Provider, Scenario, Experience, execution, Recording and reconciliation digests.")
