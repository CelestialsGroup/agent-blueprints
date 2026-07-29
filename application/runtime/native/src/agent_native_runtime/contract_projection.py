from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from typing import Any

import rfc8785
from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012

ALLOWED_JWS_ALGORITHMS = frozenset({"EdDSA", "ES256"})


def canonicalize_json(value: Any) -> bytes:
    """Return RFC 8785 bytes after the caller has admitted Strict I-JSON."""

    return rfc8785.dumps(value)


def decode_json_without_duplicate_keys(encoded: bytes) -> Any:
    def object_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate JSON object member: {key}")
            result[key] = value
        return result

    def reject_non_finite(value: str) -> Any:
        raise ValueError(f"non-finite JSON number: {value}")

    return json.loads(
        encoded,
        object_pairs_hook=object_pairs,
        parse_constant=reject_non_finite,
    )


def build_draft202012_validator(
    schema_id: str,
    documents: Iterable[Mapping[str, Any]],
) -> Draft202012Validator:
    resources: list[tuple[str, Resource[Any]]] = []
    schemas: dict[str, Mapping[str, Any]] = {}
    for document in documents:
        identifier = document.get("$id")
        if not isinstance(identifier, str) or not identifier:
            raise ValueError("Schema document lacks an absolute $id")
        schemas[identifier] = document
        resources.append(
            (
                identifier,
                Resource.from_contents(document, default_specification=DRAFT202012),
            )
        )
    try:
        root = schemas[schema_id]
    except KeyError as error:
        raise ValueError(
            f"Schema is outside the admitted projection: {schema_id}"
        ) from error
    registry = Registry().with_resources(resources)
    return Draft202012Validator(root, registry=registry, format_checker=FormatChecker())
