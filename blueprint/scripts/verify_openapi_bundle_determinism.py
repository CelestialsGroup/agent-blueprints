#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / "build"


def bundle() -> dict[str, str]:
    subprocess.run(
        ["corepack", "pnpm", "run", "bundle:openapi"], cwd=ROOT, check=True,
    )
    paths = sorted(BUILD.glob("*.bundle.yaml"))
    if not paths:
        raise AssertionError("OpenAPI bundle command produced no bundles")
    return {
        path.name: "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
        for path in paths
    }


first = bundle()
second = bundle()
if first != second:
    raise AssertionError("OpenAPI bundles differ between consecutive builds")

evidence_dir = BUILD / "validation"
evidence_dir.mkdir(parents=True, exist_ok=True)
(evidence_dir / "bundles.json").write_text(json.dumps({
    "bundle_count": len(second),
    "deterministic": True,
    "digests": second,
}, indent=2) + "\n", encoding="utf-8")
print(f"Verified {len(second)} OpenAPI bundles are byte-for-byte deterministic.")
