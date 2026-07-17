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
    revision["conformance_set_digest"] = digest(revision["conformance"])
    if revision["provider_kind"] == "sandbox" and "sandbox_conformance_report_digest" in revision:
        revision["sandbox_conformance_report_digest"] = revision["conformance_set_digest"]
    if revision["provider_kind"] == "agent_runtime" and "governed_conformance_report_digest" in revision:
        revision["governed_conformance_report_digest"] = revision["conformance_set_digest"]
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
        "plugin_id": revision["plugin_id"],
        "plugin_version": revision["plugin_version"],
        "manifest_digest": revision["manifest_digest"],
        "package_digest": revision["package_digest"],
        "runtime_binding_digest": revision["runtime_binding_digest"],
        "configuration_digest": revision["configuration_digest"],
        "approved_permissions_digest": revision["approved_permissions_digest"],
        "credential_binding_digest": revision["credential_binding_digest"],
        "conformance_report_digest": revision["conformance_set_digest"],
        "admission_decision_id": decision_id,
        "admission_decision_digest": decision["decision_digest"],
        "admission_status": "certified",
    }
    if "image_digest" in revision:
        result["image_digest"] = revision["image_digest"]
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
    return {
        "resolution_id": resolution_id,
        "capability": capability,
        "selected_provider_instance_id": revision["provider_instance_id"],
        "routing_reason": "scenario_requirement",
        "candidates_considered": [revision["provider_instance_id"]],
        "resolved_at": resolved_at,
        "capability_definition_digest": definition_by_capability[capability["id"]]["definition_digest"],
        "selected_provider_revision": snapshot(revision_id, decision_id),
    }


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
commercial_path = "examples/contracts/commercial-authorization-snapshot.json"
commercial = read(commercial_path)
commercial["authorized_entitlements"] = ["experience.html.premium"]
commercial["authorized_capabilities"] = grant["capabilities"]
commercial["authorized_limits"] = grant["limits"]
commercial["authorized_limits_digest"] = digest(commercial["authorized_limits"])
commercial["authorization_digest"] = digest_without(commercial, "authorization_digest")
write(commercial_path, commercial)
grant["commercial_authorization"] = commercial
write(grant_path, grant)
work_session = read("examples/contracts/work-session-request.json")
work_session["commercial_authorization"] = commercial
write("examples/contracts/work-session-request.json", work_session)


manifest_path = "examples/contracts/run-manifest-v2.json"
manifest = read(manifest_path)
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
]
runtime_current = manifest["agent_runtime"]["provider_revision"]
manifest["agent_runtime"]["provider_revision"] = snapshot(runtime_current["provider_revision_id"], runtime_current["admission_decision_id"])
manifest["agent_runtime"]["provider_instance_id"] = revisions[runtime_current["provider_revision_id"]]["provider_instance_id"]
manifest["agent_runtime"]["governed_conformance_report_digest"] = revisions[runtime_current["provider_revision_id"]]["conformance_set_digest"]
for sandbox in manifest["sandboxes"]:
    current = sandbox["provider_revision"]
    sandbox["provider_revision"] = snapshot(current["provider_revision_id"], current["admission_decision_id"])
    sandbox["provider_instance_id"] = revisions[current["provider_revision_id"]]["provider_instance_id"]
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
manifest["commercial_authorization_digest"] = commercial["authorization_digest"]
manifest["run_manifest_digest"] = digest_without(manifest, "run_manifest_digest")
write(manifest_path, manifest)

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
runtime_start["run_manifest_digest"] = manifest["run_manifest_digest"]
write("examples/contracts/agent-runtime-start-request.json", runtime_start)

ui_extension_path = "examples/contracts/ui-extension-manifest.json"
ui_extension = read(ui_extension_path)
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
print("Refreshed v0.9.0 Provider, Scenario, Experience, RunManifest, Recording and reconciliation digests.")
