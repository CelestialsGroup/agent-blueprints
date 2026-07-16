#!/usr/bin/env python3
from __future__ import annotations

import json
import math
from decimal import Decimal
from pathlib import Path
from typing import Any

import rfc8785

ROOT = Path(__file__).resolve().parents[2]
VECTORS = json.loads((ROOT / "contracts/testdata/jcs-v1/vectors.json").read_text(encoding="utf-8"))
SAFE_INTEGER_MAX = 9_007_199_254_740_991


def reject_constant(value: str) -> None:
    raise ValueError(f"Non-I-JSON constant: {value}")


def reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate object member: {key}")
        result[key] = value
    return result


def reject_unsafe_values(value: Any) -> None:
    if isinstance(value, bool) or value is None or isinstance(value, str):
        return
    if isinstance(value, int):
        if abs(value) > SAFE_INTEGER_MAX:
            raise ValueError("Integer exceeds interoperable IEEE-754 safe range")
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("Non-finite JSON number")
        return
    if isinstance(value, list):
        for item in value:
            reject_unsafe_values(item)
        return
    if isinstance(value, dict):
        for key, item in value.items():
            key.encode("utf-8", errors="strict")
            reject_unsafe_values(item)
        return
    raise TypeError(f"Unsupported JSON value: {type(value)!r}")


def strict_loads(raw: str) -> Any:
    def strict_int(token: str) -> int:
        value = int(token)
        if abs(value) > SAFE_INTEGER_MAX:
            raise ValueError("Integer exceeds interoperable IEEE-754 safe range")
        return value

    def strict_float(token: str) -> float:
        exact = Decimal(token)
        if exact == exact.to_integral_value() and abs(exact) > SAFE_INTEGER_MAX:
            raise ValueError("Mathematical integer exceeds interoperable IEEE-754 safe range")
        value = float(token)
        if not math.isfinite(value):
            raise ValueError("Non-finite JSON number")
        return value

    value = json.loads(raw, parse_int=strict_int, parse_float=strict_float, parse_constant=reject_constant, object_pairs_hook=reject_duplicate_pairs)
    reject_unsafe_values(value)
    return value


for vector in VECTORS["valid"]:
    value = json.loads(vector["input"], parse_constant=reject_constant, object_pairs_hook=reject_duplicate_pairs)
    actual = rfc8785.dumps(value).decode("utf-8")
    assert actual == vector["canonical"], f"{vector['id']}: expected {vector['canonical']!r}, got {actual!r}"

for vector in VECTORS["strict_valid"]:
    value = strict_loads(vector["input"])
    actual = rfc8785.dumps(value).decode("utf-8")
    assert actual == vector["canonical"], f"{vector['id']}: expected {vector['canonical']!r}, got {actual!r}"

for vector in VECTORS["invalid"]:
    try:
        value = strict_loads(vector["input"])
        rfc8785.dumps(value)
    except (ValueError, TypeError, UnicodeError, rfc8785.CanonicalizationError):
        continue
    raise AssertionError(f"Expected invalid JCS vector to fail: {vector['id']}")

print(f"Python JCS/Strict I-JSON: {len(VECTORS['valid'])} canonicalization, {len(VECTORS['strict_valid'])} strict-valid and {len(VECTORS['invalid'])} strict-invalid vectors passed.")
