#!/usr/bin/env python3
"""Compare contract.json with the solo-empire platform registry (local, read-only).

Usage: ``python3 scripts/check_registry_alignment.py --solo-empire PATH``

Reads ``repository-catalog/registries/platforms.yaml`` from a local solo-empire
checkout and fails when ``repository``, ``data_owner``, ``capabilities``,
``depends_on``, ``source_status``, ``migration_gates`` or
``current_implementation.source_paths`` disagree with this repository's
registry entry. Source paths and interface sources that do not exist in the
checkout are reported as warnings (``--strict-paths`` turns them into errors).
The registry is parsed with a small dependency-free reader for its flat
``key: value`` / ``[a, b]`` layout. Nothing is written and no network is used,
so CI does not run it (the parent checkout is not available there).
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
REGISTRY_RELATIVE = "repository-catalog/registries/platforms.yaml"
LIST_FIELDS = ("capabilities", "depends_on", "migration_gates")
SCALAR_FIELDS = ("repository", "data_owner", "source_status")


def _scalar(text: str) -> Any:
    text = text.strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in "'\"":
        return text[1:-1]
    if text.startswith("[") and text.endswith("]"):
        inner = text[1:-1].strip()
        return [_scalar(part) for part in inner.split(",")] if inner else []
    return text


def parse_registry(text: str) -> dict[str, dict[str, Any]]:
    """Return registry platforms keyed by ``id`` from the flat registry layout."""

    platforms: dict[str, dict[str, Any]] = {}
    in_platforms = False
    current: dict[str, Any] | None = None
    for raw in text.splitlines():
        line = raw.split(" #", 1)[0].rstrip() if not raw.lstrip().startswith("#") else ""
        if not line.strip():
            continue
        if not line.startswith(" "):
            in_platforms = line.strip() == "platforms:"
            current = None
            continue
        if not in_platforms:
            continue
        stripped = line.strip()
        if stripped.startswith("- "):
            current = {}
            stripped = stripped[2:]
        if current is None or ":" not in stripped:
            continue
        key, _, value = stripped.partition(":")
        current[key.strip()] = _scalar(value)
        if key.strip() == "id":
            platforms[str(current["id"])] = current
    return platforms


def _within(path: str, prefixes: list[str]) -> bool:
    return any(path == prefix or path.startswith(prefix.rstrip("/") + "/") for prefix in prefixes)


def compare(contract: dict[str, Any], entry: dict[str, Any], solo_root: Path | None) -> tuple[list[str], list[str]]:
    """Return ``(errors, warnings)`` for a contract and its registry entry."""

    errors: list[str] = []
    warnings: list[str] = []
    for field in SCALAR_FIELDS:
        actual = contract["current_implementation"].get(field) if field == "source_status" else contract.get(field)
        if field in entry and actual != entry[field]:
            errors.append(f"{field}: contract {actual!r} != registry {entry[field]!r}")
    for field in LIST_FIELDS:
        if field in entry and list(contract.get(field, [])) != list(entry[field]):
            errors.append(f"{field}: contract {contract.get(field, [])} != registry {entry[field]}")
    implementation = contract["current_implementation"]
    source_paths = list(implementation.get("source_paths", []))
    if "source_paths" in entry and source_paths != list(entry["source_paths"]):
        errors.append(
            f"current_implementation.source_paths: contract {source_paths} != registry {entry['source_paths']}"
        )
    provided = [item for item in contract.get("interfaces", []) if item.get("direction") == "provides"]
    for item in provided:
        source = item.get("source", "none")
        if source != "none" and source_paths and not _within(source, source_paths):
            warnings.append(f"provided interface {item['id']} source {source} is outside source_paths")
    if solo_root is not None and implementation.get("repository") == "solo-empire":
        candidates = source_paths + [item.get("source", "none") for item in contract.get("interfaces", [])]
        for path in dict.fromkeys(candidates):
            if path != "none" and not (solo_root / path).exists():
                warnings.append(f"{path} does not exist in {solo_root.name}")
    return errors, warnings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--solo-empire", required=True, help="path to a local solo-empire checkout")
    parser.add_argument("--root", default=str(ROOT), help="platform repository root")
    parser.add_argument("--strict-paths", action="store_true", help="treat missing paths as errors")
    args = parser.parse_args(argv)
    solo_root = Path(args.solo_empire).expanduser().resolve()
    registry_path = solo_root / REGISTRY_RELATIVE
    if not registry_path.is_file():
        print(f"FAIL: {REGISTRY_RELATIVE} not found under {solo_root}")
        return 1
    contract = json.loads((Path(args.root) / "contract.json").read_text(encoding="utf-8"))
    entry = parse_registry(registry_path.read_text(encoding="utf-8")).get(contract["platform_id"])
    if entry is None:
        print(f"FAIL: platform {contract['platform_id']!r} is not in {REGISTRY_RELATIVE}")
        return 1
    errors, warnings = compare(contract, entry, solo_root)
    if args.strict_paths:
        errors, warnings = errors + warnings, []
    for message in warnings:
        print(f"WARN: {message}")
    for message in errors:
        print(f"FAIL: {message}")
    if errors:
        return 1
    print(f"OK: {contract['repository']} contract agrees with the solo-empire platform registry")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
