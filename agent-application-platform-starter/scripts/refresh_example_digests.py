#!/usr/bin/env python3
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any

import rfc8785

ROOT = Path(__file__).resolve().parents[1]


def read(relative: str) -> dict[str, Any]:
    return json.loads((ROOT / relative).read_text(encoding="utf-8"))


def write(relative: str, value: dict[str, Any]) -> None:
    (ROOT / relative).write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def digest_without(value: dict[str, Any], field: str) -> str:
    unsigned = copy.deepcopy(value)
    unsigned.pop(field, None)
    return "sha256:" + hashlib.sha256(rfc8785.dumps(unsigned)).hexdigest()


revision_paths = [
    "examples/contracts/sandbox-provider-revision.json",
    "examples/contracts/agent-runtime-provider-revision.json",
    "examples/contracts/tool-provider-revision.json",
]
decision_paths = [
    "examples/contracts/provider-admission-decision.json",
    "examples/contracts/agent-runtime-admission-decision.json",
    "examples/contracts/tool-provider-admission-decision.json",
]
revisions: dict[str, dict[str, Any]] = {}
for path in revision_paths:
    revision = read(path)
    revision["conformance_set_digest"] = "sha256:" + hashlib.sha256(rfc8785.dumps(revision["conformance"])).hexdigest()
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


manifest_path = "examples/contracts/run-manifest-v2.json"
manifest = read(manifest_path)
for resolution in manifest["capability_resolutions"]:
    current = resolution["selected_provider_revision"]
    resolution["selected_provider_revision"] = snapshot(current["provider_revision_id"], current["admission_decision_id"])
    resolution["selected_provider_instance_id"] = revisions[current["provider_revision_id"]]["provider_instance_id"]
runtime_current = manifest["agent_runtime"]["provider_revision"]
manifest["agent_runtime"]["provider_revision"] = snapshot(runtime_current["provider_revision_id"], runtime_current["admission_decision_id"])
manifest["agent_runtime"]["provider_instance_id"] = revisions[runtime_current["provider_revision_id"]]["provider_instance_id"]
manifest["agent_runtime"]["governed_conformance_report_digest"] = revisions[runtime_current["provider_revision_id"]]["conformance_set_digest"]
for sandbox in manifest["sandboxes"]:
    current = sandbox["provider_revision"]
    sandbox["provider_revision"] = snapshot(current["provider_revision_id"], current["admission_decision_id"])
    sandbox["provider_instance_id"] = revisions[current["provider_revision_id"]]["provider_instance_id"]
manifest["run_manifest_digest"] = digest_without(manifest, "run_manifest_digest")
write(manifest_path, manifest)

context_path = "examples/contracts/run-admission-context.json"
context = read(context_path)
context["provider_revisions"] = list(revisions.values())
context["admission_decisions"] = list(decisions.values())
write(context_path, context)

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
print("Refreshed v0.8.6 Provider, admission, RunManifest, reconciliation-case and manual-review digests.")
