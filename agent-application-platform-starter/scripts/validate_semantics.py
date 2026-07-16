#!/usr/bin/env python3
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any

import rfc8785
from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parents[1]


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
    report_field = "sandbox_conformance_report_digest" if revision["provider_kind"] == "sandbox" else "governed_conformance_report_digest"
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
        "conformance_report_digest": revision[report_field],
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
    return bindings


def validate_run_admission(manifest: dict[str, Any], context: dict[str, Any]) -> None:
    validate_self_digest(manifest, "run_manifest_digest")
    if manifest["scenario"] != context["scenario"]:
        raise AssertionError("RunManifest scenario does not bind the admitted Scenario definition")
    required_items = [(item["id"], item["version"], item["profile"]) for item in context["required_capabilities"]]
    resolved_items = [(item["capability"]["id"], item["capability"]["version"], item["capability"]["profile"]) for item in manifest["capability_resolutions"]]
    required, resolved = set(required_items), set(resolved_items)
    if len(required_items) != len(required) or len(resolved_items) != len(resolved):
        raise AssertionError("Scenario requirements and CapabilityResolution entries must be unique by id/version/profile")
    if resolved != required:
        raise AssertionError(f"Capability resolution must exactly cover Scenario requirements: required={required}, resolved={resolved}")

    revisions: dict[str, dict[str, Any]] = {}
    for revision in context["provider_revisions"]:
        validate_self_digest(revision, "provider_revision_digest")
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

    slots = [sandbox["sandbox_slot_key"] for sandbox in manifest["sandboxes"]]
    if len(slots) != len(set(slots)):
        raise AssertionError("sandbox_slot_key must be unique")
    if slots.count(manifest["primary_sandbox_slot_key"]) != 1:
        raise AssertionError("primary_sandbox_slot_key must reference exactly one Sandbox")


def validate_state_machine(machine: dict[str, Any], allowed_states: set[str]) -> None:
    transitions = {(item["from"], item["event"], item["to"]) for item in machine["transitions"]}
    if len(transitions) != len(machine["transitions"]):
        raise AssertionError("Duplicate state transition")
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
    if terminal - reachable:
        raise AssertionError(f"Unreachable terminal states: {terminal-reachable}")


def status_enum(schema_path: str) -> set[str]:
    return set(load(schema_path)["properties"]["status"]["enum"])


validate_state_machine(load("contracts/state-machines/work-order-v1.json"), status_enum("contracts/schemas/work-order-state.schema.json"))
validate_state_machine(load("contracts/state-machines/invocation-v1.json"), status_enum("contracts/schemas/invocation-record.schema.json"))
sandbox_machine = load("contracts/state-machines/sandbox-operation-v2.json")
validate_state_machine(sandbox_machine, status_enum("contracts/schemas/sandbox-operation-record.schema.json"))
unsafe_direct_cancel = {"running", "reconciling", "manual_review_required"}
if any(item["from"] in unsafe_direct_cancel and item["to"] == "cancelled" for item in sandbox_machine["transitions"]):
    raise AssertionError("In-flight/unknown Sandbox operation cannot transition directly to cancelled")

context = load("examples/contracts/run-admission-context.json")
manifest = load("examples/contracts/run-manifest-v2.json")
validate_run_admission(manifest, context)
manual = load("examples/contracts/sandbox-manual-review-decision.json")
validate_self_digest(manual, "decision_digest")

negative = load("contracts/tests/semantic-invalid/run-manifest-cases.json")
for case in negative["cases"]:
    value = copy.deepcopy(manifest)
    mutation = case["mutation"]
    if mutation == "duplicate_sandbox_slot":
        duplicate = copy.deepcopy(value["sandboxes"][0]); duplicate["sandbox_id"] = "sbx_duplicate"; value["sandboxes"].append(duplicate)
    elif mutation == "missing_primary_slot":
        value["primary_sandbox_slot_key"] = "missing-slot"
    elif mutation == "wrong_run_manifest_digest":
        value["run_manifest_digest"] = "sha256:" + "0" * 64
    elif mutation == "conflicting_revision_snapshot":
        value["sandboxes"][0]["provider_revision"]["configuration_digest"] = "sha256:" + "f" * 64
    else:
        raise AssertionError(f"Unknown mutation: {mutation}")
    if mutation != "wrong_run_manifest_digest":
        value["run_manifest_digest"] = canonical_digest({key: item for key, item in value.items() if key != "run_manifest_digest"})
    try:
        validate_run_admission(value, context)
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
    else:
        raise AssertionError(f"Unknown admission mutation: {mutation}")
    value["run_manifest_digest"] = canonical_digest({key: item for key, item in value.items() if key != "run_manifest_digest"})
    try:
        validate_run_admission(value, registry)
    except AssertionError:
        pass
    else:
        raise AssertionError(f"Expected admission fixture to fail: {case['id']}")

operation_schema = load("contracts/schemas/sandbox-operation-record.schema.json")
manual_schema = load("contracts/schemas/sandbox-manual-review-decision.schema.json")
operation_validator = Draft202012Validator(operation_schema, format_checker=FormatChecker())
manual_validator = Draft202012Validator(manual_schema, format_checker=FormatChecker())
operation = load("examples/contracts/sandbox-operation.json")
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
    else:
        raise AssertionError(f"Unknown Sandbox mutation: {case['mutation']}")
    if not failed:
        raise AssertionError(f"Expected Sandbox semantic fixture to fail: {case['id']}")

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

print("Semantic validation passed with 4 state-machine checks and 12 negative invariant fixtures.")
