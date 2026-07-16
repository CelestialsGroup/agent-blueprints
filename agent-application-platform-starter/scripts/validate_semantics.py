#!/usr/bin/env python3
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any

import rfc8785

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


def provider_snapshots(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        manifest["agent_runtime"]["provider_revision"],
        *[
            resolution["selected_provider_revision"]
            for resolution in manifest["capability_resolutions"]
        ],
        *[sandbox["provider_revision"] for sandbox in manifest["sandboxes"]],
    ]


def validate_run_manifest(manifest: dict[str, Any]) -> None:
    validate_self_digest(manifest, "run_manifest_digest")
    slots = [sandbox["sandbox_slot_key"] for sandbox in manifest["sandboxes"]]
    if len(slots) != len(set(slots)):
        raise AssertionError("sandbox_slot_key must be unique")
    if slots.count(manifest["primary_sandbox_slot_key"]) != 1:
        raise AssertionError("primary_sandbox_slot_key must reference exactly one Sandbox")

    capability_keys = [
        (
            item["capability"]["id"],
            item["capability"]["version"],
            item["capability"]["profile"],
        )
        for item in manifest["capability_resolutions"]
    ]
    if len(capability_keys) != len(set(capability_keys)):
        raise AssertionError("Capability resolution must be unique per exact capability/profile")

    by_revision: dict[str, dict[str, Any]] = {}
    for snapshot in provider_snapshots(manifest):
        if snapshot["admission_status"] != "certified":
            raise AssertionError("RunManifest may contain only certified ProviderRevision snapshots")
        revision_id = snapshot["provider_revision_id"]
        previous = by_revision.setdefault(revision_id, snapshot)
        if previous != snapshot:
            raise AssertionError(f"Conflicting snapshots for ProviderRevision {revision_id}")


def validate_attempt_sequence(attempts: list[dict[str, Any]]) -> None:
    previous_number = 0
    previous_fencing = 0
    seen_ids: set[str] = set()
    for attempt in attempts:
        if attempt["attempt_id"] in seen_ids:
            raise AssertionError("attempt_id_not_unique")
        seen_ids.add(attempt["attempt_id"])
        if attempt["attempt_number"] != previous_number + 1:
            raise AssertionError("attempt_number_not_contiguous")
        if attempt["fencing_token"] <= previous_fencing:
            raise AssertionError("fencing_token_not_monotonic")
        previous_number = attempt["attempt_number"]
        previous_fencing = attempt["fencing_token"]


def validate_state_machine(machine: dict[str, Any], allowed_states: set[str]) -> None:
    transitions = {
        (item["from"], item["event"], item["to"])
        for item in machine["transitions"]
    }
    if len(transitions) != len(machine["transitions"]):
        raise AssertionError("Duplicate state transition")
    used_states = {machine["initial_state"], *machine["terminal_states"]}
    for source, _, target in transitions:
        used_states.update((source, target))
    if not used_states.issubset(allowed_states):
        raise AssertionError(f"State machine uses undeclared aggregate states: {sorted(used_states - allowed_states)}")
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
    missing = set(machine["terminal_states"]) - reachable
    if missing:
        raise AssertionError(f"Unreachable terminal states: {sorted(missing)}")


provider_revision = load("examples/contracts/sandbox-provider-revision.json")
validate_self_digest(provider_revision, "provider_revision_digest")
admission = load("examples/contracts/provider-admission-decision.json")
validate_self_digest(admission, "decision_digest")
if admission["provider_revision_digest"] != provider_revision["provider_revision_digest"]:
    raise AssertionError("Admission decision does not bind the immutable ProviderRevision digest")
manual_review = load("examples/contracts/sandbox-manual-review-decision.json")
validate_self_digest(manual_review, "decision_digest")
validate_run_manifest(load("examples/contracts/run-manifest-v2.json"))
operation_record_schema = load("contracts/schemas/sandbox-operation-record.schema.json")
operation_states = set(operation_record_schema["properties"]["status"]["enum"])
validate_state_machine(load("contracts/state-machines/sandbox-operation-v2.json"), operation_states)

negative = load("contracts/tests/semantic-invalid/run-manifest-cases.json")
base_manifest = load(negative["base"])
for case in negative["cases"]:
    value = copy.deepcopy(base_manifest)
    mutation = case["mutation"]
    if mutation == "duplicate_sandbox_slot":
        duplicate = copy.deepcopy(value["sandboxes"][0])
        duplicate["sandbox_id"] = "sbx_duplicate"
        value["sandboxes"].append(duplicate)
        unsigned = copy.deepcopy(value)
        unsigned.pop("run_manifest_digest")
        value["run_manifest_digest"] = canonical_digest(unsigned)
    elif mutation == "missing_primary_slot":
        value["primary_sandbox_slot_key"] = "missing-slot"
        unsigned = copy.deepcopy(value)
        unsigned.pop("run_manifest_digest")
        value["run_manifest_digest"] = canonical_digest(unsigned)
    elif mutation == "wrong_run_manifest_digest":
        value["run_manifest_digest"] = "sha256:" + "0" * 64
    elif mutation == "conflicting_revision_snapshot":
        value["sandboxes"][0]["provider_revision"]["configuration_digest"] = (
            "sha256:" + "f" * 64
        )
        unsigned = copy.deepcopy(value)
        unsigned.pop("run_manifest_digest")
        value["run_manifest_digest"] = canonical_digest(unsigned)
    else:
        raise AssertionError(f"Unknown semantic fixture mutation: {mutation}")
    try:
        validate_run_manifest(value)
    except AssertionError:
        pass
    else:
        raise AssertionError(f"Expected semantic fixture to fail: {case['id']}")

attempt_fixture = load("contracts/tests/semantic-invalid/sandbox-attempt-sequence.json")
try:
    validate_attempt_sequence(attempt_fixture["attempts"])
except AssertionError as error:
    if str(error) != attempt_fixture["expected_error"]:
        raise
else:
    raise AssertionError("Expected invalid Sandbox attempt sequence to fail")

print("Semantic validation passed with 5 negative invariant fixtures.")
