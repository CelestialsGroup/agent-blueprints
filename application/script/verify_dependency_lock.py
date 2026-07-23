#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
BLUEPRINT_ROOT = Path(
    os.environ.get("AGENT_BLUEPRINT_ROOT", ROOT.parent / "blueprint")
).resolve()
CONTRACT_ROOT = Path(
    os.environ.get("AGENT_CONTRACT_ROOT", ROOT.parent / "contract")
).resolve()
LOCK_PATH = ROOT / "dependency-lock.json"
SHA256 = re.compile(r"^[0-9a-f]{64}$")
SHA256_URI = re.compile(r"^sha256:[0-9a-f]{64}$")


def governed_snapshot(root: Path, suffixes: set[str]) -> tuple[str, int]:
    paths = sorted(
        (path for path in root.rglob("*") if path.is_file() and path.suffix in suffixes),
        key=lambda path: path.relative_to(root).as_posix(),
    )
    if not paths:
        raise AssertionError(f"No governed source files found under {root}")

    digest = hashlib.sha256()
    for path in paths:
        if path.is_symlink():
            raise AssertionError(f"Governed source must not be a symlink: {path}")
        relative = path.relative_to(root).as_posix().encode("utf-8")
        content = path.read_bytes()
        digest.update(len(relative).to_bytes(8, "big"))
        digest.update(relative)
        digest.update(len(content).to_bytes(8, "big"))
        digest.update(content)
    return digest.hexdigest(), len(paths)


def expected_lock() -> dict[str, Any]:
    blueprint_digest, blueprint_count = governed_snapshot(BLUEPRINT_ROOT, {".md"})
    contract_digest, contract_count = governed_snapshot(
        CONTRACT_ROOT, {".json", ".md", ".yaml", ".yml"}
    )

    manifest = json.loads(
        (CONTRACT_ROOT / "compatibility/contract-manifest.json").read_text(encoding="utf-8")
    )
    runtime_suite_path = CONTRACT_ROOT / "conformance/runtime/v1/suite.json"
    runtime_suite = json.loads(runtime_suite_path.read_text(encoding="utf-8"))

    return {
        "schema_version": 1,
        "blueprint": {
            "revision_kind": "governed_source_snapshot_sha256",
            "source_revision": blueprint_digest,
            "source_tree_digest": f"sha256:{blueprint_digest}",
            "governed_file_count": blueprint_count,
        },
        "contract": {
            "revision_kind": "governed_source_snapshot_sha256",
            "source_revision": contract_digest,
            "source_tree_digest": f"sha256:{contract_digest}",
            "governed_file_count": contract_count,
            "manifest_digest": manifest["manifest_digest"],
            "resource_count": manifest["resource_count"],
            "suites": [
                {
                    "path": "conformance/runtime/v1/suite.json",
                    "suite_id": runtime_suite["suite_id"],
                    "suite_version": runtime_suite["suite_version"],
                    "suite_digest": runtime_suite["suite_digest"],
                    "profiles": ["runtime-core-v1"],
                }
            ],
        },
    }


def validate_shape(lock: dict[str, Any]) -> None:
    if set(lock) != {"schema_version", "blueprint", "contract"} or lock["schema_version"] != 1:
        raise AssertionError("Dependency lock root shape is invalid")

    source_keys = {
        "revision_kind",
        "source_revision",
        "source_tree_digest",
        "governed_file_count",
    }
    if set(lock["blueprint"]) != source_keys:
        raise AssertionError("Blueprint lock shape is invalid")
    if set(lock["contract"]) != source_keys | {"manifest_digest", "resource_count", "suites"}:
        raise AssertionError("Contract lock shape is invalid")

    for name in ("blueprint", "contract"):
        source = lock[name]
        if source["revision_kind"] != "governed_source_snapshot_sha256":
            raise AssertionError(f"{name} revision kind is unsupported")
        if not SHA256.fullmatch(source["source_revision"]):
            raise AssertionError(f"{name} source revision is not SHA-256")
        if source["source_tree_digest"] != f"sha256:{source['source_revision']}":
            raise AssertionError(f"{name} source revision and tree digest differ")
        if not isinstance(source["governed_file_count"], int) or source["governed_file_count"] <= 0:
            raise AssertionError(f"{name} governed file count is invalid")

    contract = lock["contract"]
    if not SHA256_URI.fullmatch(contract["manifest_digest"]):
        raise AssertionError("Contract Manifest digest is invalid")
    if not isinstance(contract["resource_count"], int) or contract["resource_count"] <= 0:
        raise AssertionError("Contract resource count is invalid")
    if not isinstance(contract["suites"], list) or not contract["suites"]:
        raise AssertionError("At least one consumed Conformance Suite is required")

    suite_keys = {"path", "suite_id", "suite_version", "suite_digest", "profiles"}
    for suite in contract["suites"]:
        if set(suite) != suite_keys:
            raise AssertionError("Conformance Suite lock shape is invalid")
        if not SHA256_URI.fullmatch(suite["suite_digest"]):
            raise AssertionError("Conformance Suite digest is invalid")
        if not suite["profiles"] or len(suite["profiles"]) != len(set(suite["profiles"])):
            raise AssertionError("Conformance Suite profiles must be non-empty and unique")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--refresh", action="store_true")
    args = parser.parse_args()

    expected = expected_lock()
    if args.refresh:
        LOCK_PATH.write_text(
            json.dumps(expected, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    if not LOCK_PATH.is_file():
        raise AssertionError("dependency-lock.json is missing; use --refresh after reviewing inputs")
    actual = json.loads(LOCK_PATH.read_text(encoding="utf-8"))
    validate_shape(actual)
    if actual != expected:
        raise AssertionError(
            "Blueprint or Contract differs from dependency-lock.json; review the upstream change and refresh explicitly"
        )

    print(
        "Verified immutable upstream lock: "
        f"Blueprint {actual['blueprint']['source_tree_digest']}, "
        f"Contract {actual['contract']['source_tree_digest']}, "
        f"Manifest {actual['contract']['manifest_digest']}, "
        f"{len(actual['contract']['suites'])} consumed suite(s)."
    )


if __name__ == "__main__":
    main()
