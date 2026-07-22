#!/usr/bin/env python3
from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run(command: list[str], cwd: Path, expected: int = 0) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(command, cwd=cwd, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)
    if result.returncode != expected:
        raise AssertionError(f"Expected exit {expected}, got {result.returncode}: {' '.join(command)}\n{result.stdout}")
    return result


with tempfile.TemporaryDirectory(prefix="agent-platform-monorepo-gate-") as temporary:
    repository = Path(temporary)
    package = repository / "starter"
    shutil.copytree(ROOT, package, ignore=shutil.ignore_patterns(".venv", "node_modules", "build", "__pycache__", "*.pyc"))
    (repository / ".DS_Store").write_bytes(b"tracked-test-fixture")
    run(["git", "init", "-q"], repository)
    run(["git", "config", "user.email", "contract-gate@example.invalid"], repository)
    run(["git", "config", "user.name", "Contract Gate"], repository)
    run(["git", "add", "."], repository)
    run(["git", "commit", "-qm", "initial nested package with tracked DS_Store"], repository)

    installer = run(["./scripts/install_github_workflow.sh"], package, expected=3)
    if "DS_Store" not in installer.stdout:
        raise AssertionError("Installer did not report the tracked root .DS_Store blocker")
    run([sys.executable, "scripts/check_supply_chain.py"], package, expected=1)

    run(["git", "rm", "--cached", "--", ".DS_Store"], repository)
    run(["git", "add", ".github/workflows/contracts.yml", ".gitignore"], repository)
    run([sys.executable, "scripts/check_supply_chain.py"], package, expected=1)

    run(["git", "commit", "-qm", "activate root contract admission"], repository)
    passed = run([sys.executable, "scripts/check_supply_chain.py"], package)
    if "Supply-chain gate passed" not in passed.stdout:
        raise AssertionError("Committed integration did not pass the Supply-chain Gate")

print("Monorepo integration negative/commit-state tests passed.")
