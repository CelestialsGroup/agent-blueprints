#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from urllib.parse import urlparse

import yaml

ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN = (".internal", "localhost", "127.0.0.1", "applied-caas-gateway", "openai.org/artifactory")


def check_url(url: str, source: Path) -> None:
    host = urlparse(url).hostname or ""
    if any(marker in host or marker in url for marker in FORBIDDEN):
        raise AssertionError(f"Private registry URL in {source}: {url}")


lock_path = ROOT / "package-lock.json"
lock = json.loads(lock_path.read_text(encoding="utf-8"))
for package_name, package in lock.get("packages", {}).items():
    if isinstance(package, dict) and isinstance(package.get("resolved"), str):
        check_url(package["resolved"], lock_path)
        if package_name and not package.get("integrity"):
            raise AssertionError(f"Missing npm integrity for {package_name}")

package = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))
root_lock = lock.get("packages", {}).get("", {})
if lock.get("version") != package.get("version") or root_lock.get("version") != package.get("version"):
    raise AssertionError("package.json and package-lock.json versions must match")
for group in ("dependencies", "devDependencies"):
    for name, version in package.get(group, {}).items():
        if not re.fullmatch(r"\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?", version):
            raise AssertionError(f"Unpinned npm dependency: {name}={version}")

requirements = (ROOT / "requirements-contracts-v0.8.2.txt").read_text(encoding="utf-8")
logical_lines: list[str] = []
buffer = ""
for raw in requirements.splitlines():
    line = raw.strip()
    if not line or line.startswith("#") or line.startswith("--index-url"):
        continue
    buffer += (" " if buffer else "") + line.rstrip("\\").strip()
    if not line.endswith("\\"):
        logical_lines.append(buffer)
        buffer = ""
if buffer:
    logical_lines.append(buffer)
for requirement in logical_lines:
    if "==" not in requirement or "--hash=sha256:" not in requirement:
        raise AssertionError(f"Python requirement lacks exact version/hash: {requirement}")

workflow = yaml.safe_load((ROOT / ".github/workflows/contracts.yml").read_text(encoding="utf-8"))
for job in workflow.get("jobs", {}).values():
    for step in job.get("steps", []):
        action = step.get("uses")
        if action and not action.startswith("./"):
            ref = action.rsplit("@", 1)[-1]
            if not re.fullmatch(r"[0-9a-f]{40}", ref):
                raise AssertionError(f"GitHub Action must be pinned by full commit SHA: {action}")

for relative in ("scripts/bootstrap_contracts.sh", "scripts/validate_all.sh", "scripts/install_github_workflow.sh"):
    path = ROOT / relative
    if not path.exists() or not os.access(path, os.X_OK):
        raise AssertionError(f"Required gate script is not executable: {relative}")

pyc = sorted(path.relative_to(ROOT) for path in ROOT.rglob("*.pyc"))
if pyc:
    raise AssertionError(f"Compiled Python artifacts must not be committed: {pyc}")

npmrc = (ROOT / ".npmrc").read_text(encoding="utf-8")
assert "registry=https://registry.npmjs.org/" in npmrc
print("Supply-chain gate passed: pinned Actions/dependencies, hashed Python lock, public registries, executable entrypoints, no bytecode artifacts.")
