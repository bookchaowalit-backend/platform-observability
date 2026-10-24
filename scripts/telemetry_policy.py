#!/usr/bin/env python3
"""Redacted telemetry policy (BOO-160, accepted 2026-10-16): validate events and redact health snapshots.

Dependency-free. ``validate_event`` applies
``schema/telemetry/redacted-telemetry-event.v1.schema.json`` (a closed allow-list)
plus its ``x-forbidden`` key and value scan. ``redact_health_snapshot`` turns the
payload produced by solo-empire ``infra/scripts/utils/system_health.py``
``full_health()`` into a schema-valid ``health_snapshot`` event, dropping revenue
amounts, personal counts, provider names and free-text errors.

Usage::

    python3 scripts/telemetry_policy.py validate EVENT.json [...]
    python3 scripts/telemetry_policy.py redact-health [--assume-tz Asia/Bangkok] RAW.json
"""

from __future__ import annotations

import json
import re
import sys
from datetime import UTC, datetime, tzinfo
from functools import lru_cache
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "schema" / "telemetry" / "redacted-telemetry-event.v1.schema.json"
SCHEMA_VERSION = "observability.telemetry.v1"
# system_health.py writes datetime.now().isoformat(): naive wall-clock time on the
# operator host, which runs in Asia/Bangkok (+07:00).
SYSTEM_HEALTH_TZ = "Asia/Bangkok"
ENVELOPE_KEYS = frozenset({"schema_version", "signal", "retention_class", "service", "environment", "observed_at"})
SUPPORTED_KEYWORDS = frozenset({
    "$schema", "$id", "$defs", "$ref", "title", "description", "x-status", "x-forbidden",
    "type", "const", "enum", "pattern", "minLength", "maxLength", "minimum", "maximum",
    "required", "properties", "additionalProperties", "items", "minItems", "maxItems",
    "oneOf", "allOf", "not",
})
_TYPES: dict[str, type | tuple[type, ...]] = {
    "object": dict, "array": list, "string": str, "boolean": bool,
    "number": (int, float), "integer": int, "null": type(None),
}


@lru_cache(maxsize=1)
def load_schema() -> dict[str, Any]:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def _normalise_key(key: str) -> str:
    """camelCase -> snake_case, lowercase, '-' and '.' -> '_'."""

    key = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", key)
    key = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", key)
    return re.sub(r"[-.]+", "_", key.lower()).strip("_")


@lru_cache(maxsize=1)
def _forbidden() -> tuple[tuple[tuple[str, ...], ...], tuple[tuple[str, re.Pattern[str]], ...]]:
    rules = load_schema()["x-forbidden"]
    keys = tuple(sorted({tuple(_normalise_key(key).split("_")) for key in rules["keys"]}))
    patterns = tuple((name, re.compile(pattern)) for name, pattern in rules["value_patterns"].items())
    return keys, patterns


@lru_cache(maxsize=1)
def _exempt_formats() -> dict[str, re.Pattern[str]]:
    rules = load_schema()["x-forbidden"]["exempt_when_format_matches"]
    return {key: re.compile(pattern) for key, pattern in rules.items() if key != "description"}


@lru_cache(maxsize=4096)
def forbidden_key(key: str) -> bool:
    """True when a forbidden name equals the key or is a run of its components."""

    parts = tuple(_normalise_key(key).split("_"))
    for forbidden in _forbidden()[0]:
        size = len(forbidden)
        if any(parts[index:index + size] == forbidden for index in range(len(parts) - size + 1)):
            return True
    return False


def scan_forbidden(value: Any, path: str = "$", field: str | None = None) -> list[str]:
    """Return a finding for every forbidden key or forbidden-looking string value.

    A value under a format-pinned key (trace/span/correlation/request IDs) is not
    pattern-scanned when it already matches its closed hex/UUID format: random
    hex can look like a digit run, but cannot carry free text.
    """

    patterns = _forbidden()[1]
    findings: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            if forbidden_key(str(key)):
                findings.append(f"{path}.{key}: forbidden key")
            findings.extend(scan_forbidden(child, f"{path}.{key}", str(key)))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            findings.extend(scan_forbidden(child, f"{path}[{index}]"))
    elif isinstance(value, str):
        exempt = _exempt_formats().get(field or "")
        if exempt is not None and exempt.fullmatch(value):
            return findings
        for name, pattern in patterns:
            if pattern.search(value):
                findings.append(f"{path}: forbidden value ({name})")
    return findings


def _resolve(root: dict[str, Any], ref: str) -> dict[str, Any]:
    if not ref.startswith("#/"):
        raise ValueError(f"unsupported $ref {ref!r}")
    node: Any = root
    for part in ref[2:].split("/"):
        node = node[part]
    return node


def _type_ok(value: Any, expected: str) -> bool:
    if expected in {"integer", "number"} and isinstance(value, bool):
        return False
    return isinstance(value, _TYPES[expected])


def schema_errors(value: Any, schema: dict[str, Any], root: dict[str, Any], path: str = "$") -> list[str]:
    """Validate with the JSON Schema subset listed in SUPPORTED_KEYWORDS."""

    if "$ref" in schema:
        return schema_errors(value, _resolve(root, schema["$ref"]), root, path)
    if "oneOf" in schema:
        branches = [schema_errors(value, branch, root, path) for branch in schema["oneOf"]]
        passing = [errors for errors in branches if not errors]
        if len(passing) == 1:
            return []
        if len(passing) > 1:
            return [f"{path} matches more than one oneOf branch"]
        # Report the branch selected by the discriminator when there is one.
        signal = value.get("signal") if isinstance(value, dict) else None
        for branch, branch_errors in zip(schema["oneOf"], branches):
            target = _resolve(root, branch["$ref"]) if "$ref" in branch else branch
            if target.get("properties", {}).get("signal", {}).get("const") == signal:
                return branch_errors
        return [f"{path} matches no oneOf branch (unknown signal {signal!r})"]
    errors: list[str] = []
    for sub in schema.get("allOf", []):
        errors.extend(schema_errors(value, sub, root, path))
    if "not" in schema and not schema_errors(value, schema["not"], root, path):
        errors.append(f"{path} matches a disallowed pattern")
    if "const" in schema and value != schema["const"]:
        return errors + [f"{path} must be {schema['const']!r}"]
    if "enum" in schema and value not in schema["enum"]:
        return errors + [f"{path} must be one of {schema['enum']}"]
    expected = schema.get("type")
    if expected is not None and not _type_ok(value, expected):
        return errors + [f"{path} must be of type {expected}"]
    if isinstance(value, str):
        if len(value) < schema.get("minLength", 0):
            errors.append(f"{path} is too short")
        if "maxLength" in schema and len(value) > schema["maxLength"]:
            errors.append(f"{path} is too long")
        if "pattern" in schema and re.search(schema["pattern"], value) is None:
            errors.append(f"{path} does not match pattern {schema['pattern']}")
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if "minimum" in schema and value < schema["minimum"]:
            errors.append(f"{path} is below minimum {schema['minimum']}")
        if "maximum" in schema and value > schema["maximum"]:
            errors.append(f"{path} is above maximum {schema['maximum']}")
    if isinstance(value, list):
        if len(value) < schema.get("minItems", 0):
            errors.append(f"{path} has too few items")
        if "maxItems" in schema and len(value) > schema["maxItems"]:
            errors.append(f"{path} has more than {schema['maxItems']} items")
        if "items" in schema:
            for index, item in enumerate(value):
                errors.extend(schema_errors(item, schema["items"], root, f"{path}[{index}]"))
    if isinstance(value, dict):
        properties = schema.get("properties", {})
        for key in schema.get("required", []):
            if key not in value:
                errors.append(f"{path}.{key} is required")
        if schema.get("additionalProperties") is False:
            for key in sorted(set(value) - set(properties)):
                errors.append(f"{path}.{key} is not allowed")
        for key, child in properties.items():
            if key in value:
                errors.extend(schema_errors(value[key], child, root, f"{path}.{key}"))
    return errors


def validate_event(event: Any) -> list[str]:
    """Return schema errors plus forbidden key/value findings for one event."""

    schema = load_schema()
    return schema_errors(event, schema, schema) + scan_forbidden(event)


# --- Redaction of solo-empire system_health.full_health() --------------------

_GRADES = {"system_health": "system", "business_health": "business", "score": "overall"}
_CREDENTIALS = ("gmail", "calendar", "telegram")
_CRON_STATUSES = {"success", "failed", "running", "pending", "skipped"}
_JOB_TYPE = re.compile(r"[a-z][a-z0-9_]{0,63}")


def _utc(raw: Any, assume_tz: tzinfo) -> str | None:
    try:
        moment = datetime.fromisoformat(str(raw))
    except ValueError:
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=assume_tz)
    return moment.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _count(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value


def _section_ok(section: Any) -> bool:
    return isinstance(section, dict) and "error" not in section and not section.get("unavailable")


def _counts(section: Any, names: tuple[str, ...]) -> dict[str, Any]:
    out: dict[str, Any] = {"available": _section_ok(section)}
    if out["available"]:
        for name in names:
            count = _count(section.get(name))
            if count is not None:
                out[name] = count
    return out


def redact_health_snapshot(
    raw: dict[str, Any],
    *,
    service: str = "solo-empire-health",
    environment: str = "local",
    assume_tz: tzinfo | str = SYSTEM_HEALTH_TZ,
) -> dict[str, Any]:
    """Map a system_health ``full_health()`` payload onto the health_snapshot allow-list.

    Naive source timestamps are read in ``assume_tz`` (default Asia/Bangkok, the
    zone system_health.py runs in) and converted to UTC.

    Dropped on purpose: revenue amounts/displays/by_currency, goal/habit/task
    counts (personal productivity records), cron/freshness/alerts ``error``
    text, credential ``message``/``provider`` and any key not listed here.
    """

    if isinstance(assume_tz, str):
        assume_tz = ZoneInfo(assume_tz)
    if raw.get("schema_version") != "1.0":
        raise ValueError("unsupported system_health schema_version")
    observed_at = _utc(raw.get("timestamp"), assume_tz)
    if observed_at is None:
        raise ValueError("system_health timestamp is not ISO-8601")

    grades = {}
    for source_key, target_key in _GRADES.items():
        grade = raw[source_key]
        grades[target_key] = {
            "issues": _count(grade["issues"]) or 0,
            "checks": _count(grade["checks"]) or 0,
            "healthy": bool(grade["healthy"]),
            "grade": grade["grade"] if grade["grade"] in {"A", "B", "C", "D"} else "D",
        }

    cron_raw: Any = raw.get("cron")
    cron = _counts(cron_raw, ("total", "active", "success", "failed"))
    if cron["available"]:
        pending = _count(cron_raw.get("pending"))
        if pending is not None:
            cron["pending_jobs"] = pending
        cron["failed_jobs"] = [job for job in cron_raw.get("failed_jobs", []) if isinstance(job, str) and _JOB_TYPE.fullmatch(job)][:64]
        recent = []
        for item in cron_raw.get("recent", [])[:5]:
            if not isinstance(item, dict):
                continue
            job_type = item.get("job_type")
            if not isinstance(job_type, str) or not _JOB_TYPE.fullmatch(job_type):
                continue
            entry: dict[str, Any] = {
                "job_type": job_type,
                "status": item.get("status") if item.get("status") in _CRON_STATUSES else "unknown",
            }
            last_run = _utc(item.get("last_run"), assume_tz) if item.get("last_run") else None
            if last_run is not None:
                entry["last_run"] = last_run
            recent.append(entry)
        cron["recent"] = recent

    credentials_raw = raw.get("credentials") or {}
    credentials = {}
    for name in _CREDENTIALS:
        status = (credentials_raw.get(name) or {}).get("status")
        credentials[name] = {"status": status if status in {"configured", "not_configured"} else "error"}

    revenue = raw.get("revenue")
    return {
        "schema_version": SCHEMA_VERSION,
        "signal": "health_snapshot",
        "retention_class": "health-90d",
        "service": service,
        "environment": environment,
        "observed_at": observed_at,
        "source_schema_version": "1.0",
        "grades": grades,
        "sections": {
            "finance": {"available": isinstance(revenue, dict) and not revenue.get("unavailable")},
            "goals": {"available": _section_ok(raw.get("goals"))},
            "habits": {"available": _section_ok(raw.get("habits"))},
            "tasks": {"available": _section_ok(raw.get("tasks"))},
            "cron": cron,
            "freshness": _counts(raw.get("freshness"), ("ok", "stale", "missing")),
            "alerts": _counts(raw.get("alerts"), ("critical", "warnings", "info")),
            "credentials": credentials,
        },
    }


def _envelope(event: dict[str, Any], *, observed_at: str, service: str, environment: str, level: str, extra: dict[str, Any]) -> dict[str, Any]:
    clash = ENVELOPE_KEYS & set(event)
    if clash:
        raise ValueError(f"producer event sets envelope field(s) {sorted(clash)}")
    return {
        **event,
        **extra,
        "schema_version": SCHEMA_VERSION,
        "signal": "log",
        "retention_class": "log-14d",
        "service": service,
        "environment": environment,
        "observed_at": observed_at,
        "level": level,
    }


def _level(status: Any) -> str:
    return "error" if isinstance(status, int) and not isinstance(status, bool) and status >= 500 else "info"


def envelope_gateway_event(
    event: dict[str, Any],
    *,
    observed_at: str,
    service: str = "platform-api-gateway",
    environment: str = "local",
) -> dict[str, Any]:
    """Wrap a platform-api-gateway ``request.completed`` event without filtering it.

    Every gateway field is copied as-is, so a new or renamed gateway field fails
    validation instead of being silently dropped. A gateway field that collides
    with an envelope field is refused.
    """

    return _envelope(event, observed_at=observed_at, service=service, environment=environment,
                     level=_level(event.get("status")), extra={})


def envelope_access_log(line: dict[str, Any], *, observed_at: str, environment: str = "local") -> dict[str, Any]:
    """Wrap one PR #1 ``platform_observability`` access-log line (collector side).

    The line carries ``service`` itself and no ``event``/``level``; the collector
    adds the fixed event name ``http.request`` and derives ``level`` from status.
    All other fields are copied as-is.
    """

    body = {key: value for key, value in line.items() if key != "service"}
    if "event" in body or "level" in body:
        raise ValueError("access-log line unexpectedly carries event/level")
    return _envelope(body, observed_at=observed_at, service=line.get("service", ""), environment=environment,
                     level=_level(line.get("status")), extra={"event": "http.request"})


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) >= 2 and args[0] == "validate":
        failed = 0
        for name in args[1:]:
            errors = validate_event(json.loads(Path(name).read_text(encoding="utf-8")))
            for error in errors:
                print(f"FAIL {name}: {error}")
            failed += bool(errors)
            if not errors:
                print(f"OK {name}")
        return 1 if failed else 0
    if args and args[0] == "redact-health" and len(args) in {2, 4}:
        assume_tz = SYSTEM_HEALTH_TZ
        if len(args) == 4:
            if args[1] != "--assume-tz":
                print("usage: telemetry_policy.py redact-health [--assume-tz ZONE] RAW.json", file=sys.stderr)
                return 2
            assume_tz = args[2]
        event = redact_health_snapshot(json.loads(Path(args[-1]).read_text(encoding="utf-8")), assume_tz=assume_tz)
        print(json.dumps(event, indent=2, sort_keys=True))
        return 1 if validate_event(event) else 0
    print("usage: telemetry_policy.py validate EVENT.json [...] | redact-health [--assume-tz ZONE] RAW.json", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
