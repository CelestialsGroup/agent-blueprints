#!/usr/bin/env python3
from __future__ import annotations

import copy
import json
import shutil
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_SOURCE = ROOT / "contracts" / "schemas"
OPENAPI_SOURCE = ROOT / "contracts" / "openapi"
OUTPUT = ROOT / "build" / "openapi-src"


def rewrite_refs(value: Any, id_to_filename: dict[str, str]) -> Any:
    if isinstance(value, dict):
        result = {key: rewrite_refs(child, id_to_filename) for key, child in value.items()}
        ref = result.get("$ref")
        if isinstance(ref, str):
            base, separator, fragment = ref.partition("#")
            if base in id_to_filename:
                result["$ref"] = id_to_filename[base] + (separator + fragment if separator else "")
        return result
    if isinstance(value, list):
        return [rewrite_refs(child, id_to_filename) for child in value]
    return value


def annotate_required_scopes(value: Any) -> Any:
    """Add no-op property annotations required by Redocly's scoped rule.

    Draft 2020-12 allows `required` in a nested `not` schema to refer to the
    containing instance without redeclaring `properties`. Redocly evaluates
    its lint rule per subschema, so the generated projection supplies empty
    annotations without changing validation semantics.
    """
    if isinstance(value, dict):
        required = value.get("required")
        if isinstance(required, list):
            properties = value.setdefault("properties", {})
            if isinstance(properties, dict):
                for name in required:
                    properties.setdefault(name, {})
        for child in value.values():
            annotate_required_scopes(child)
    elif isinstance(value, list):
        for child in value:
            annotate_required_scopes(child)
    return value


schemas: dict[Path, dict[str, Any]] = {}
id_to_filename: dict[str, str] = {}
for path in sorted(SCHEMA_SOURCE.glob("*.json")):
    schema = json.loads(path.read_text(encoding="utf-8"))
    schema_id = schema.get("$id")
    if isinstance(schema_id, str):
        if schema_id in id_to_filename:
            raise AssertionError(f"Duplicate schema $id: {schema_id}")
        id_to_filename[schema_id] = path.name
    schemas[path] = schema

if OUTPUT.exists():
    shutil.rmtree(OUTPUT)
(OUTPUT / "schemas").mkdir(parents=True)
(OUTPUT / "openapi").mkdir(parents=True)

for path, schema in schemas.items():
    prepared = annotate_required_scopes(rewrite_refs(copy.deepcopy(schema), id_to_filename))
    (OUTPUT / "schemas" / path.name).write_text(
        json.dumps(prepared, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

for path in sorted(OPENAPI_SOURCE.glob("*.yaml")):
    shutil.copy2(path, OUTPUT / "openapi" / path.name)

print(
    f"Prepared {len(schemas)} Registry-backed schemas and "
    f"{len(list(OPENAPI_SOURCE.glob('*.yaml')))} OpenAPI documents for Redocly."
)
