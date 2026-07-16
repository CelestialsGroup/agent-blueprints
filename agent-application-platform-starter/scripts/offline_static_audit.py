#!/usr/bin/env python3
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Iterable

import yaml

ROOT = Path(__file__).resolve().parents[1]
SOURCE_DIRS = ["contracts", "deploy", "docs", "examples", "prompts", "tasks", "scripts"]


def source_files(patterns: Iterable[str]) -> list[Path]:
    paths: set[Path] = set()
    for directory in SOURCE_DIRS:
        base = ROOT / directory
        if base.exists():
            for pattern in patterns:
                paths.update(base.rglob(pattern))
    for pattern in patterns:
        paths.update(ROOT.glob(pattern))
    return sorted(path for path in paths if path.is_file())


def load_yaml(path: Path) -> Any:
    documents = list(yaml.safe_load_all(path.read_text(encoding="utf-8")))
    return documents[0] if len(documents) == 1 else documents


json_files = source_files(["*.json"])
yaml_files = source_files(["*.yaml", "*.yml"])
for path in json_files:
    json.loads(path.read_text(encoding="utf-8"))
for path in yaml_files:
    list(yaml.safe_load_all(path.read_text(encoding="utf-8")))

openapi_files = sorted((ROOT / "contracts/openapi").glob("*.yaml"))
for path in openapi_files:
    document = load_yaml(path)
    assert document["openapi"] == "3.1.1", path
    assert document.get("servers"), path
    assert document.get("security") is not None, path
    for route, path_item in document["paths"].items():
        for method, operation in path_item.items():
            if method not in {"get", "post", "put", "patch", "delete"}:
                continue
            assert operation.get("operationId"), f"{path}: {method} {route}"
            security = operation.get("security", document.get("security"))
            responses = set(operation.get("responses", {}))
            assert any(code.startswith("2") for code in responses), f"{path}: {method} {route}: missing success"
            assert "500" in responses, f"{path}: {method} {route}: missing 500"
            if method in {"post", "put", "patch", "delete"} and security:
                missing = {"401", "500"} - responses
                assert not missing, f"{path}: {method} {route}: missing {missing}"
    for match in re.finditer(r"\$ref:\s+([^\s]+)", path.read_text(encoding="utf-8")):
        ref = match.group(1).strip("'\"")
        if ref.startswith("#") or "://" in ref or ref.startswith("urn:"):
            continue
        assert (path.parent / ref.split("#", 1)[0]).resolve().exists(), f"Missing ref: {path}: {ref}"

kustomization_path = ROOT / "deploy/k8s/base/kustomization.yaml"
for resource in load_yaml(kustomization_path).get("resources", []):
    assert (kustomization_path.parent / resource).resolve().exists(), f"Missing Kustomize resource: {resource}"

namespace_docs = load_yaml(ROOT / "deploy/k8s/base/namespace.yaml")
namespace_names = {doc["metadata"]["name"] for doc in namespace_docs if doc and doc.get("kind") == "Namespace"}
assert {"agent-platform", "agent-runtime"}.issubset(namespace_names)

network_docs = load_yaml(ROOT / "deploy/k8s/base/network-policy.yaml")
policy_names = {doc["metadata"]["name"] for doc in network_docs if doc and doc.get("kind") == "NetworkPolicy"}
assert {
    "default-deny-control-plane", "default-deny-runtime", "allow-control-plane-dns",
    "allow-runtime-dns", "allow-runtime-to-egress-gateway"
}.issubset(policy_names)

runtime_docs = load_yaml(ROOT / "deploy/k8s/base/runtime-gateway.yaml")
deployment = next(doc for doc in runtime_docs if doc.get("kind") == "Deployment")
pod_spec = deployment["spec"]["template"]["spec"]
assert pod_spec["securityContext"]["runAsNonRoot"] is True
security = pod_spec["containers"][0]["securityContext"]
assert security["allowPrivilegeEscalation"] is False
assert security["readOnlyRootFilesystem"] is True
assert security["capabilities"]["drop"] == ["ALL"]

markdown_files = source_files(["*.md"])
link_pattern = re.compile(r"\[[^\]]+\]\(([^)]+)\)")
missing_links: list[str] = []
for path in markdown_files:
    for target in link_pattern.findall(path.read_text(encoding="utf-8")):
        target = target.split("#", 1)[0]
        if not target or "://" in target or target.startswith("mailto:"):
            continue
        if not (path.parent / target).resolve().exists():
            missing_links.append(f"{path.relative_to(ROOT)} -> {target}")
assert not missing_links, "Missing Markdown links:\n" + "\n".join(missing_links)

print(f"Offline static audit passed: {len(json_files)} JSON, {len(yaml_files)} YAML, {len(openapi_files)} OpenAPI, {len(markdown_files)} Markdown source files.")
