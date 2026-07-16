#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path
from urllib.parse import urlparse

import yaml

ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN = (".internal", "localhost", "127.0.0.1", "applied-caas-gateway", "openai.org/artifactory")
EXCLUDED_PARTS = {".git", ".venv", "node_modules", "build", "coverage", "__pycache__"}


def check_url(url: str, source: Path) -> None:
    host = urlparse(url).hostname or ""
    if any(marker in host or marker in url for marker in FORBIDDEN):
        raise AssertionError(f"Private registry URL in {source}: {url}")


def git_root() -> Path | None:
    result = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"], cwd=ROOT, text=True,
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, check=False,
    )
    if result.returncode != 0:
        return None
    repository = Path(result.stdout.strip())
    prefix = ROOT.relative_to(repository).as_posix()
    tracked = subprocess.run(
        ["git", "ls-files", "--", prefix or "."], cwd=repository, text=True,
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, check=False,
    )
    return repository if tracked.returncode == 0 and tracked.stdout.strip() else None


def governed_files() -> list[Path]:
    repository = git_root()
    if repository is not None:
        prefix = ROOT.relative_to(repository).as_posix()
        result = subprocess.run(
            ["git", "ls-files", "-z", "--", prefix or "."], cwd=repository,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True,
        )
        return [repository / item.decode() for item in result.stdout.split(b"\0") if item]
    roots = ["contracts", "deploy", "docs", "examples", "prompts", "scripts", "tasks", ".github"]
    files = [path for name in roots for path in (ROOT / name).rglob("*") if path.is_file()]
    files.extend(path for path in ROOT.iterdir() if path.is_file())
    return sorted({path for path in files if not EXCLUDED_PARTS.intersection(path.relative_to(ROOT).parts)})


lock_path = ROOT / "package-lock.json"
lock = json.loads(lock_path.read_text(encoding="utf-8"))
for package_name, package_entry in lock.get("packages", {}).items():
    if isinstance(package_entry, dict) and isinstance(package_entry.get("resolved"), str):
        check_url(package_entry["resolved"], lock_path)
        if package_name and not package_entry.get("integrity"):
            raise AssertionError(f"Missing npm integrity for {package_name}")

package = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))
root_lock = lock.get("packages", {}).get("", {})
if lock.get("version") != package.get("version") or root_lock.get("version") != package.get("version"):
    raise AssertionError("package.json and package-lock.json versions must match")
for group in ("dependencies", "devDependencies"):
    for name, version in package.get(group, {}).items():
        if not re.fullmatch(r"\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?", version):
            raise AssertionError(f"Unpinned npm dependency: {name}={version}")

requirements = (ROOT / "requirements-contracts-v0.8.4.txt").read_text(encoding="utf-8")
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
for requirement in logical_lines:
    if "==" not in requirement or "--hash=sha256:" not in requirement:
        raise AssertionError(f"Python requirement lacks exact version/hash: {requirement}")

workflow_path = ROOT / ".github/workflows/contracts.yml"
workflow = yaml.safe_load(workflow_path.read_text(encoding="utf-8"))
for job in workflow.get("jobs", {}).values():
    for step in job.get("steps", []):
        action = step.get("uses")
        if action and not action.startswith("./") and not re.fullmatch(r"[0-9a-zA-Z_.-]+/[0-9a-zA-Z_.-]+@[0-9a-f]{40}", action):
            raise AssertionError(f"GitHub Action must be pinned by full commit SHA: {action}")

for relative in ("scripts/bootstrap_contracts.sh", "scripts/validate_all.sh", "scripts/install_github_workflow.sh"):
    path = ROOT / relative
    if not path.exists() or not os.access(path, os.X_OK):
        raise AssertionError(f"Required gate script is not executable: {relative}")

tracked = governed_files()
pyc = sorted(path for path in tracked if path.suffix == ".pyc" or "__pycache__" in path.parts)
if pyc:
    raise AssertionError(f"Tracked Python bytecode is forbidden: {[str(path) for path in pyc]}")
ds_store = sorted(path for path in tracked if path.name == ".DS_Store")
if ds_store:
    raise AssertionError(f"Tracked .DS_Store files are forbidden: {[str(path) for path in ds_store]}")

repository = git_root()
if repository is not None and repository.resolve() != ROOT.resolve():
    installed = repository / ".github/workflows/contracts.yml"
    if not installed.exists():
        raise AssertionError("Monorepo contract workflow is not installed at the Git root; run scripts/install_github_workflow.sh and commit it")
    if installed.read_bytes() != workflow_path.read_bytes():
        raise AssertionError("Git-root contracts workflow differs from the governed package workflow; reinstall and commit it")

npmrc = (ROOT / ".npmrc").read_text(encoding="utf-8")
assert "registry=https://registry.npmjs.org/" in npmrc
print("Supply-chain gate passed: tracked-file hygiene/workflow placement, pinned Actions/dependencies, hashes and public registries.")
