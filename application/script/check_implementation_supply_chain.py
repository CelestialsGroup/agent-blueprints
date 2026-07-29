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


def canonical_python_name(value: str) -> str:
    return re.sub(r"[-_.]+", "-", value).lower()


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
    "RUNTIME_PYTHON_CODEGEN_IMAGE",
    "SQLC_IMAGE",
    "POSTGRES_TEST_IMAGE",
    "TEMPORAL_SERVER_TEST_IMAGE",
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
if toolchain.get("TEMPORAL_SDK_VERSION") != "1.46.0":
    raise AssertionError("TEMPORAL_SDK_VERSION must equal the admitted SDK version")
if f"go.temporal.io/sdk v{toolchain['TEMPORAL_SDK_VERSION']}" not in go_mod:
    raise AssertionError("go.mod must pin the governed Temporal Go SDK version")
if "go.temporal.io/api v1.63.0" not in go_mod:
    raise AssertionError("go.mod must pin the SDK-aligned Temporal API version")
expected_runtime_go_dependencies = {
    "RUNTIME_GO_CODEGEN_VERSION": "0.24.0",
    "RUNTIME_PYTHON_CODEGEN_VERSION": "0.71.0",
}
for key, expected in expected_runtime_go_dependencies.items():
    if toolchain.get(key) != expected:
        raise AssertionError(f"{key} must equal the admitted Runtime projection version")
for module, version in (
    ("github.com/go-jose/go-jose/v4", "4.1.4"),
    ("github.com/gowebpki/jcs", "1.0.1"),
    ("github.com/santhosh-tekuri/jsonschema/v6", "6.0.2"),
):
    if f"{module} v{version}" not in go_mod:
        raise AssertionError(f"go.mod must pin admitted Runtime dependency {module} v{version}")
expected_temporal_metadata = {
    "TEMPORAL_SDK_COMMIT": "8e2c89c7c9d8d41f633bf039063422dd10c1fec5",
    "TEMPORAL_SDK_SOURCE": "https://github.com/temporalio/sdk-go/tree/v1.46.0",
    "TEMPORAL_SERVER_VERSION": "1.29.7",
    "TEMPORAL_SERVER_COMMIT": "1f74f0c8e9935980d92a39069185671bbbba7c7e",
    "TEMPORAL_SERVER_SOURCE": "https://github.com/temporalio/temporal/tree/v1.29.7",
    "TEMPORAL_SERVER_IMAGE_REVISION": "cb8c66860ecef6ddc413fdc187494df0beae7407",
}
for key, expected in expected_temporal_metadata.items():
    if toolchain.get(key) != expected:
        raise AssertionError(f"{key} must equal the reviewed Temporal source metadata")
expected_temporal_sums = {
    "go.temporal.io/sdk v1.46.0 h1:zD2l907+4iVkLsnJZwFj/oIIjYsoqyjsHlKO/3tDKoU=",
    "go.temporal.io/sdk v1.46.0/go.mod h1:x3v/9ImVh469kiHspoq1xgLdPnetbfuCAm+Y1+sUtIo=",
}
go_sum_lines = set((ROOT / "go.sum").read_text(encoding="utf-8").splitlines())
if not expected_temporal_sums <= go_sum_lines:
    raise AssertionError("Temporal SDK module and module-file sums must match the reviewed release")

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
expected_python_runtime_dependencies = {
    "cryptography==49.0.0",
    "jsonschema==4.26.0",
    "PyJWT==2.13.0",
    "rfc8785==0.1.4",
    "typing-extensions==4.15.0",
}
if set(pyproject["project"]["dependencies"]) != expected_python_runtime_dependencies:
    raise AssertionError("Native Runtime dependencies differ from the admitted P0 set")
expected_python_quality_dependencies = {"mypy==2.3.0", "ruff==0.16.0"}
if set(pyproject.get("dependency-groups", {}).get("dev", [])) != (
    expected_python_quality_dependencies
):
    raise AssertionError("Native Runtime quality dependencies differ from the admitted set")

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
    ("golang.org/x/sync", "0.20.0"),
    ("golang.org/x/text", "0.37.0"),
    ("go.temporal.io/sdk", "1.46.0"),
    ("go.temporal.io/api", "1.63.0"),
    ("github.com/facebookgo/clock", "0.0.0-20150410010913-600d898af40a"),
    ("github.com/gogo/protobuf", "1.3.2"),
    ("github.com/golang/mock", "1.6.0"),
    ("github.com/google/uuid", "1.6.0"),
    ("github.com/grpc-ecosystem/go-grpc-middleware/v2", "2.3.2"),
    ("github.com/grpc-ecosystem/grpc-gateway/v2", "2.22.0"),
    ("github.com/nexus-rpc/nexus-proto-annotations", "0.1.0"),
    ("github.com/nexus-rpc/sdk-go", "0.6.0"),
    ("github.com/robfig/cron", "1.2.0"),
    ("golang.org/x/net", "0.55.0"),
    ("golang.org/x/sys", "0.45.0"),
    ("golang.org/x/time", "0.3.0"),
    ("google.golang.org/grpc", "1.79.3"),
    ("google.golang.org/protobuf", "1.36.11"),
    ("google.golang.org/genproto/googleapis/api", "0.0.0-20260120221211-b8f7ae30c516"),
    ("google.golang.org/genproto/googleapis/rpc", "0.0.0-20260120221211-b8f7ae30c516"),
    ("github.com/davecgh/go-spew", "1.1.1"),
    ("github.com/pmezard/go-difflib", "1.0.0"),
    ("github.com/stretchr/objx", "0.5.2"),
    ("github.com/stretchr/testify", "1.11.1"),
    ("gopkg.in/yaml.v3", "3.0.1"),
    ("temporalio/auto-setup", "1.29.7"),
    ("github.com/pressly/goose/v3", "3.27.2"),
    ("github.com/sqlc-dev/sqlc", "1.31.1"),
    ("staticcheck", "2026.1"),
    ("postgres", "18.4"),
}
required_components.update(
    {
        ("github.com/go-jose/go-jose/v4", "4.1.4"),
        ("github.com/gowebpki/jcs", "1.0.1"),
        ("github.com/santhosh-tekuri/jsonschema/v6", "6.0.2"),
        ("koxudaxi/datamodel-code-generator", "0.71.0"),
        ("github.com/atombender/go-jsonschema", "0.24.0"),
        ("dario.cat/mergo", "1.0.2"),
        ("github.com/cpuguy83/go-md2man/v2", "2.0.6"),
        ("github.com/goccy/go-yaml", "1.19.2"),
        ("github.com/google/go-cmp", "0.7.0"),
        ("github.com/inconshreveable/mousetrap", "1.1.0"),
        ("github.com/mitchellh/go-wordwrap", "1.0.1"),
        ("github.com/russross/blackfriday/v2", "2.1.0"),
        ("github.com/sanity-io/litter", "1.5.8"),
        ("github.com/sosodev/duration", "1.4.0"),
        ("github.com/spf13/cobra", "1.10.2"),
        ("github.com/spf13/pflag", "1.0.10"),
        ("go.yaml.in/yaml/v3", "3.0.4"),
        ("gopkg.in/check.v1", "0.0.0-20161208181325-20d25e280405"),
        ("attrs", "26.1.0"),
        ("cffi", "2.1.0"),
        ("cryptography", "49.0.0"),
        ("jsonschema", "4.26.0"),
        ("jsonschema-specifications", "2025.9.1"),
        ("pycparser", "3.0"),
        ("PyJWT", "2.13.0"),
        ("referencing", "0.37.0"),
        ("rfc8785", "0.1.4"),
        ("rpds-py", "2026.6.3"),
        ("ast-serialize", "0.6.0"),
        ("librt", "0.13.0"),
        ("mypy", "2.3.0"),
        ("ruff", "0.16.0"),
        ("typing-extensions", "4.15.0"),
        ("annotated-types", "0.8.0"),
        ("anyio", "4.14.2"),
        ("argcomplete", "3.7.0"),
        ("black", "26.5.1"),
        ("certifi", "2026.7.22"),
        ("click", "8.4.2"),
        ("genson", "1.4.0"),
        ("h11", "0.16.0"),
        ("httpcore", "1.0.9"),
        ("httpx", "0.28.1"),
        ("idna", "3.18"),
        ("inflect", "7.5.0"),
        ("isort", "8.0.1"),
        ("jinja2", "3.1.6"),
        ("markupsafe", "3.0.3"),
        ("more-itertools", "11.1.0"),
        ("mypy-extensions", "1.1.0"),
        ("pip", "26.1.2"),
        ("platformdirs", "4.11.0"),
        ("pydantic", "2.13.4"),
        ("pydantic-core", "2.46.4"),
        ("pytokens", "0.4.1"),
        ("pyyaml", "6.0.3"),
        ("typeguard", "4.5.2"),
        ("typing-extensions", "4.16.0"),
        ("typing-inspection", "0.4.2"),
    }
)
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
        "orchestration",
        "orchestration-test",
        "implementation-gate",
        "runtime-contract-projection",
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

admitted_orchestration_dependencies = {
    item["name"]
    for item in inventory["components"]
    if {"orchestration", "orchestration-test"} & set(item["components"])
}
for component_name in admitted_orchestration_dependencies:
    item = inventory_by_name[component_name]
    if item.get("maintenance_status") not in {"active", "upstream_selected"}:
        raise AssertionError(f"{component_name} must record its reviewed maintenance status")
    for field in (
        "maintenance_evidence",
        "security_review_source",
        "security_reviewed_at",
        "upgrade_strategy",
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

admitted_runtime_projection_dependencies = [
    item
    for item in inventory["components"]
    if "runtime-contract-projection" in item["components"]
]
for item in admitted_runtime_projection_dependencies:
    component_name = f"{item['name']}@{item['version']}"
    if item.get("maintenance_status") not in {"active", "upstream_selected"}:
        raise AssertionError(f"{component_name} must record reviewed maintenance status")
    for field in (
        "maintenance_evidence",
        "security_review_source",
        "security_reviewed_at",
        "upgrade_strategy",
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

admitted_native_quality_dependencies = [
    item
    for item in inventory["components"]
    if item.get("native_runtime_lock_distribution") is True
]
for item in admitted_native_quality_dependencies:
    component_name = f"{item['name']}@{item['version']}"
    if item.get("maintenance_status") not in {"active", "upstream_selected"}:
        raise AssertionError(f"{component_name} must record reviewed maintenance status")
    for field in (
        "maintenance_evidence",
        "security_review_source",
        "security_reviewed_at",
        "upgrade_strategy",
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

go_mod_components = {
    (match.group(1), match.group(2).removeprefix("v"))
    for line in go_mod.splitlines()
    if (match := re.fullmatch(r"\s*([^\s]+)\s+(v[^\s]+)(?:\s+// indirect)?\s*", line))
}
inventory_go_modules = {
    (item["name"], item["version"])
    for item in inventory["components"]
    if item["kind"] == "go_module"
}
if go_mod_components != inventory_go_modules:
    raise AssertionError("go.mod modules and reviewed Go dependency inventory differ")

codegen_modules = {
    (parts[0], parts[1].removeprefix("v"))
    for line in (ROOT / "toolchain/runtime-codegen/modules.txt").read_text(
        encoding="utf-8"
    ).splitlines()
    if line.strip() and len(parts := line.split()) == 2
}
inventory_all_go_modules = {
    (item["name"], item["version"])
    for item in inventory["components"]
    if item["kind"] in {"go_module", "go_codegen_module"}
}
inventory_codegen_modules = {
    (item["name"], item["version"])
    for item in inventory["components"]
    if item["kind"] == "go_codegen_module"
}
if not codegen_modules <= inventory_all_go_modules:
    raise AssertionError("Go Runtime generator build list contains unreviewed modules")
if not inventory_codegen_modules <= codegen_modules:
    raise AssertionError("Go Runtime generator inventory contains stale modules")
runtime_codegen_mod = (ROOT / "toolchain/runtime-codegen/go.mod").read_text(encoding="utf-8")
if (
    f"github.com/atombender/go-jsonschema v{toolchain['RUNTIME_GO_CODEGEN_VERSION']}"
    not in runtime_codegen_mod
):
    raise AssertionError("Runtime Go generator module differs from the admitted version")

python_codegen_lock = json.loads(
    (ROOT / "toolchain/runtime-python-codegen-packages.json").read_text(encoding="utf-8")
)
if python_codegen_lock.get("schema_version") != 1:
    raise AssertionError("Python Runtime generator distribution manifest version differs")
if python_codegen_lock.get("image_reference") != toolchain["RUNTIME_PYTHON_CODEGEN_IMAGE"]:
    raise AssertionError("Python Runtime generator manifest is bound to another image")
if python_codegen_lock.get("generator") != {
    "name": "datamodel-code-generator",
    "version": toolchain["RUNTIME_PYTHON_CODEGEN_VERSION"],
}:
    raise AssertionError("Python Runtime generator identity differs from the admitted version")
locked_python_codegen = {
    (canonical_python_name(item["name"]), item["version"])
    for item in python_codegen_lock["distributions"]
}
if len(locked_python_codegen) != python_codegen_lock.get("distribution_count"):
    raise AssertionError("Python Runtime generator distribution manifest has duplicates")
inventory_python_codegen = {
    (
        canonical_python_name(item.get("python_distribution_name", item["name"])),
        item["version"],
    )
    for item in inventory["components"]
    if item.get("python_codegen_distribution") is True
}
if locked_python_codegen != inventory_python_codegen:
    raise AssertionError(
        "Python Runtime generator image distributions and reviewed inventory differ"
    )

locked_python_runtime = {
    (canonical_python_name(package["name"]), package["version"])
    for package in uv_lock["package"]
    if package.get("source", {}).get("registry")
}
inventory_python_runtime_lock = {
    (canonical_python_name(item["name"]), item["version"])
    for item in inventory["components"]
    if item["kind"] == "python_runtime_dependency"
    or item.get("native_runtime_lock_distribution") is True
}
if locked_python_runtime != inventory_python_runtime_lock:
    raise AssertionError("uv.lock and reviewed Python Runtime dependency inventory differ")

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
    ("temporalio/auto-setup", "TEMPORAL_SERVER_TEST_IMAGE"),
    ("koxudaxi/datamodel-code-generator", "RUNTIME_PYTHON_CODEGEN_IMAGE"),
):
    expected_digest = "sha256:" + toolchain[image_key].rsplit("@sha256:", 1)[1]
    if inventory_by_name[component_name].get("oci_digest") != expected_digest:
        raise AssertionError(f"{component_name} OCI digest differs from the third-party inventory")
if inventory_by_name["go.temporal.io/sdk"].get("source_commit") != toolchain[
    "TEMPORAL_SDK_COMMIT"
]:
    raise AssertionError("Temporal SDK source commit differs from the third-party inventory")
if inventory_by_name["go.temporal.io/sdk"].get("source") != toolchain["TEMPORAL_SDK_SOURCE"]:
    raise AssertionError("Temporal SDK source differs from the third-party inventory")
if inventory_by_name["temporalio/auto-setup"].get("server_source_commit") != toolchain[
    "TEMPORAL_SERVER_COMMIT"
]:
    raise AssertionError("Temporal Server source commit differs from the third-party inventory")
if inventory_by_name["temporalio/auto-setup"].get("server_source") != toolchain[
    "TEMPORAL_SERVER_SOURCE"
]:
    raise AssertionError("Temporal Server source differs from the third-party inventory")
if inventory_by_name["temporalio/auto-setup"].get("image_build_revision") != toolchain[
    "TEMPORAL_SERVER_IMAGE_REVISION"
]:
    raise AssertionError("Temporal image build revision differs from the third-party inventory")

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
