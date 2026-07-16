#!/usr/bin/env python3
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any

import rfc8785

ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / "contracts/compatibility/v0.8.1-contract-manifest.json"


def digest_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
unsigned = copy.deepcopy(manifest)
expected_manifest_digest = unsigned.pop("manifest_digest")
actual_manifest_digest = digest_bytes(rfc8785.dumps(unsigned))
if actual_manifest_digest != expected_manifest_digest:
    raise AssertionError(
        f"Contract manifest self-digest mismatch: "
        f"{actual_manifest_digest} != {expected_manifest_digest}"
    )

for resource in manifest["resources"]:
    path = ROOT / resource["path"]
    if not path.exists():
        raise AssertionError(f"Missing manifest resource: {resource['path']}")
    if resource["kind"] == "json-schema":
        value: Any = json.loads(path.read_text(encoding="utf-8"))
        actual = digest_bytes(rfc8785.dumps(value))
        if value.get("$id") != resource["id"]:
            raise AssertionError(f"Schema ID changed: {resource['path']}")
    else:
        actual = digest_bytes(path.read_bytes())
    if actual != resource["digest"]:
        raise AssertionError(
            f"Contract resource changed without manifest update: "
            f"{resource['path']}: {actual} != {resource['digest']}"
        )

print(
    f"Verified immutable contract manifest with {len(manifest['resources'])} resources."
)
