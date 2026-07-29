from __future__ import annotations

import json
import math
from collections import deque
from collections.abc import Iterable, Mapping
from decimal import Decimal, InvalidOperation
from typing import Any

import rfc8785
from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012

ALLOWED_JWS_ALGORITHMS = frozenset({"EdDSA", "ES256"})
MAX_SAFE_INTEGER = 9_007_199_254_740_991
DEFAULT_MAX_JSON_DEPTH = 64
DEFAULT_MAX_JSON_NODES = 100_000
DEFAULT_MAX_NUMBER_TOKEN_BYTES = 1_024
DEFAULT_MAX_DECIMAL_EXPONENT = 400


def canonicalize_json(value: Any) -> bytes:
    """Return RFC 8785 bytes after the caller has admitted Strict I-JSON."""

    return rfc8785.dumps(value)


def decode_strict_ijson(
    encoded: bytes,
    *,
    max_depth: int = DEFAULT_MAX_JSON_DEPTH,
    max_nodes: int = DEFAULT_MAX_JSON_NODES,
    max_number_token_bytes: int = DEFAULT_MAX_NUMBER_TOKEN_BYTES,
    max_decimal_exponent: int = DEFAULT_MAX_DECIMAL_EXPONENT,
) -> Any:
    if encoded.startswith(b"\xef\xbb\xbf"):
        raise ValueError("Strict I-JSON forbids a UTF-8 BOM")
    if max_depth < 1 or max_nodes < 1:
        raise ValueError("Strict I-JSON bounds must be positive")
    if max_number_token_bytes < 1 or max_decimal_exponent < 1:
        raise ValueError("Strict I-JSON number bounds must be positive")
    try:
        source = encoded.decode("utf-8", errors="strict")
    except UnicodeDecodeError as error:
        raise ValueError("Strict I-JSON requires valid UTF-8") from error

    def object_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate JSON object member: {key}")
            result[key] = value
        return result

    def reject_non_finite(value: str) -> Any:
        raise ValueError(f"non-finite JSON number: {value}")

    def parse_number(value: str) -> int | float:
        if len(value.encode("ascii")) > max_number_token_bytes:
            raise ValueError("JSON number token exceeds the configured byte limit")
        exponent_text = value.lower().partition("e")[2]
        if exponent_text:
            try:
                exponent = int(exponent_text, 10)
            except ValueError as error:
                raise ValueError("JSON number exponent is invalid") from error
            if abs(exponent) > max_decimal_exponent:
                raise ValueError("JSON number exponent exceeds the configured limit")
        try:
            decimal_value = Decimal(value)
        except InvalidOperation as error:
            raise ValueError("JSON number is invalid") from error
        if not decimal_value.is_finite():
            raise ValueError("JSON number must be finite")
        if (
            decimal_value == decimal_value.to_integral_value()
            and abs(decimal_value) > MAX_SAFE_INTEGER
        ):
            raise ValueError("Strict I-JSON forbids an unsafe integer")
        if "." not in value and "e" not in value.lower():
            return int(value, 10)
        parsed = float(value)
        if not math.isfinite(parsed):
            raise ValueError("JSON number is outside the finite IEEE-754 range")
        return parsed

    document = json.loads(
        source,
        object_pairs_hook=object_pairs,
        parse_constant=reject_non_finite,
        parse_float=parse_number,
        parse_int=parse_number,
    )
    _validate_json_structure(document, max_depth=max_depth, max_nodes=max_nodes)
    return document


def decode_json_without_duplicate_keys(encoded: bytes) -> Any:
    """Decode JCS reference inputs while rejecting ambiguous JSON objects."""

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


def _validate_json_structure(value: Any, *, max_depth: int, max_nodes: int) -> None:
    pending: deque[tuple[Any, int]] = deque([(value, 1)])
    nodes = 0
    while pending:
        current, depth = pending.pop()
        nodes += 1
        if nodes > max_nodes:
            raise ValueError("JSON document exceeds the configured node limit")
        if depth > max_depth:
            raise ValueError("JSON document exceeds the configured depth limit")
        if isinstance(current, str):
            if any(0xD800 <= ord(character) <= 0xDFFF for character in current):
                raise ValueError("Strict I-JSON forbids lone Unicode surrogates")
            continue
        if isinstance(current, list):
            pending.extend((item, depth + 1) for item in current)
            continue
        if isinstance(current, dict):
            for key, item in current.items():
                nodes += 1
                if nodes > max_nodes:
                    raise ValueError("JSON document exceeds the configured node limit")
                if any(0xD800 <= ord(character) <= 0xDFFF for character in key):
                    raise ValueError("Strict I-JSON forbids lone Unicode surrogates")
                pending.append((item, depth + 1))


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
