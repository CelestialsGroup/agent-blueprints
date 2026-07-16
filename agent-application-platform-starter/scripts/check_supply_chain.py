#!/usr/bin/env python3
from __future__ import annotations

import json
import re
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN_HOST_MARKERS = (
    ".internal",
    "localhost",
    "127.0.0.1",
    "applied-caas-gateway",
    "openai.org/artifactory",
)


def check_url(url: str, source: Path) -> None:
    parsed = urlparse(url)
    host = parsed.hostname or ""
    if any(marker in host or marker in url for marker in FORBIDDEN_HOST_MARKERS):
        raise AssertionError(f"Private registry URL in {source}: {url}")


lock_path = ROOT / "package-lock.json"
lock = json.loads(lock_path.read_text(encoding="utf-8"))
for package_name, package in lock.get("packages", {}).items():
    if isinstance(package, dict) and isinstance(package.get("resolved"), str):
        check_url(package["resolved"], lock_path)
        if package_name and not package.get("integrity"):
            raise AssertionError(f"Missing npm integrity for {package_name}")

package = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))
for group in ("dependencies", "devDependencies"):
    for name, version in package.get(group, {}).items():
        if not re.fullmatch(r"\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?", version):
            raise AssertionError(f"Unpinned npm dependency: {name}={version}")

for line in (ROOT / "requirements-contracts.txt").read_text(encoding="utf-8").splitlines():
    line = line.strip()
    if not line or line.startswith("#"):
        continue
    if "==" not in line:
        raise AssertionError(f"Unpinned Python requirement: {line}")

npmrc = (ROOT / ".npmrc").read_text(encoding="utf-8")
if "registry=https://registry.npmjs.org/" not in npmrc:
    raise AssertionError(".npmrc must default to the public npm registry")

print("Supply-chain configuration contains pinned versions and no private registry URLs.")
