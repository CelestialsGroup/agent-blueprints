#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import re
import tomllib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BLUEPRINT_ROOT = Path(
    os.environ.get("AGENT_BLUEPRINT_ROOT", ROOT.parent / "blueprint")
).resolve()
CONTRACT_ROOT = Path(
    os.environ.get("AGENT_CONTRACT_ROOT", ROOT.parent / "contract")
).resolve()
SHA256_IMAGE = re.compile(r"^[a-z0-9./:-]+@sha256:[0-9a-f]{64}$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")
EXACT_VERSION = re.compile(r"^\d+\.\d+\.\d+$")
PYTHON_REQUIREMENT = re.compile(r"^([a-z0-9-]+)==([0-9][0-9.]*)")
PURL = re.compile(r"^pkg:[a-z0-9.+-]+/.+@[^@]+$")


def load_env(path: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        key, separator, value = line.partition("=")
        if separator != "=" or not key or not value:
            raise AssertionError(f"Invalid toolchain entry: {raw_line}")
        result[key] = value
    return result


tool_versions = dict(
    line.split(maxsplit=1)
    for line in (ROOT / ".tool-versions").read_text(encoding="utf-8").splitlines()
    if line.strip()
)
if not (BLUEPRINT_ROOT / "START_HERE.md").is_file():
    raise AssertionError("Configured Blueprint root does not contain START_HERE.md")
if not (CONTRACT_ROOT / "compatibility/contract-manifest.json").is_file():
    raise AssertionError("Configured Contract root does not contain its manifest")
toolchain = load_env(ROOT / "toolchain/toolchain.env")
expected_versions = {
    "GO_VERSION": tool_versions["golang"],
    "PYTHON_VERSION": tool_versions["python"],
    "NODE_VERSION": tool_versions["nodejs"],
    "PNPM_VERSION": "11.15.1",
    "UV_VERSION": "0.11.30",
}
for key, expected in expected_versions.items():
    if toolchain.get(key) != expected or not EXACT_VERSION.fullmatch(expected):
        raise AssertionError(f"{key} must equal governed version {expected}")
if toolchain.get("GO_TARGET_OS") != "linux" or toolchain.get("GO_TARGET_ARCH") != "arm64":
    raise AssertionError("B01 Go target must be explicitly pinned to linux/arm64")
for key in (
    "GO_TOOLCHAIN_IMAGE",
    "PYTHON_TOOLCHAIN_IMAGE",
    "NODE_TOOLCHAIN_IMAGE",
    "UV_BINARY_IMAGE",
    "SQLC_IMAGE",
    "POSTGRES_TEST_IMAGE",
):
    image = toolchain.get(key, "")
    if not SHA256_IMAGE.fullmatch(image) or ":latest" in image:
        raise AssertionError(f"{key} must use an exact OCI digest")

uv_dockerfile = (ROOT / "toolchain/uv-toolchain.Dockerfile").read_text(encoding="utf-8")
if toolchain["UV_BINARY_IMAGE"] not in uv_dockerfile:
    raise AssertionError("uv toolchain must copy the pinned uv binary image")
if toolchain["PYTHON_TOOLCHAIN_IMAGE"] not in uv_dockerfile:
    raise AssertionError("uv toolchain must run on the pinned Python image")

go_mod = (ROOT / "go.mod").read_text(encoding="utf-8")
if not go_mod.startswith("module github.com/shell-echo/agent\n"):
    raise AssertionError("go.mod must use the governed shell-echo repository identity")
if "toolchain go1.26.5" not in go_mod:
    raise AssertionError("go.mod must pin toolchain go1.26.5")
if "github.com/go-chi/chi/v5 v5.3.1" not in go_mod:
    raise AssertionError("go.mod must pin chi v5.3.1")
if f"github.com/jackc/pgx/v5 v{toolchain['PGX_VERSION']}" not in go_mod:
    raise AssertionError("go.mod must pin the governed pgx v5 version")

expected_persistence_tools = {
    "GOOSE_VERSION": "3.27.2",
    "SQLC_VERSION": "1.31.1",
    "STATICCHECK_VERSION": "2026.1",
    "STATICCHECK_MODULE_VERSION": "0.7.0",
    "POSTGRES_VERSION": "18.4",
}
for key, expected in expected_persistence_tools.items():
    if toolchain.get(key) != expected:
        raise AssertionError(f"{key} must equal governed version {expected}")
for key in ("GOOSE_LINUX_ARM64_SHA256", "STATICCHECK_LINUX_ARM64_SHA256"):
    if not SHA256.fullmatch(toolchain.get(key, "")):
        raise AssertionError(f"{key} must be a SHA-256 digest")

pyproject = tomllib.loads((ROOT / "runtime/native/pyproject.toml").read_text(encoding="utf-8"))
if pyproject["build-system"]["requires"] != ["hatchling==1.31.0"]:
    raise AssertionError("Native Runtime build backend must be exact")
if pyproject["project"]["dependencies"]:
    raise AssertionError("B01 Native Runtime has no runtime dependencies")

uv_lock = tomllib.loads((ROOT / "runtime/native/uv.lock").read_text(encoding="utf-8"))
if uv_lock.get("requires-python") != ">=3.13, <3.15":
    raise AssertionError("uv.lock Python range differs from pyproject.toml")

inventory = json.loads((ROOT / "toolchain/third-party.json").read_text(encoding="utf-8"))
components = {(item["name"], item["version"]) for item in inventory["components"]}
required_components = {
    ("github.com/go-chi/chi/v5", "5.3.1"),
    ("hatchling", "1.31.0"),
    ("packaging", "26.2"),
    ("pathspec", "1.1.1"),
    ("pluggy", "1.6.0"),
    ("trove-classifiers", "2026.6.1.19"),
    ("uv", "0.11.30"),
    ("github.com/jackc/pgx/v5", "5.10.0"),
    ("github.com/jackc/pgpassfile", "1.0.0"),
    ("github.com/jackc/pgservicefile", "0.0.0-20240606120523-5a60cdf6a761"),
    ("github.com/jackc/puddle/v2", "2.2.2"),
    ("golang.org/x/sync", "0.17.0"),
    ("golang.org/x/text", "0.29.0"),
    ("github.com/pressly/goose/v3", "3.27.2"),
    ("github.com/sqlc-dev/sqlc", "1.31.1"),
    ("staticcheck", "2026.1"),
    ("postgres", "18.4"),
}
if components != required_components:
    raise AssertionError("Third-party inventory does not match governed implementation dependencies")
for item in inventory["components"]:
    if not item.get("license") or not item.get("source") or not item.get("usage"):
        raise AssertionError(f"Incomplete dependency inventory entry: {item['name']}")
    if not PURL.fullmatch(item.get("purl", "")):
        raise AssertionError(f"Invalid package URL for dependency: {item['name']}")
    if not item.get("components") or not set(item["components"]) <= {
        "agent-access",
        "native-runtime",
        "persistence",
        "persistence-test",
        "implementation-gate",
    }:
        raise AssertionError(f"Invalid component ownership for dependency: {item['name']}")

inventory_by_name = {item["name"]: item for item in inventory["components"]}
admitted_persistence_dependencies = {
    "github.com/jackc/pgx/v5",
    "github.com/pressly/goose/v3",
    "github.com/sqlc-dev/sqlc",
    "staticcheck",
    "postgres",
}
for component_name in admitted_persistence_dependencies:
    item = inventory_by_name[component_name]
    if item.get("maintenance_status") != "active":
        raise AssertionError(f"{component_name} must record active maintenance status")
    for field in (
        "maintenance_evidence",
        "security_review_source",
        "security_reviewed_at",
        "rollback_strategy",
    ):
        if not isinstance(item.get(field), str) or not item[field].strip():
            raise AssertionError(f"{component_name} is missing {field}")
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", item["security_reviewed_at"]):
        raise AssertionError(f"{component_name} has an invalid security review date")
    alternatives = item.get("alternatives_considered")
    if not isinstance(alternatives, list) or not alternatives or not all(
        isinstance(alternative, str) and alternative.strip() for alternative in alternatives
    ):
        raise AssertionError(f"{component_name} must record reviewed alternatives")

if inventory_by_name["github.com/pressly/goose/v3"].get("artifact_sha256") != toolchain[
    "GOOSE_LINUX_ARM64_SHA256"
]:
    raise AssertionError("goose release digest differs from the third-party inventory")
if inventory_by_name["staticcheck"].get("artifact_sha256") != toolchain[
    "STATICCHECK_LINUX_ARM64_SHA256"
]:
    raise AssertionError("Staticcheck release digest differs from the third-party inventory")
for component_name, image_key in (
    ("github.com/sqlc-dev/sqlc", "SQLC_IMAGE"),
    ("postgres", "POSTGRES_TEST_IMAGE"),
):
    expected_digest = "sha256:" + toolchain[image_key].rsplit("@sha256:", 1)[1]
    if inventory_by_name[component_name].get("oci_digest") != expected_digest:
        raise AssertionError(f"{component_name} OCI digest differs from the third-party inventory")

constraints = (ROOT / "runtime/native/build-constraints.txt").read_text(encoding="utf-8")
constraint_versions = {
    match.group(1): match.group(2)
    for line in constraints.splitlines()
    if (match := PYTHON_REQUIREMENT.match(line))
}
expected_build_dependencies = {
    item["name"]: item["version"]
    for item in inventory["components"]
    if item["kind"] in {"python_build_backend", "python_build_dependency"}
}
if constraint_versions != expected_build_dependencies:
    raise AssertionError("Hashed Python build constraints differ from the dependency inventory")
if constraints.count("--hash=sha256:") != 2 * len(expected_build_dependencies):
    raise AssertionError("Every Python build dependency must carry both release-file hashes")

print("Implementation supply-chain check passed: exact toolchains, hashed dependencies, licenses and public sources.")
