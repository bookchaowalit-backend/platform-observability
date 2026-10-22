#!/usr/bin/env python3
"""Fail when the vendored contract schema drifts from its pinned canonical copy.

``schema/book-platform.contract.v1.schema.json`` is vendored from
``bookchaowalit-backend-core/contracts/``. The sha256 of the canonical file is
pinned in ``schema/book-platform.contract.v1.schema.json.sha256`` (``sha256sum``
format), and the same pin file lives next to the canonical schema in
bookchaowalit-backend-core. This check always compares the vendored copy with
the pin (offline). With ``--canonical PATH`` (a backend-core checkout or the
canonical schema file) it also compares against the canonical copy itself.

To change the schema: change the canonical copy in bookchaowalit-backend-core,
update its pin there, then copy both files into this repository's ``schema/``.
The check never contacts a network service.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_NAME = "book-platform.contract.v1.schema.json"
SCHEMA_RELATIVE = f"schema/{SCHEMA_NAME}"
PIN_RELATIVE = f"{SCHEMA_RELATIVE}.sha256"
CANONICAL_RELATIVE = f"contracts/{SCHEMA_NAME}"
CANONICAL_ENV = "BOOK_BACKEND_CORE_DIR"
PIN_RE = re.compile(r"^([0-9a-f]{64})\s+\*?(\S+)\s*$")


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_pin(path: Path) -> tuple[str | None, str | None]:
    """Return ``(digest, error)`` for a single-line sha256sum pin file."""

    try:
        lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    except (OSError, UnicodeError) as exc:
        return None, f"cannot read pin file: {exc}"
    if len(lines) != 1:
        return None, "pin file must contain exactly one '<sha256>  <file>' line"
    match = PIN_RE.match(lines[0])
    if match is None:
        return None, "pin file line must be '<64 lowercase hex>  <file>'"
    if Path(match.group(2)).name != SCHEMA_NAME:
        return None, f"pin file names {match.group(2)!r}, expected {SCHEMA_NAME!r}"
    return match.group(1), None


def resolve_canonical(value: str) -> Path:
    path = Path(value).expanduser().resolve()
    return path / CANONICAL_RELATIVE if path.is_dir() else path


def validate(root: Path = ROOT, canonical: Path | None = None) -> list[str]:
    """Return every drift error for the repository at ``root``."""

    schema = root / SCHEMA_RELATIVE
    pin = root / PIN_RELATIVE
    errors: list[str] = []
    for path, relative in ((schema, SCHEMA_RELATIVE), (pin, PIN_RELATIVE)):
        if not path.is_file():
            errors.append(f"{relative} is missing")
    if errors:
        return errors

    pinned, pin_error = read_pin(pin)
    if pin_error:
        return [f"{PIN_RELATIVE}: {pin_error}"]
    actual = sha256_file(schema)
    if actual != pinned:
        errors.append(
            f"{SCHEMA_RELATIVE} sha256 {actual[:12]} does not match pinned canonical {pinned[:12]}; "
            "change bookchaowalit-backend-core/contracts first, then re-vendor the schema and its pin"
        )

    if canonical is not None:
        if not canonical.is_file():
            errors.append(f"canonical schema {canonical} is missing")
        else:
            canonical_digest = sha256_file(canonical)
            if canonical_digest != actual:
                errors.append(
                    f"{SCHEMA_RELATIVE} sha256 {actual[:12]} differs from canonical "
                    f"{canonical} ({canonical_digest[:12]})"
                )
            if canonical_digest != pinned:
                errors.append(f"{PIN_RELATIVE} is stale: canonical sha256 is {canonical_digest[:12]}")
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("root", nargs="?", default=str(ROOT), help="platform repository root")
    parser.add_argument(
        "--canonical",
        default=os.environ.get(CANONICAL_ENV),
        help=f"backend-core checkout or canonical schema file (default: ${CANONICAL_ENV})",
    )
    args = parser.parse_args(argv)
    root = Path(args.root).resolve()
    canonical = resolve_canonical(args.canonical) if args.canonical else None
    errors = validate(root, canonical)
    if errors:
        for message in errors:
            print(f"FAIL: {message}")
        return 1
    scope = f"pin and canonical {canonical}" if canonical else "pin"
    print(f"OK: {SCHEMA_RELATIVE} matches {scope} ({sha256_file(root / SCHEMA_RELATIVE)[:12]})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
