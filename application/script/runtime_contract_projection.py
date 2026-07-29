#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import re
import shutil
from pathlib import Path
from typing import Any, Iterable

import yaml


OPENAPI_PATH = Path("openapi/agent-runtime-provider-v1.yaml")
SCHEMA_DIRECTORY = Path("schemas")
ADDITIONAL_RUNTIME_SCHEMA_IDS = (
    "urn:agent-platform:system-safety-control:v1",
)


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def canonical_python_distribution_name(value: str) -> str:
    return re.sub(r"[-_.]+", "-", value).lower()


def iter_refs(value: Any) -> Iterable[str]:
    if isinstance(value, dict):
        reference = value.get("$ref")
        if isinstance(reference, str):
            yield reference
        for nested in value.values():
            yield from iter_refs(nested)
    elif isinstance(value, list):
        for nested in value:
            yield from iter_refs(nested)


def iter_strings(value: Any) -> Iterable[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for nested in value.values():
            yield from iter_strings(nested)
    elif isinstance(value, list):
        for nested in value:
            yield from iter_strings(nested)


def split_reference(reference: str) -> tuple[str, str]:
    target, separator, fragment = reference.partition("#")
    return target, f"#{fragment}" if separator else ""


def load_schema_index(contract_root: Path) -> tuple[dict[Path, Any], dict[str, Path]]:
    schema_root = contract_root / SCHEMA_DIRECTORY
    documents: dict[Path, Any] = {}
    identifiers: dict[str, Path] = {}
    for path in sorted(schema_root.glob("*.schema.json")):
        relative = path.relative_to(contract_root)
        document = json.loads(path.read_text(encoding="utf-8"))
        identifier = document.get("$id")
        if not isinstance(identifier, str) or not identifier:
            raise AssertionError(f"Schema lacks an absolute $id: {relative}")
        if identifier in identifiers:
            raise AssertionError(f"Duplicate Schema $id: {identifier}")
        documents[relative] = document
        identifiers[identifier] = relative
    return documents, identifiers


def resolve_reference(
    reference: str,
    current: Path,
    identifiers: dict[str, Path],
) -> Path | None:
    target, _ = split_reference(reference)
    if not target:
        return None
    if target.startswith("urn:"):
        try:
            return identifiers[target]
        except KeyError as error:
            raise AssertionError(f"Unresolved Schema $id reference: {target}") from error
    resolved = Path(os.path.normpath(current.parent / target))
    if not resolved.is_relative_to(SCHEMA_DIRECTORY):
        raise AssertionError(f"Schema reference escapes Contract schemas: {reference}")
    return resolved


def runtime_schema_closure(
    openapi: Any,
    documents: dict[Path, Any],
    identifiers: dict[str, Path],
) -> list[Path]:
    roots: set[Path] = set()
    for reference in iter_refs(openapi):
        target, _ = split_reference(reference)
        if not target.startswith("../schemas/"):
            continue
        resolved = Path(os.path.normpath(OPENAPI_PATH.parent / target))
        if resolved not in documents:
            raise AssertionError(f"OpenAPI references an unknown Schema: {reference}")
        roots.add(resolved)
    for value in iter_strings(openapi):
        if value in identifiers:
            roots.add(identifiers[value])
            continue
        if value.startswith("../schemas/") and value.endswith(".schema.json"):
            resolved = Path(os.path.normpath(OPENAPI_PATH.parent / value))
            if resolved not in documents:
                raise AssertionError(f"OpenAPI names an unknown Schema: {value}")
            roots.add(resolved)
    for identifier in ADDITIONAL_RUNTIME_SCHEMA_IDS:
        roots.add(identifiers[identifier])
    if not roots:
        raise AssertionError("Runtime Provider OpenAPI contains no external Schema roots")

    closure: set[Path] = set()
    pending = sorted(roots, reverse=True)
    while pending:
        current = pending.pop()
        if current in closure:
            continue
        closure.add(current)
        for reference in iter_refs(documents[current]):
            resolved = resolve_reference(reference, current, identifiers)
            if resolved is not None and resolved not in closure:
                if resolved not in documents:
                    raise AssertionError(
                        f"Schema {current} references an unknown local document: {reference}"
                    )
                pending.append(resolved)
    return sorted(closure)


def rewrite_references(
    value: Any,
    current: Path,
    identifiers: dict[str, Path],
) -> Any:
    if isinstance(value, dict):
        rewritten = {
            key: rewrite_references(nested, current, identifiers)
            for key, nested in value.items()
        }
        reference = rewritten.get("$ref")
        if isinstance(reference, str) and reference.startswith("urn:"):
            target, fragment = split_reference(reference)
            target_path = identifiers[target]
            rewritten["$ref"] = os.path.relpath(target_path, current.parent) + fragment
        return rewritten
    if isinstance(value, list):
        return [rewrite_references(nested, current, identifiers) for nested in value]
    return value


def closure_digest(paths: list[Path], contract_root: Path) -> str:
    digest = hashlib.sha256()
    for relative in paths:
        content = (contract_root / relative).read_bytes()
        encoded_path = relative.as_posix().encode("utf-8")
        digest.update(len(encoded_path).to_bytes(8, "big"))
        digest.update(encoded_path)
        digest.update(len(content).to_bytes(8, "big"))
        digest.update(content)
    return digest.hexdigest()


def prepare(contract_root: Path, output_root: Path) -> None:
    if output_root.exists():
        shutil.rmtree(output_root)
    (output_root / OPENAPI_PATH.parent).mkdir(parents=True)
    (output_root / SCHEMA_DIRECTORY).mkdir(parents=True)

    openapi_source = contract_root / OPENAPI_PATH
    openapi = yaml.safe_load(openapi_source.read_text(encoding="utf-8"))
    documents, identifiers = load_schema_index(contract_root)
    closure = runtime_schema_closure(openapi, documents, identifiers)

    shutil.copyfile(openapi_source, output_root / OPENAPI_PATH)
    for relative in closure:
        rewritten = rewrite_references(documents[relative], relative, identifiers)
        (output_root / relative).write_text(
            json.dumps(rewritten, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

    manifest = {
        "schema_version": 1,
        "openapi_path": OPENAPI_PATH.as_posix(),
        "openapi_sha256": sha256_file(openapi_source),
        "schema_count": len(closure),
        "schema_closure_sha256": closure_digest(closure, contract_root),
        "schemas": [
            {
                "path": relative.as_posix(),
                "id": documents[relative]["$id"],
                "sha256": sha256_file(contract_root / relative),
            }
            for relative in closure
        ],
    }
    (output_root / "projection-manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def write_python_codegen_inventory(image_reference: str, output_path: Path) -> None:
    distributions: dict[str, str] = {}
    for distribution in importlib.metadata.distributions():
        name = distribution.metadata.get("Name")
        if not isinstance(name, str) or not name:
            raise AssertionError("Python codegen distribution lacks a package name")
        canonical_name = canonical_python_distribution_name(name)
        if canonical_name in distributions:
            raise AssertionError(f"Duplicate Python codegen distribution: {canonical_name}")
        distributions[canonical_name] = distribution.version
    generator_version = distributions.get("datamodel-code-generator")
    if generator_version is None:
        raise AssertionError("Python codegen image lacks datamodel-code-generator")
    inventory = {
        "schema_version": 1,
        "image_reference": image_reference,
        "generator": {
            "name": "datamodel-code-generator",
            "version": generator_version,
        },
        "distribution_count": len(distributions),
        "distributions": [
            {"name": name, "version": version}
            for name, version in sorted(distributions.items())
        ],
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(inventory, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def finalize(
    language: str,
    generated_path: Path,
    manifest_path: Path,
    dependency_lock_path: Path,
    output_path: Path,
) -> None:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    dependency_lock = json.loads(dependency_lock_path.read_text(encoding="utf-8"))
    contract = dependency_lock["contract"]
    if language == "go":
        marker = "// Code generated by github.com/atombender/go-jsonschema, DO NOT EDIT.\n"
        prefix = "//"
    else:
        marker = "# generated by datamodel-codegen:\n"
        prefix = "#"
    header = (
        f"{prefix} Contract source revision: {contract['source_revision']}\n"
        f"{prefix} Contract manifest digest: {contract['manifest_digest']}\n"
        f"{prefix} Runtime OpenAPI SHA-256: {manifest['openapi_sha256']}\n"
        f"{prefix} Runtime Schema closure ({manifest['schema_count']} documents): "
        f"{manifest['schema_closure_sha256']}\n"
    )
    if generated_path.is_dir():
        if language != "python":
            raise AssertionError("Only Python projection may be generated as a module tree")
        if output_path.exists():
            shutil.rmtree(output_path)
        for source in sorted(generated_path.rglob("*")):
            if not source.is_file():
                continue
            relative = source.relative_to(generated_path)
            destination = output_path / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            generated = source.read_text(encoding="utf-8")
            if source.suffix == ".py" and marker in generated[:256]:
                generated = generated.replace(marker, marker + header, 1)
            destination.write_text(generated, encoding="utf-8")
        return

    generated = generated_path.read_text(encoding="utf-8")
    if marker not in generated[:256]:
        raise AssertionError(f"Unexpected {language} generator header")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(generated.replace(marker, marker + header, 1), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)

    prepare_parser = subparsers.add_parser("prepare")
    prepare_parser.add_argument("--contract-root", type=Path, required=True)
    prepare_parser.add_argument("--output-root", type=Path, required=True)

    inventory_parser = subparsers.add_parser("python-codegen-inventory")
    inventory_parser.add_argument("--image-reference", required=True)
    inventory_parser.add_argument("--output", type=Path, required=True)

    finalize_parser = subparsers.add_parser("finalize")
    finalize_parser.add_argument("--language", choices=("go", "python"), required=True)
    finalize_parser.add_argument("--generated", type=Path, required=True)
    finalize_parser.add_argument("--manifest", type=Path, required=True)
    finalize_parser.add_argument("--dependency-lock", type=Path, required=True)
    finalize_parser.add_argument("--output", type=Path, required=True)

    arguments = parser.parse_args()
    if arguments.command == "prepare":
        prepare(arguments.contract_root.resolve(), arguments.output_root.resolve())
    elif arguments.command == "python-codegen-inventory":
        write_python_codegen_inventory(arguments.image_reference, arguments.output)
    else:
        finalize(
            arguments.language,
            arguments.generated,
            arguments.manifest,
            arguments.dependency_lock,
            arguments.output,
        )


if __name__ == "__main__":
    main()
