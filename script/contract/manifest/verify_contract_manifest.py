#!/usr/bin/env python3
from __future__ import annotations

import copy
import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any

import rfc8785

SCRIPT_ROOT = Path(__file__).resolve().parents[2]
CONTRACT_ROOT = Path(
    os.environ.get("AGENT_CONTRACT_ROOT", SCRIPT_ROOT.parent / "contract")
).resolve()
MANIFEST = CONTRACT_ROOT / "compatibility/contract-manifest.json"


def sha(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def inventory() -> list[dict[str, Any]]:
    paths = [
        *sorted((CONTRACT_ROOT / "schemas").glob("*.json")),
        *sorted((CONTRACT_ROOT / "examples/schemas").glob("*.json")),
        *sorted((CONTRACT_ROOT / "openapi").glob("*.yaml")),
        *sorted((CONTRACT_ROOT / "state-machines").glob("*.json")),
        *sorted((CONTRACT_ROOT / "event-types").rglob("*.json")),
        *sorted((CONTRACT_ROOT / "conformance").rglob("*.json")),
        *sorted((CONTRACT_ROOT / "testdata").rglob("*")),
    ]
    result: list[dict[str, Any]] = []
    for path in paths:
        if not path.is_file():
            continue
        relative = path.relative_to(CONTRACT_ROOT).as_posix()
        if path.name.endswith(".schema.json"):
            value = json.loads(path.read_text(encoding="utf-8"))
            result.append({"path": relative, "kind": "json-schema", "id": value["$id"], "digest": sha(rfc8785.dumps(value))})
        elif relative.startswith("openapi/"):
            result.append({"path": relative, "kind": "openapi", "id": relative, "digest": sha(path.read_bytes())})
        elif relative.startswith("state-machines/"):
            result.append({"path": relative, "kind": "state-machine", "id": relative, "digest": sha(path.read_bytes())})
        else:
            result.append({"path": relative, "kind": "governance", "id": relative, "digest": sha(path.read_bytes())})
    return sorted(result, key=lambda item: item["path"])


resources = inventory()
resources_digest = sha(rfc8785.dumps(resources))
if "--print-values" in sys.argv:
    print(json.dumps({"resource_count": len(resources), "resources_digest": resources_digest}))
    raise SystemExit(0)
if "--refresh" in sys.argv:
    manifest = {
        "contract_line": "agent",
        "status": "candidate-not-frozen",
        "digest_profile": "RFC8785-JCS+SHA-256; Strict-I-JSON-v2.0",
        "resource_count": len(resources),
        "resources_digest": resources_digest,
        "resources": resources,
    }
    manifest["manifest_digest"] = sha(rfc8785.dumps(manifest))
    MANIFEST.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
if manifest["resource_count"] != len(resources) or manifest["resources_digest"] != resources_digest:
    raise AssertionError("Contract inventory changed without manifest refresh")
unsigned = copy.deepcopy(manifest)
expected = unsigned.pop("manifest_digest")
actual = sha(rfc8785.dumps(unsigned))
if actual != expected:
    raise AssertionError(f"Manifest self-digest mismatch: {actual} != {expected}")
print(f"Verified contract manifest over {len(resources)} governed resources.")
