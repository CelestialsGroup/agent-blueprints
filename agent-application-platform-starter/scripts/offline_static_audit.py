#!/usr/bin/env python3
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]


def load_yaml(path: Path) -> Any:
    documents = list(yaml.safe_load_all(path.read_text(encoding="utf-8")))
    return documents[0] if len(documents) == 1 else documents


json_files = sorted(ROOT.rglob("*.json"))
yaml_files = sorted([*ROOT.rglob("*.yaml"), *ROOT.rglob("*.yml")])

for path in json_files:
    json.loads(path.read_text(encoding="utf-8"))

for path in yaml_files:
    list(yaml.safe_load_all(path.read_text(encoding="utf-8")))

openapi_files = sorted((ROOT / "contracts/openapi").glob("*.yaml"))
required_mutation_responses = {"401", "500"}

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
            effective_security = operation.get("security", document.get("security"))
            assert effective_security is not None, f"{path}: {method} {route}"
            responses = set(operation.get("responses", {}))
            assert any(code.startswith("2") for code in responses), (
                f"{path}: {method} {route}: missing success response"
            )
            assert "500" in responses, f"{path}: {method} {route}: missing 500"
            if method in {"post", "put", "patch", "delete"} and effective_security:
                missing = required_mutation_responses - responses
                assert not missing, (
                    f"{path}: {method} {route}: missing mutation responses {missing}"
                )

    for match in re.finditer(r"\$ref:\s+([^\s]+)", path.read_text(encoding="utf-8")):
        ref = match.group(1).strip("'\"")
        if ref.startswith("#") or "://" in ref or ref.startswith("urn:"):
            continue
        target = (path.parent / ref.split("#", 1)[0]).resolve()
        assert target.exists(), f"Missing OpenAPI external ref: {path}: {ref}"

kustomization_path = ROOT / "deploy/k8s/base/kustomization.yaml"
kustomization = load_yaml(kustomization_path)
for resource in kustomization.get("resources", []):
    target = (kustomization_path.parent / resource).resolve()
    assert target.exists(), f"Missing Kustomize resource: {resource}"

namespace_docs = load_yaml(ROOT / "deploy/k8s/base/namespace.yaml")
namespace_names = {
    document["metadata"]["name"]
    for document in namespace_docs
    if document and document.get("kind") == "Namespace"
}
assert {"agent-platform", "agent-runtime"}.issubset(namespace_names)

network_docs = load_yaml(ROOT / "deploy/k8s/base/network-policy.yaml")
policy_names = {
    document["metadata"]["name"]
    for document in network_docs
    if document and document.get("kind") == "NetworkPolicy"
}
assert "default-deny-control-plane" in policy_names
assert "default-deny-runtime" in policy_names
assert "allow-control-plane-dns" in policy_names
assert "allow-runtime-dns" in policy_names
assert "allow-runtime-to-egress-gateway" in policy_names

runtime_docs = load_yaml(ROOT / "deploy/k8s/base/runtime-gateway.yaml")
runtime_deployment = next(
    document for document in runtime_docs if document.get("kind") == "Deployment"
)
pod_spec = runtime_deployment["spec"]["template"]["spec"]
assert pod_spec["securityContext"]["runAsNonRoot"] is True
container = pod_spec["containers"][0]
security = container["securityContext"]
assert security["allowPrivilegeEscalation"] is False
assert security["readOnlyRootFilesystem"] is True
assert security["capabilities"]["drop"] == ["ALL"]

markdown_files = sorted(ROOT.rglob("*.md"))
link_pattern = re.compile(r"\[[^\]]+\]\(([^)]+)\)")
missing_links: list[str] = []
for path in markdown_files:
    text = path.read_text(encoding="utf-8")
    for target in link_pattern.findall(text):
        target = target.split("#", 1)[0]
        if not target or "://" in target or target.startswith("mailto:"):
            continue
        candidate = (path.parent / target).resolve()
        if not candidate.exists():
            missing_links.append(f"{path.relative_to(ROOT)} -> {target}")
assert not missing_links, "Missing Markdown links:\n" + "\n".join(missing_links)

for path in [ROOT / "package-lock.json", ROOT / "package.json"]:
    text = path.read_text(encoding="utf-8")
    assert "applied-caas-gateway" not in text
    assert "openai.org/artifactory" not in text

print(
    f"Offline static audit passed: {len(json_files)} JSON, {len(yaml_files)} YAML, "
    f"{len(openapi_files)} OpenAPI, {len(markdown_files)} Markdown files."
)
