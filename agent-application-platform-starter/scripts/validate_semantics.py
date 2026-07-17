#!/usr/bin/env python3
from __future__ import annotations

import copy
import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any

import rfc8785
from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource

ROOT = Path(__file__).resolve().parents[1]


SCHEMA_REGISTRY = Registry()
for schema_path in sorted((ROOT / "contracts/schemas").glob("*.json")):
    schema_value = json.loads(schema_path.read_text(encoding="utf-8"))
    SCHEMA_REGISTRY = SCHEMA_REGISTRY.with_resource(schema_value["$id"], Resource.from_contents(schema_value))


def load(relative: str) -> Any:
    return json.loads((ROOT / relative).read_text(encoding="utf-8"))


def canonical_digest(value: Any) -> str:
    return "sha256:" + hashlib.sha256(rfc8785.dumps(value)).hexdigest()


def validate_self_digest(value: dict[str, Any], field: str) -> None:
    unsigned = copy.deepcopy(value)
    expected = unsigned.pop(field)
    actual = canonical_digest(unsigned)
    if actual != expected:
        raise AssertionError(f"{field} mismatch: expected {actual}, got {expected}")


def snapshot_fields(revision: dict[str, Any], decision: dict[str, Any]) -> dict[str, Any]:
    result = {
        "provider_revision_id": revision["provider_revision_id"],
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
        "admission_decision_id": decision["decision_id"],
        "admission_decision_digest": decision["decision_digest"],
        "admission_status": "certified",
    }
    if "image_digest" in revision:
        result["image_digest"] = revision["image_digest"]
    return result


def provider_snapshot_bindings(manifest: dict[str, Any]) -> list[tuple[dict[str, Any], str]]:
    bindings = [(manifest["agent_runtime"]["provider_revision"], manifest["agent_runtime"]["provider_instance_id"])]
    bindings.extend((item["selected_provider_revision"], item["selected_provider_instance_id"]) for item in manifest["capability_resolutions"])
    bindings.extend((item["provider_revision"], item["provider_instance_id"]) for item in manifest["sandboxes"])
    bindings.extend((item["provider_revision"], item["provider_instance_id"]) for item in manifest["selected_experiences"])
    return bindings


def capability_key(value: dict[str, Any], id_field: str = "id") -> tuple[str, str, str | None]:
    return (value[id_field], value["version"], value.get("profile"))


def revision_supports(revision: dict[str, Any], key: tuple[str, str, str | None]) -> bool:
    return any((item["capability"], item["version"], item.get("profile")) == key and item["status"] == "passed" for item in revision["conformance"])


def validate_run_admission(manifest: dict[str, Any], context: dict[str, Any]) -> None:
    validate_self_digest(manifest, "run_manifest_digest")
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
    validate_self_digest(commercial, "authorization_digest")
    if commercial["authorized_limits_digest"] != canonical_digest(commercial["authorized_limits"]):
        raise AssertionError("Commercial authorization does not bind its explicit limits")
    if manifest["commercial_authorization_digest"] != commercial["authorization_digest"]:
        raise AssertionError("RunManifest does not bind the admitted CommercialAuthorizationSnapshot")
    required_items = [(item["id"], item["version"], item["profile"]) for item in context["required_capabilities"]]
    resolved_items = [(item["capability"]["id"], item["capability"]["version"], item["capability"]["profile"]) for item in manifest["capability_resolutions"]]
    required, resolved = set(required_items), set(resolved_items)
    if len(required_items) != len(required) or len(resolved_items) != len(resolved):
        raise AssertionError("Scenario requirements and CapabilityResolution entries must be unique by id/version/profile")
    if resolved != required:
        raise AssertionError(f"Capability resolution must exactly cover Scenario requirements: required={required}, resolved={resolved}")

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
        for legacy in ("sandbox_conformance_report_digest", "governed_conformance_report_digest"):
            if legacy in revision and revision[legacy] != expected_conformance_digest:
                raise AssertionError(f"Legacy {legacy} conflicts with generic conformance_set_digest")
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
        key = capability_key(resolution["capability"])
        definition = definitions.get(key)
        revision = revisions[resolution["selected_provider_revision"]["provider_revision_id"]]
        if definition is None or resolution["capability_definition_digest"] != definition["definition_digest"]:
            raise AssertionError(f"CapabilityResolution does not bind the admitted CapabilityDefinition: {key}")
        if revision["provider_kind"] not in definition["allowed_provider_kinds"]:
            raise AssertionError(f"Provider kind {revision['provider_kind']} is not allowed for {key}")
        if not revision_supports(revision, key):
            raise AssertionError(f"ProviderRevision conformance does not cover selected capability: {key}")

    runtime_revision = revisions[manifest["agent_runtime"]["provider_revision"]["provider_revision_id"]]
    if runtime_revision["provider_kind"] != "agent_runtime" or "agent_runtime" not in context["agent_runtime_capability"]["allowed_provider_kinds"]:
        raise AssertionError("RunManifest agent_runtime must bind an admitted Agent Runtime Provider")
    if not revision_supports(runtime_revision, runtime_key):
        raise AssertionError("Agent Runtime Provider conformance does not cover its governed execution capability")
    if manifest["agent_runtime"]["governed_conformance_report_digest"] != runtime_revision["conformance_set_digest"]:
        raise AssertionError("Agent Runtime outer conformance digest conflicts with the verified ProviderRevision")

    for sandbox in manifest["sandboxes"]:
        revision = revisions[sandbox["provider_revision"]["provider_revision_id"]]
        if revision["provider_kind"] != "sandbox":
            raise AssertionError("Sandbox slot must bind a Sandbox ProviderRevision")
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
    if slots.count(manifest["primary_sandbox_slot_key"]) != 1:
        raise AssertionError("primary_sandbox_slot_key must reference exactly one Sandbox")


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


def status_enum(schema_path: str) -> set[str]:
    return set(load(schema_path)["properties"]["status"]["enum"])


validate_state_machine(load("contracts/state-machines/work-order-v1.json"), status_enum("contracts/schemas/work-order-state.schema.json"))
validate_state_machine(load("contracts/state-machines/conversation-v1.json"), status_enum("contracts/schemas/conversation.schema.json"))
validate_state_machine(load("contracts/state-machines/agent-runtime-run-v1.json"), status_enum("contracts/schemas/agent-runtime-run-status.schema.json"))
validate_state_machine(load("contracts/state-machines/runtime-recording-v1.json"), status_enum("contracts/schemas/runtime-recording.schema.json"))
invocation_machine = load("contracts/state-machines/invocation-v2.json")
validate_state_machine(invocation_machine, status_enum("contracts/schemas/invocation-record.schema.json"))
if any(item["from"] in {"executing", "outcome_unknown", "reconciling", "manual_review"} and item["to"] == "cancelled" for item in invocation_machine["transitions"]):
    raise AssertionError("In-flight/unknown Invocation cannot transition directly to cancelled")
if any(item["event"] == "abandon" for item in invocation_machine["transitions"]):
    raise AssertionError("Invocation abandon must explicitly bind risk acceptance")
if any(item["event"] == "retryable_failure" for item in invocation_machine["transitions"]):
    raise AssertionError("Invocation retry transition must distinguish idempotent retry from approved non-idempotent retry")
sandbox_machine = load("contracts/state-machines/sandbox-operation-v2.json")
validate_state_machine(sandbox_machine, status_enum("contracts/schemas/sandbox-operation-record.schema.json"))
unsafe_direct_cancel = {"running", "reconciling", "manual_review_required"}
if any(item["from"] in unsafe_direct_cancel and item["to"] == "cancelled" for item in sandbox_machine["transitions"]):
    raise AssertionError("In-flight/unknown Sandbox operation cannot transition directly to cancelled")

nondeterministic = copy.deepcopy(invocation_machine)
nondeterministic["transitions"].append({"from": "prepared", "event": "dispatch", "to": "failed"})
try:
    validate_state_machine(nondeterministic, status_enum("contracts/schemas/invocation-record.schema.json"))
except AssertionError:
    pass
else:
    raise AssertionError("Expected non-deterministic state-machine fixture to fail")
orphaned = copy.deepcopy(invocation_machine)
orphaned["transitions"].append({"from": "orphaned", "event": "remain_orphaned", "to": "orphaned"})
try:
    validate_state_machine(orphaned, status_enum("contracts/schemas/invocation-record.schema.json") | {"orphaned"})
except AssertionError:
    pass
else:
    raise AssertionError("Expected unreachable non-terminal state fixture to fail")

context = load("examples/contracts/run-admission-context.json")
manifest = load("examples/contracts/run-manifest-v2.json")
validate_run_admission(manifest, context)
grant = load("examples/contracts/execution-grant-claims.json")
commercial = grant["commercial_authorization"]
validate_self_digest(commercial, "authorization_digest")
if commercial != context["commercial_authorization"]:
    raise AssertionError("ExecutionGrant and Run admission bind different CommercialAuthorizationSnapshots")
if not set(grant["capabilities"]) <= set(commercial["authorized_capabilities"]):
    raise AssertionError("ExecutionGrant capabilities exceed commercial authorization")
if any(name not in commercial["authorized_limits"] or value > commercial["authorized_limits"][name] for name, value in grant["limits"].items()):
    raise AssertionError("ExecutionGrant limits exceed commercial authorization")
manual = load("examples/contracts/sandbox-manual-review-decision.json")
validate_self_digest(manual, "decision_digest")
invocation_manual = load("examples/contracts/invocation-manual-review-decision.json")
validate_self_digest(invocation_manual, "decision_digest")

negative = load("contracts/tests/semantic-invalid/run-manifest-cases.json")
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
        value["sandboxes"][0]["provider_revision"]["configuration_digest"] = "sha256:" + "f" * 64
    elif mutation == "unadmitted_experience":
        value["selected_experiences"] = [{
            "selection": {
                "kind": "template",
                "catalog_entry_id": "unadmitted/template",
                "revision_id": "unadmitted-revision",
                "revision_digest": "sha256:" + "9" * 64,
                "capability_id": "template.html.generate",
            },
            "provider_instance_id": value["agent_runtime"]["provider_instance_id"],
            "provider_revision": copy.deepcopy(value["agent_runtime"]["provider_revision"]),
        }]
    elif mutation == "unauthorized_experience_entitlement":
        registry["commercial_authorization"]["authorized_entitlements"] = []
        registry["commercial_authorization"]["authorization_digest"] = canonical_digest({key: item for key, item in registry["commercial_authorization"].items() if key != "authorization_digest"})
        value["commercial_authorization_digest"] = registry["commercial_authorization"]["authorization_digest"]
    elif mutation == "missing_required_experience_tag":
        registry["experience_requirements"][0]["required_tags"] = ["nonexistent-tag"]
    elif mutation == "commercial_authorization_digest_mismatch":
        value["commercial_authorization_digest"] = "sha256:" + "7" * 64
    elif mutation == "scenario_definition_mismatch":
        registry["scenario_definition"]["id"] = "other-scenario"
        registry["scenario_definition"]["definition_digest"] = canonical_digest({key: item for key, item in registry["scenario_definition"].items() if key != "definition_digest"})
    else:
        raise AssertionError(f"Unknown mutation: {mutation}")
    if mutation != "wrong_run_manifest_digest":
        value["run_manifest_digest"] = canonical_digest({key: item for key, item in value.items() if key != "run_manifest_digest"})
    try:
        validate_run_admission(value, registry)
    except AssertionError:
        pass
    else:
        raise AssertionError(f"Expected semantic fixture to fail: {case['id']}")

admission_negative = load("contracts/tests/semantic-invalid/run-admission-cases.json")
for case in admission_negative["cases"]:
    value = copy.deepcopy(manifest)
    registry = copy.deepcopy(context)
    mutation = case["mutation"]
    if mutation == "forged_provider_revision_digest":
        value["agent_runtime"]["provider_revision"]["provider_revision_digest"] = "sha256:" + "f" * 64
    elif mutation == "extraneous_capability_resolution":
        extra = copy.deepcopy(value["capability_resolutions"][0]); extra["resolution_id"] = "res_extra"; extra["capability"] = {"id": "scenario.unrequested", "version": "1.0", "profile": None}; value["capability_resolutions"].append(extra)
    elif mutation == "forged_admission_decision_digest":
        value["sandboxes"][0]["provider_revision"]["admission_decision_digest"] = "sha256:" + "e" * 64
    elif mutation == "stale_admission_decision":
        previous = registry["admission_decisions"][0]
        revoked = {"decision_id": "pad_revoked_later", "provider_revision_id": previous["provider_revision_id"], "provider_revision_digest": previous["provider_revision_digest"], "decision_sequence": 2, "decision": "revoked", "reason": "Test revocation", "evidence_digest": "sha256:" + "9" * 64, "decided_by": "principal:test", "decided_at": "2026-07-16T09:30:00Z", "supersedes_decision_id": previous["decision_id"], "decision_digest": "sha256:" + "0" * 64}
        revoked["decision_digest"] = canonical_digest({key: item for key, item in revoked.items() if key != "decision_digest"}); registry["admission_decisions"].append(revoked)
    elif mutation == "forged_capability_definition_digest":
        value["capability_resolutions"][0]["capability_definition_digest"] = "sha256:" + "a" * 64
    elif mutation == "sandbox_unsupported_capability":
        value["sandboxes"][0]["required_capabilities"] = [{"id": "tool.echo", "version": "1.0", "profile": "default"}]
    elif mutation == "forged_agent_runtime_outer_conformance":
        value["agent_runtime"]["governed_conformance_report_digest"] = "sha256:" + "b" * 64
    elif mutation == "capability_incompatible_provider_kind":
        value["capability_resolutions"][1]["selected_provider_revision"] = copy.deepcopy(value["agent_runtime"]["provider_revision"])
        value["capability_resolutions"][1]["selected_provider_instance_id"] = value["agent_runtime"]["provider_instance_id"]
    elif mutation == "missing_admission_predecessor":
        previous = registry["admission_decisions"][0]
        forged = copy.deepcopy(previous)
        forged.update({"decision_id": "pad_sequence_gap", "decision_sequence": 3, "supersedes_decision_id": "pad_missing", "decided_at": "2026-07-16T09:30:00Z"})
        forged["decision_digest"] = canonical_digest({key: item for key, item in forged.items() if key != "decision_digest"})
        registry["admission_decisions"].append(forged)
    else:
        raise AssertionError(f"Unknown admission mutation: {mutation}")
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


operation_schema = load("contracts/schemas/sandbox-operation-record.schema.json")
manual_schema = load("contracts/schemas/sandbox-manual-review-decision.schema.json")
operation_validator = Draft202012Validator(operation_schema, registry=SCHEMA_REGISTRY, format_checker=FormatChecker())
manual_validator = Draft202012Validator(manual_schema, registry=SCHEMA_REGISTRY, format_checker=FormatChecker())
operation = load("examples/contracts/sandbox-operation.json")
reconciliation = load("examples/contracts/sandbox-reconciliation-case.json")
validate_case_decision_binding(operation, reconciliation, manual, record_id_field="operation_id", case_record_id_field="operation_id")
if operation["current_attempt_number"] > operation["max_attempts"]:
    raise AssertionError("current_attempt_number exceeds max_attempts")
sandbox_negative = load("contracts/tests/semantic-invalid/sandbox-operation-cases.json")
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

invocation_schema = load("contracts/schemas/invocation-record.schema.json")
invocation_manual_schema = load("contracts/schemas/invocation-manual-review-decision.schema.json")
invocation_validator = Draft202012Validator(invocation_schema, registry=SCHEMA_REGISTRY, format_checker=FormatChecker())
invocation_manual_validator = Draft202012Validator(invocation_manual_schema, registry=SCHEMA_REGISTRY, format_checker=FormatChecker())
invocation = load("examples/contracts/invocation-record.json")
invocation_reconciliation = load("examples/contracts/invocation-reconciliation-case.json")
validate_case_decision_binding(invocation, invocation_reconciliation, invocation_manual, record_id_field="invocation_id", case_record_id_field="invocation_id")
retry_invocation = load("examples/contracts/invocation-non-idempotent-retry.json")
retry_case = load("examples/contracts/invocation-retry-reconciliation-case.json")
retry_decision = load("examples/contracts/invocation-retry-manual-review-decision.json")
validate_case_decision_binding(retry_invocation, retry_case, retry_decision, record_id_field="invocation_id", case_record_id_field="invocation_id")
invocation_negative = load("contracts/tests/semantic-invalid/invocation-cases.json")
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


invocation_attempt_fixture = load("contracts/tests/semantic-invalid/invocation-attempt-sequence.json")
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

attempt_sequence = load("contracts/tests/semantic-invalid/sandbox-attempt-sequence.json")
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


conversation_fixture = load("contracts/tests/semantic-invalid/conversation-message-sequence.json")
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


recording_fixture = load("contracts/tests/semantic-invalid/runtime-recording-sequence.json")
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


runtime_command_fixture = load("contracts/tests/semantic-invalid/agent-runtime-command-sequence.json")
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


def validate_conversation_branch(
    branch: dict[str, Any], message: dict[str, Any], work_order: dict[str, Any],
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


branch_fixture = load("contracts/tests/semantic-invalid/conversation-branch-cases.json")
branch = load(branch_fixture["branch"])
branch_message = load(branch_fixture["message"])
branch_work_order = load(branch_fixture["work_order"])
validate_conversation_branch(branch, branch_message, branch_work_order)
for case in branch_fixture["cases"]:
    candidate_branch = copy.deepcopy(branch)
    candidate_message = copy.deepcopy(branch_message)
    candidate_work_order = copy.deepcopy(branch_work_order)
    if case["mutation"] == "zero_sequence_with_head":
        candidate_branch["head_message_sequence"] = 0
    elif case["mutation"] == "positive_sequence_without_head":
        candidate_branch["head_message_id"] = None
    elif case["mutation"] == "cross_conversation_message":
        candidate_message["conversation_id"] = "conv_other"
    elif case["mutation"] == "active_work_order_branch_mismatch":
        candidate_work_order["work"]["branch_id"] = "other-branch"
    else:
        raise AssertionError(f"Unknown ConversationBranch mutation: {case['mutation']}")
    try:
        validate_conversation_branch(candidate_branch, candidate_message, candidate_work_order)
    except AssertionError:
        pass
    else:
        raise AssertionError(f"Expected ConversationBranch semantic fixture to fail: {case['id']}")


print("Semantic validation passed with deterministic state-machine/safety checks and 60 negative invariant fixtures.")
