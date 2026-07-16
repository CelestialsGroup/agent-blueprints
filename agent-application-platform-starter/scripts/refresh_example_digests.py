#!/usr/bin/env python3
"""Refresh self-digests and immutable bindings in governed examples."""
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
    (ROOT / relative).write_text(
        json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


def self_digest(value: dict[str, Any], field: str) -> str:
    unsigned = copy.deepcopy(value)
    unsigned.pop(field, None)
    return "sha256:" + hashlib.sha256(rfc8785.dumps(unsigned)).hexdigest()


revision_path = "examples/contracts/sandbox-provider-revision.json"
revision = read(revision_path)
revision["provider_revision_digest"] = self_digest(revision, "provider_revision_digest")
write(revision_path, revision)

admission_path = "examples/contracts/provider-admission-decision.json"
admission = read(admission_path)
admission["provider_revision_digest"] = revision["provider_revision_digest"]
admission["decision_digest"] = self_digest(admission, "decision_digest")
write(admission_path, admission)

manual_path = "examples/contracts/sandbox-manual-review-decision.json"
manual = read(manual_path)
manual["decision_digest"] = self_digest(manual, "decision_digest")
write(manual_path, manual)

manifest_path = "examples/contracts/run-manifest-v2.json"
manifest = read(manifest_path)
for snapshot in [
    *[item["selected_provider_revision"] for item in manifest["capability_resolutions"]],
    *[item["provider_revision"] for item in manifest["sandboxes"]],
]:
    if snapshot["provider_revision_id"] == revision["provider_revision_id"]:
        snapshot["provider_revision_digest"] = revision["provider_revision_digest"]
        snapshot["admission_decision_digest"] = admission["decision_digest"]
manifest["run_manifest_digest"] = self_digest(manifest, "run_manifest_digest")
write(manifest_path, manifest)

print("Refreshed ProviderRevision, admission, manual-review, and RunManifest digests.")
