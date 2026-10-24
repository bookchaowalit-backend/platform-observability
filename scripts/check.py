#!/usr/bin/env python3
"""Offline contract and repository-shape check for a Book Platform repository.

The contract is validated against ``schema/book-platform.contract.v1.schema.json``
with a small, dependency-free JSON Schema subset, followed by semantic checks
that a schema cannot express (README/contract agreement, source-path rules,
interface documentation and placeholder detection). The check never contacts a
network service and never reads secrets.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

# --- Repository-specific settings -------------------------------------------
# Everything below this block is shared verbatim across Book Platform
# repositories; keep local differences inside this block.
ALLOWED_STATUS = frozenset({"scaffolded"})
IMPLEMENTATION_REPOSITORIES = frozenset({"solo-empire"})
EXTRA_REQUIRED_FILES: tuple[str, ...] = ()
EXTRA_README_HEADINGS: tuple[str, ...] = ()
# ---------------------------------------------------------------------------

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_RELATIVE = "schema/book-platform.contract.v1.schema.json"
BASE_REQUIRED_FILES = ("README.md", "contract.json", "scripts/check.sh", SCHEMA_RELATIVE)
BASE_README_HEADINGS = ("## Scope", "## Boundary", "## Local verification", "## Migration gate")
PLACEHOLDER_RE = re.compile(r"__[A-Z][A-Z0-9_]*__")
JSON_TYPES: dict[str, type | tuple[type, ...]] = {
    "object": dict,
    "array": list,
    "string": str,
    "boolean": bool,
    "number": (int, float),
    "integer": int,
    "null": type(None),
}


def _type_matches(value: Any, expected: str) -> bool:
    python_type = JSON_TYPES[expected]
    if expected in {"integer", "number"} and isinstance(value, bool):
        return False
    return isinstance(value, python_type)


def _resolve_ref(schema_root: dict[str, Any], ref: str) -> dict[str, Any]:
    if not ref.startswith("#/"):
        raise ValueError(f"unsupported $ref {ref!r}")
    node: Any = schema_root
    for part in ref[2:].split("/"):
        node = node[part]
    return node


def validate_schema(value: Any, schema: dict[str, Any], schema_root: dict[str, Any], path: str = "$") -> list[str]:
    """Validate ``value`` with the JSON Schema subset used by the contract schema."""

    if "$ref" in schema:
        return validate_schema(value, _resolve_ref(schema_root, schema["$ref"]), schema_root, path)
    errors: list[str] = []
    if "const" in schema and value != schema["const"]:
        return [f"{path} must be {schema['const']!r}"]
    if "enum" in schema and value not in schema["enum"]:
        return [f"{path} must be one of {schema['enum']}"]
    expected_type = schema.get("type")
    if expected_type is not None and not _type_matches(value, expected_type):
        return [f"{path} must be of type {expected_type}"]
    if isinstance(value, str):
        if len(value) < schema.get("minLength", 0):
            errors.append(f"{path} must not be empty")
        pattern = schema.get("pattern")
        if pattern is not None and re.search(pattern, value) is None:
            errors.append(f"{path} does not match pattern {pattern}")
    if isinstance(value, list):
        if len(value) < schema.get("minItems", 0):
            errors.append(f"{path} must contain at least {schema['minItems']} item(s)")
        if schema.get("uniqueItems"):
            seen: list[Any] = []
            for item in value:
                if item in seen:
                    errors.append(f"{path} contains duplicate item {item!r}")
                seen.append(item)
        item_schema = schema.get("items")
        if item_schema is not None:
            for index, item in enumerate(value):
                errors.extend(validate_schema(item, item_schema, schema_root, f"{path}[{index}]"))
    if isinstance(value, dict):
        for key in schema.get("required", []):
            if key not in value:
                errors.append(f"{path}.{key} is required")
        properties = schema.get("properties", {})
        if schema.get("additionalProperties") is False:
            for key in sorted(set(value) - set(properties)):
                errors.append(f"{path}.{key} is not allowed")
        for key, child_schema in properties.items():
            if key in value:
                errors.extend(validate_schema(value[key], child_schema, schema_root, f"{path}.{key}"))
    return errors


def _read_json(path: Path, label: str, errors: list[str]) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        errors.append(f"{label} is not valid JSON: {exc}")
        return None


def _semantic_errors(root: Path, contract: dict[str, Any], readme: str) -> list[str]:
    errors: list[str] = []
    platform_id = contract["platform_id"]
    repository = contract["repository"]
    status = contract["status"]

    if status not in ALLOWED_STATUS:
        errors.append(f"status {status!r} is not allowed here; expected one of {sorted(ALLOWED_STATUS)}")
    if platform_id in contract["depends_on"]:
        errors.append("a platform must not depend on itself")
    if contract["data_owner"] not in {"none", repository}:
        errors.append("data_owner must be this repository or 'none'")

    implementation = contract["current_implementation"]
    source_repository = implementation["repository"]
    if source_repository not in IMPLEMENTATION_REPOSITORIES | {repository}:
        errors.append(
            "current_implementation.repository must be one of "
            f"{sorted(IMPLEMENTATION_REPOSITORIES | {repository})}"
        )
    source_path = implementation["source_path"]
    source_paths = implementation.get("source_paths")
    if source_paths is not None:
        expected = source_paths[0] if source_paths else "none"
        if source_path != expected:
            errors.append(f"current_implementation.source_path must equal the first source_paths entry ({expected!r})")
    if source_repository == repository and not (root / source_path).exists():
        errors.append("current_implementation.source_path must exist in this repository")
    if source_path == "none" and implementation.get("source_status") not in {None, "new-boundary"}:
        errors.append("source_path 'none' is only valid for a new-boundary platform")

    for heading in BASE_README_HEADINGS + EXTRA_README_HEADINGS:
        if heading not in readme:
            errors.append(f"README.md is missing {heading}")
    if f"Repository: `{repository}`" not in readme:
        errors.append("README.md must name the repository in its Boundary section")
    if f"Status: `{status}`" not in readme:
        errors.append(f"README.md status must match contract status {status!r}")

    documents = {"README.md": readme}
    interfaces = contract.get("interfaces", [])
    surface_doc = contract.get("surface_doc")
    if interfaces and surface_doc is None:
        errors.append("surface_doc is required when interfaces are declared")
    if surface_doc is not None:
        surface_path = root / surface_doc
        if not surface_path.is_file():
            errors.append(f"surface_doc {surface_doc} is missing")
        else:
            surface_text = surface_path.read_text(encoding="utf-8")
            documents[surface_doc] = surface_text
            for item in interfaces:
                if f"`{item['id']}`" not in surface_text:
                    errors.append(f"{surface_doc} does not document interface `{item['id']}`")
    ids = [item["id"] for item in interfaces]
    for duplicate in sorted({item for item in ids if ids.count(item) > 1}):
        errors.append(f"interface id {duplicate!r} is declared more than once")

    documents["contract.json"] = json.dumps(contract)
    for label, text in documents.items():
        match = PLACEHOLDER_RE.search(text)
        if match:
            errors.append(f"{label} still contains scaffold placeholder {match.group(0)}")
    return errors


def validate(root: Path = ROOT) -> list[str]:
    """Return every contract and repository-shape error for ``root``."""

    errors: list[str] = []
    for relative in BASE_REQUIRED_FILES + EXTRA_REQUIRED_FILES:
        if not (root / relative).is_file():
            errors.append(f"{relative} is missing")
    if errors:
        return errors

    schema = _read_json(root / SCHEMA_RELATIVE, SCHEMA_RELATIVE, errors)
    contract = _read_json(root / "contract.json", "contract.json", errors)
    if errors:
        return errors
    if not isinstance(schema, dict):
        return [f"{SCHEMA_RELATIVE} root must be an object"]
    schema_errors = validate_schema(contract, schema, schema)
    if schema_errors:
        return [f"contract.json: {message}" for message in schema_errors]
    readme = (root / "README.md").read_text(encoding="utf-8")
    return _semantic_errors(root, contract, readme)


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    root = Path(args[0]).resolve() if args else ROOT
    errors = validate(root)
    if errors:
        for message in errors:
            print(f"FAIL: {message}")
        return 1
    contract = json.loads((root / "contract.json").read_text(encoding="utf-8"))
    interfaces = len(contract.get("interfaces", []))
    print(
        f"OK: {contract['repository']} ({contract['platform_id']}) {contract['status']} contract, "
        f"{interfaces} documented interface(s)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
