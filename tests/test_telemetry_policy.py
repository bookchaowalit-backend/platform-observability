"""BOO-160: redacted telemetry schema, forbidden fields, redaction and retention.

Offline by default. Two optional source-drift checks run when a local
checkout path is supplied (they are skipped in CI):

- SYSTEM_HEALTH_SOURCE=/path/to/system_health.py (solo-empire 99ddc05c^ or later)
- PLATFORM_API_GATEWAY_SRC=/path/to/platform-api-gateway/src (exercises the
  real gateway telemetry sink; CI checks out the public repo pinned at 6e1fb34
  and sets REQUIRE_GATEWAY_TESTS=1 so a missing checkout fails instead of skipping)

PR1RuntimeTelemetryTests run the real platform_observability.instrument() when
PR #1's package and its test dependencies (fastapi, opentelemetry-sdk,
prometheus-client) are importable, i.e. after PR #1 lands; skipped otherwise.
"""

from __future__ import annotations

import ast
import contextlib
import copy
import importlib.util
import io
import json
import os
import random
import re
import sys
import threading
import unittest
import uuid
from pathlib import Path
from typing import Any, ClassVar
from urllib.error import HTTPError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
_SPEC = importlib.util.spec_from_file_location("telemetry_policy", ROOT / "scripts" / "telemetry_policy.py")
assert _SPEC is not None and _SPEC.loader is not None
policy = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(policy)

FIXTURES = ROOT / "fixtures" / "telemetry"
GATE = json.loads((ROOT / "fixtures" / "gates" / "telemetry-redaction-retention.json").read_text(encoding="utf-8"))
SCHEMA = policy.load_schema()
SIGNALS = ("log", "metric", "trace", "health_snapshot")
RAW_HEALTH = json.loads((FIXTURES / "raw" / "system-health-full.synthetic.json").read_text(encoding="utf-8"))
INVENTORY = GATE["sources"]["system_health"]["fields"]


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _variant(signal: str) -> dict[str, Any]:
    return SCHEMA["$defs"][signal]


def _valid(name: str) -> dict[str, Any]:
    return _load(FIXTURES / "valid" / f"{name}.json")


def _get(value: Any, path: str) -> list[Any]:
    """Resolve a dotted path with ``[]`` list expansion; returns every match."""

    nodes = [value]
    for part in path.split("."):
        expand = part.endswith("[]")
        key = part[:-2] if expand else part
        nxt: list[Any] = []
        for node in nodes:
            if isinstance(node, dict) and key in node:
                child = node[key]
                if expand:
                    nxt.extend(child if isinstance(child, list) else [])
                else:
                    nxt.append(child)
        nodes = nxt
    return nodes


def _leaves(value: Any) -> list[Any]:
    if isinstance(value, dict):
        return [leaf for child in value.values() for leaf in _leaves(child)]
    if isinstance(value, list):
        return [leaf for child in value for leaf in _leaves(child)]
    return [value]


class SchemaShapeTests(unittest.TestCase):
    def test_schema_uses_only_keywords_the_validator_implements(self) -> None:
        unsupported: set[str] = set()

        def walk(node: Any, in_properties: bool = False) -> None:
            if isinstance(node, dict):
                for key, child in node.items():
                    if not in_properties and key not in policy.SUPPORTED_KEYWORDS:
                        unsupported.add(key)
                    if key == "x-forbidden":
                        continue
                    walk(child, key in {"properties", "$defs"} and not in_properties)
            elif isinstance(node, list):
                for child in node:
                    walk(child)

        walk(SCHEMA)
        self.assertEqual(unsupported, set())

    def test_every_signal_is_a_closed_oneof_branch(self) -> None:
        refs = [branch["$ref"] for branch in SCHEMA["oneOf"]]
        self.assertEqual(refs, [f"#/$defs/{signal}" for signal in SIGNALS])
        for signal in SIGNALS:
            variant = _variant(signal)
            self.assertIs(variant["additionalProperties"], False, signal)
            self.assertEqual(variant["properties"]["signal"]["const"], signal)
            for field in ("schema_version", "signal", "retention_class", "service", "environment", "observed_at"):
                self.assertIn(field, variant["required"], f"{signal} must require {field}")

    def test_no_object_anywhere_is_open(self) -> None:
        def walk(node: Any, path: str) -> None:
            if isinstance(node, dict):
                if node.get("type") == "object":
                    self.assertIs(node.get("additionalProperties"), False, f"{path} must be closed")
                for key, child in node.items():
                    walk(child, f"{path}/{key}")
            elif isinstance(node, list):
                for index, child in enumerate(node):
                    walk(child, f"{path}/{index}")

        walk(SCHEMA["$defs"], "#/$defs")

    def test_no_allowed_field_is_a_forbidden_key(self) -> None:
        def walk(node: Any, path: str) -> None:
            if isinstance(node, dict):
                for key in node.get("properties", {}):
                    self.assertFalse(policy.forbidden_key(key), f"{path}.{key} is allowed but forbidden")
                for key, child in node.items():
                    walk(child, f"{path}/{key}")

        walk(SCHEMA["$defs"], "#")

    def test_forbidden_value_patterns_compile(self) -> None:
        for name, pattern in SCHEMA["x-forbidden"]["value_patterns"].items():
            with self.subTest(name=name):
                re.compile(pattern)


class FixtureTests(unittest.TestCase):
    def test_valid_fixtures_pass(self) -> None:
        paths = sorted((FIXTURES / "valid").glob("*.json"))
        self.assertTrue(paths)
        seen = set()
        for path in paths:
            event = _load(path)
            seen.add(event["signal"])
            with self.subTest(fixture=path.name):
                self.assertEqual(policy.validate_event(event), [])
        self.assertEqual(seen, set(SIGNALS), "every signal needs a valid fixture")

    def test_invalid_fixtures_fail_for_the_stated_reason(self) -> None:
        paths = sorted((FIXTURES / "invalid").glob("*.json"))
        self.assertGreaterEqual(len(paths), 15)
        for path in paths:
            case = _load(path)
            with self.subTest(fixture=path.name):
                errors = policy.validate_event(case["event"])
                self.assertTrue(any(case["expect"] in error for error in errors), f"{case['expect']!r} not in {errors}")

    def test_invalid_fixtures_cover_every_signal(self) -> None:
        prefixes = {path.name.split("-")[0] for path in (FIXTURES / "invalid").glob("*.json")}
        self.assertEqual(prefixes, {"log", "metric", "trace", "health"})

    def test_cli_validate(self) -> None:
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(policy.main(["validate", str(FIXTURES / "valid" / "log-request-completed.json")]), 0)
            self.assertEqual(policy.main(["validate", str(FIXTURES / "invalid" / "log-free-text-message.json")]), 1)


class ForbiddenFieldTests(unittest.TestCase):
    SAMPLES: ClassVar[dict[str, str]] = {
        "email": "synthetic.person@example.invalid",
        "bearer_token": "Bearer synthetic0123456789token",
        "basic_auth": "Basic c3ludGhldGljOnN5bnRoZXRpYw==",
        "telegram_bot_token": "123456789:AAHdqTcvCH1vGWJxfSeofSAs0K5PALDsaw",
        "thai_phone": "081-234-5678",
        "grouped_number": "4111 1111 1111 1111",
        "jwt": "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJzeW50aGV0aWMifQ.c2ln",
        "provider_key": "sk_live_SYNTHETIC0123456789",
        "private_key": "-----BEGIN RSA PRIVATE KEY-----",
        "ipv4": "203.0.113.7",
        "ipv6": "2001:db8::42",
        "currency_amount": "฿125,000",
        "phone": "+66 81 234 5678",
        "long_digit_run": "4111111111111111",
        "url": "https://example.invalid/callback?code=synthetic",
    }

    def test_every_value_pattern_has_a_sample(self) -> None:
        self.assertEqual(set(self.SAMPLES), set(SCHEMA["x-forbidden"]["value_patterns"]))

    def test_samples_are_flagged_in_any_string_field(self) -> None:
        base = _valid("log-request-completed")
        for name, sample in self.SAMPLES.items():
            for field in ("request_id", "route", "event", "service"):
                with self.subTest(pattern=name, field=field):
                    event = dict(base, **{field: sample})
                    errors = policy.validate_event(event)
                    self.assertIn(f"$.{field}: forbidden value ({name})", errors)

    EXTRA_SAMPLES = (
        ("provider_key", "sk-ant-api03-SYNTHETICsyntheticSYNTHETIC0123"),
        ("provider_key", "sk-proj-SYNTHETICsyntheticSYNTHETIC0123"),
        ("provider_key", "ya29.a0SYNTHETICsyntheticToken0123"),
        ("thai_phone", "0812345678"),
        ("thai_phone", "66812345678"),
        ("phone", "+66812345678"),
        ("phone", "+66 81 234 5678"),
        ("grouped_number", "4111-1111-1111-1111"),
        ("grouped_number", "1-2345-67890-12-3"),
        ("email", "synthetic.user%40example.invalid"),
        ("url", "www.example.invalid"),
        ("url", "example.com/callback"),
    )

    def test_extra_samples_are_flagged(self) -> None:
        for name, sample in self.EXTRA_SAMPLES:
            with self.subTest(sample=sample):
                self.assertIn(f"$.x: forbidden value ({name})", policy.scan_forbidden({"x": sample}))

    def test_amounts_with_currency_codes_are_flagged(self) -> None:
        for sample in ("1,250.00 THB", "$40", "99 USD", "THB 1,250", "1,250\u0e3f", "40 usd", "500 baht"):
            with self.subTest(sample=sample):
                self.assertIn("$.x: forbidden value (currency_amount)", policy.scan_forbidden({"x": sample}))

    def test_every_forbidden_key_is_rejected_at_top_level_and_nested(self) -> None:
        log = _valid("log-request-completed")
        metric = _valid("metric-requests-total")
        trace = _valid("trace-server-span")
        for key in SCHEMA["x-forbidden"]["keys"]:
            with self.subTest(key=key):
                errors = policy.validate_event(dict(log, **{key: "x"}))
                self.assertIn(f"$.{key}: forbidden key", errors)
                self.assertIn(f"$.{key} is not allowed", errors)
                labelled = copy.deepcopy(metric)
                labelled["labels"][key] = "x"
                self.assertIn(f"$.labels.{key}: forbidden key", policy.validate_event(labelled))
                attributed = copy.deepcopy(trace)
                attributed["attributes"][key] = "x"
                self.assertIn(f"$.attributes.{key}: forbidden key", policy.validate_event(attributed))

    def test_key_normalisation_catches_spelling_variants(self) -> None:
        for key in ("Net-Peer-IP", "net_peer_ip", "HTTP.URL", "Set-Cookie", "API-Key", "accessToken", "sessionId",
                    "clientIp", "user_email", "x-api-key", "enduser.id", "jwt", "X-Forwarded-For", "refreshToken",
                    "credit_card", "creditCard", "cvv"):
            with self.subTest(key=key):
                self.assertTrue(policy.scan_forbidden({key: "x"}))

    def test_valid_fixtures_have_no_false_positives(self) -> None:
        for path in sorted((FIXTURES / "valid").glob("*.json")):
            with self.subTest(fixture=path.name):
                self.assertEqual(policy.scan_forbidden(_load(path)), [])

    def test_raw_numeric_amount_cannot_ride_in_a_metric_named_like_finance(self) -> None:
        for name in ("revenue_received", "pending_amount_thb", "Customer_Balance", "REVENUE_TOTAL"):
            with self.subTest(name=name):
                event = dict(_valid("metric-requests-total"), name=name)
                self.assertIn("$.name matches a disallowed pattern", policy.validate_event(event))


class NoFalsePositiveTests(unittest.TestCase):
    """Legitimate telemetry must not be rejected by the value scan (round-2 review)."""

    N = 20_000
    PR1_LINE = _load(FIXTURES / "raw" / "pr1-access-log.synthetic.json")["lines"][0]

    def test_reviewer_uuid_with_all_digit_tail(self) -> None:
        line = dict(self.PR1_LINE, correlation_id="26980061-e670-49ba-8e17-141944054981")
        self.assertEqual(policy.validate_event(policy.envelope_access_log(line, observed_at="2026-10-15T08:00:00Z")), [])

    def test_random_uuid4_correlation_and_request_ids_pass(self) -> None:
        rng = random.Random(160)
        request_schema = _variant("log")["properties"]["request_id"]
        failures = []
        for index in range(self.N):
            value = uuid.UUID(int=rng.getrandbits(128), version=4)
            if index % 4 == 0:  # force the worst case: an all-digit last group
                value = uuid.UUID(str(value)[:24] + "".join(rng.choice("0123456789") for _ in range(12)))
            line = dict(self.PR1_LINE, correlation_id=str(value))
            if policy.scan_forbidden(policy.envelope_access_log(line, observed_at="2026-10-15T08:00:00Z")):
                failures.append(str(value))
            for request_id in (value.hex, str(value)):
                if policy.scan_forbidden({"request_id": request_id}) or policy.schema_errors(request_id, request_schema, SCHEMA):
                    failures.append(request_id)
        self.assertEqual(failures[:5], [])

    def test_random_span_and_trace_ids_pass(self) -> None:
        rng = random.Random(161)
        base = _valid("trace-server-span")
        failures = []
        for index in range(self.N):
            alphabet = "0123456789" if index % 4 == 0 else "0123456789abcdef"
            span_id = "".join(rng.choice(alphabet) for _ in range(16))
            trace_id = "".join(rng.choice(alphabet) for _ in range(32))
            event = dict(base, span_id=span_id, parent_span_id=span_id[::-1], trace_id=trace_id)
            if policy.scan_forbidden(event):
                failures.append(span_id)
        self.assertEqual(failures[:5], [])
        self.assertEqual(policy.validate_event(dict(base, span_id="2658756600664653")), [])

    def test_unpinned_value_in_a_pinned_field_is_still_scanned(self) -> None:
        errors = policy.validate_event(dict(_valid("log-request-completed"), request_id="203.0.113.7"))
        self.assertIn("$.request_id: forbidden value (ipv4)", errors)

    def test_dotted_identifiers_and_routes_are_not_urls_or_amounts(self) -> None:
        log = _valid("log-request-completed")
        metric = _valid("metric-requests-total")
        cases = [("service", s) for s in ("platform.app", "media.io", "shared-api.dev", "catalog.ai", "notify.me", "data.co")]
        cases += [("event", e) for e in ("sync.app.started", "model.ai.inference", "auth.me.lookup", "storage.io.error")]
        cases += [("route", r) for r in ("/api/config.io", "/api/rates/usd1", "/api/v1/usd2thb", "/sk-test-endpoint-fixture",
                                          "/.well-known/health")]
        for field, value in cases:
            with self.subTest(field=field, value=value):
                self.assertEqual(policy.validate_event(dict(log, **{field: value})), [])
        labels = {"job": ("kubernetes.io", "prometheus.io"), "mountpoint": ("/mnt/data.io",), "model_name": ("ranker.ai",)}
        for label, values in labels.items():
            for value in values:
                with self.subTest(label=label, value=value):
                    event = copy.deepcopy(metric)
                    event["labels"][label] = value
                    self.assertEqual(policy.validate_event(event), [])


class HealthRedactionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.redacted = policy.redact_health_snapshot(copy.deepcopy(RAW_HEALTH))

    def test_redacted_snapshot_is_schema_valid(self) -> None:
        self.assertEqual(policy.validate_event(self.redacted), [])

    def test_redacted_snapshot_matches_committed_fixture(self) -> None:
        self.assertEqual(self.redacted, _valid("health-snapshot"))

    def test_raw_fixture_contains_what_must_be_removed(self) -> None:
        # Guard: the raw fixture must keep exercising every redaction rule.
        self.assertTrue(policy.scan_forbidden(RAW_HEALTH))
        self.assertIn("received", RAW_HEALTH["revenue"])
        self.assertIn("error", RAW_HEALTH["freshness"])
        self.assertIn("provider", RAW_HEALTH["credentials"]["calendar"])

    def test_dropped_values_never_reach_the_output(self) -> None:
        leaves = _leaves(self.redacted)
        rendered = json.dumps(self.redacted, ensure_ascii=False)
        for field in INVENTORY:
            if field["disposition"] != "drop":
                continue
            for value in _get(RAW_HEALTH, field["path"]):
                for leaf in _leaves(value):
                    with self.subTest(path=field["path"], value=leaf):
                        if isinstance(leaf, str):
                            self.assertNotIn(leaf, rendered)
                        elif isinstance(leaf, float):
                            self.assertNotIn(leaf, leaves)

    def test_kept_and_transformed_fields_reach_their_target(self) -> None:
        for field in INVENTORY:
            if field["disposition"] == "drop":
                continue
            if not _get(RAW_HEALTH, field["path"]):
                continue  # e.g. freshness counts when the raw section is an error
            with self.subTest(path=field["path"]):
                self.assertTrue(_get(self.redacted, field["target"]), f"{field['target']} missing")

    def test_every_raw_field_has_a_disposition(self) -> None:
        inventory = {field["path"] for field in INVENTORY}
        unmapped: list[str] = []

        def walk(node: Any, path: str) -> None:
            if path in inventory:
                return
            if isinstance(node, dict):
                for key, child in node.items():
                    walk(child, f"{path}.{key}" if path else key)
            elif isinstance(node, list):
                for child in node:
                    walk(child, f"{path}[]")
            else:
                unmapped.append(path)

        walk(RAW_HEALTH, "")
        self.assertEqual(unmapped, [])

    def test_section_errors_become_unavailable_without_text(self) -> None:
        raw = copy.deepcopy(RAW_HEALTH)
        raw["cron"] = {"error": "connection to 10.0.0.9 refused for synthetic@example.invalid"}
        raw["alerts"] = {"error": "alerts.py not found"}
        event = policy.redact_health_snapshot(raw)
        self.assertEqual(event["sections"]["cron"], {"available": False})
        self.assertEqual(event["sections"]["alerts"], {"available": False})
        self.assertEqual(policy.validate_event(event), [])

    def test_naive_source_time_is_read_as_bangkok_by_default(self) -> None:
        self.assertEqual(self.redacted["observed_at"], "2026-10-15T08:00:00Z")
        # The snapshot must not claim to be observed before or long after its latest job run.
        latest = max(item["last_run"] for item in self.redacted["sections"]["cron"]["recent"])
        self.assertLessEqual(latest, self.redacted["observed_at"])
        from datetime import datetime

        gap = datetime.fromisoformat(self.redacted["observed_at"]) - datetime.fromisoformat(latest)
        self.assertLess(gap.total_seconds(), 3600)

    def test_assume_tz_can_be_overridden(self) -> None:
        event = policy.redact_health_snapshot(copy.deepcopy(RAW_HEALTH), assume_tz="UTC")
        self.assertEqual(event["observed_at"], "2026-10-15T15:00:00Z")

    def test_cli_redact_health_with_assume_tz(self) -> None:
        raw = str(FIXTURES / "raw" / "system-health-full.synthetic.json")
        for args, expected in ((["redact-health", raw], "2026-10-15T08:00:00Z"),
                               (["redact-health", "--assume-tz", "UTC", raw], "2026-10-15T15:00:00Z")):
            buffer = io.StringIO()
            with self.subTest(args=args), contextlib.redirect_stdout(buffer):
                self.assertEqual(policy.main(args), 0)
            self.assertEqual(json.loads(buffer.getvalue())["observed_at"], expected)

    def test_non_dict_recent_items_are_skipped(self) -> None:
        raw = copy.deepcopy(RAW_HEALTH)
        raw["cron"]["recent"].insert(0, "synthetic string row")
        self.assertEqual(policy.validate_event(policy.redact_health_snapshot(raw)), [])

    def test_offset_timestamps_are_normalised_to_utc(self) -> None:
        raw = dict(copy.deepcopy(RAW_HEALTH), timestamp="2026-10-15T22:00:00+07:00")
        self.assertEqual(policy.redact_health_snapshot(raw)["observed_at"], "2026-10-15T15:00:00Z")

    def test_unknown_source_version_is_refused(self) -> None:
        with self.assertRaises(ValueError):
            policy.redact_health_snapshot(dict(RAW_HEALTH, schema_version="2.0"))


class PR1AccessLogShapeTests(unittest.TestCase):
    """PR #1 access-log lines (synthetic, modelled on its real output) validate after the collector envelope."""

    def test_pr1_lines_validate_after_envelope(self) -> None:
        raw = _load(FIXTURES / "raw" / "pr1-access-log.synthetic.json")
        self.assertEqual({key for line in raw["lines"] for key in line},
                         set(GATE["sources"]["pr1_access_log_reference"]["fields"]))
        for line in raw["lines"]:
            with self.subTest(route=line["route"]):
                event = policy.envelope_access_log(line, observed_at="2026-10-15T08:00:00Z")
                self.assertEqual(policy.validate_event(event), [])
                self.assertEqual(event["level"], "error" if line["status"] >= 500 else "info")

    def test_committed_access_log_fixture_is_adapter_output(self) -> None:
        line = _load(FIXTURES / "raw" / "pr1-access-log.synthetic.json")["lines"][0]
        self.assertEqual(policy.envelope_access_log(line, observed_at="2026-10-15T08:00:00Z"), _valid("log-access-middleware"))

    def test_starlette_route_templates_are_accepted_and_raw_paths_are_not(self) -> None:
        route = SCHEMA["$defs"]["route"]
        for good in ("/api/items/{item_id:int}", "/api/files/{path:path}", "/api/v1/things/", "/.well-known/health",
                     "unmatched", "/", "/v1/runs/{run_id}"):
            with self.subTest(route=good):
                self.assertEqual(policy.schema_errors(good, route, SCHEMA), [])
        for bad in ("/api/items/42", "/api/items/42/", "/v1/runs?owner=x", "api/items", "/api/{Item Id}", "//"):
            with self.subTest(route=bad):
                self.assertTrue(policy.schema_errors(bad, route, SCHEMA))

    def test_envelope_fields_cannot_be_overridden_by_producers(self) -> None:
        with self.assertRaises(ValueError):
            policy.envelope_gateway_event({"event": "request.completed", "signal": "metric"}, observed_at="2026-10-15T08:00:00Z")
        with self.assertRaises(ValueError):
            policy.envelope_access_log({"service": "media", "retention_class": "health-90d"}, observed_at="2026-10-15T08:00:00Z")


class OwnerDecisionTests(unittest.TestCase):
    """The owner accepted the BOO-160 decision on 2026-10-16; G10 and other gaps stay open."""

    DOC = ROOT / "docs" / "gates" / "BOO-160-telemetry-redaction-retention.md"
    MARKER = "## Owner decision \u2014 ACCEPTED (owner decision 2026-10-16)"
    VERBATIM = "\u0e17\u0e31\u0e49\u0e07\u0e2b\u0e21\u0e14 \u0e22\u0e01\u0e40\u0e27\u0e49\u0e19 140/256 (Recommended)"

    def test_fixture_records_accepted_decision_with_date(self) -> None:
        decision = GATE.get("owner_decision", {})
        self.assertEqual(GATE["status"], "accepted")
        self.assertEqual(decision.get("status"), "accepted")
        self.assertEqual(decision.get("date"), "2026-10-16")
        self.assertEqual(decision.get("verbatim"), self.VERBATIM)
        self.assertTrue(decision.get("relayed_via"))

    def test_undecided_items_remain_open(self) -> None:
        still_open = " ".join(GATE["owner_decision"]["still_open"])
        for gap in ("G10", "G5", "G6"):
            self.assertIn(gap, still_open)

    def test_accepted_retention_days(self) -> None:
        days = {row["signal"]: row["proposed_days"] for row in GATE["retention"]}
        self.assertEqual(days, {"metric": 30, "log": 14, "trace": 7, "health_snapshot": 90})

    def test_doc_carries_accepted_marker_and_verbatim_answer(self) -> None:
        text = self.DOC.read_text(encoding="utf-8")
        self.assertIn(self.MARKER, text)
        self.assertIn(self.VERBATIM, text)
        self.assertNotIn("PROPOSED, NOT ACCEPTED", text)
        self.assertIn("G10", text.split(self.MARKER, 1)[1])

    def test_schema_status_is_accepted(self) -> None:
        self.assertEqual(SCHEMA["x-status"], "accepted-2026-10-16")


class RetentionTests(unittest.TestCase):
    def test_one_retention_row_per_signal_matching_the_schema_class(self) -> None:
        rows = {row["signal"]: row for row in GATE["retention"]}
        self.assertEqual(set(rows), set(SIGNALS))
        for signal in SIGNALS:
            with self.subTest(signal=signal):
                row = rows[signal]
                self.assertEqual(row["retention_class"], _variant(signal)["properties"]["retention_class"]["const"])
                self.assertTrue(row["retention_class"].endswith(f"-{row['proposed_days']}d"))
                self.assertGreater(row["proposed_days"], 0)
                self.assertLessEqual(row["purge_sla_hours"], 24)
                self.assertEqual(row["backup"], "excluded")
                self.assertTrue(row["current"]["source"])

    def test_high_risk_signals_are_short_lived(self) -> None:
        rows = {row["signal"]: row for row in GATE["retention"]}
        self.assertLessEqual(rows["log"]["proposed_days"], 30)
        self.assertLessEqual(rows["trace"]["proposed_days"], rows["log"]["proposed_days"])

    def test_metric_retention_covers_widest_dashboard_window(self) -> None:
        rows = {row["signal"]: row for row in GATE["retention"]}
        widest = max(max(c.get("windows_days", [0])) for c in GATE["dashboard_consumers"])
        self.assertGreaterEqual(rows["metric"]["proposed_days"], widest)


class DashboardConsumerTests(unittest.TestCase):
    def test_grafana_labels_are_allowed_metric_labels(self) -> None:
        allowed = set(_variant("metric")["properties"]["labels"]["properties"])
        for consumer in GATE["dashboard_consumers"]:
            for label in consumer.get("labels", []):
                with self.subTest(label=label):
                    self.assertIn(label, allowed)

    def test_grafana_metric_names_are_allowed(self) -> None:
        base = _valid("metric-requests-total")
        for consumer in GATE["dashboard_consumers"]:
            for name in consumer.get("metrics", []):
                with self.subTest(metric=name):
                    self.assertEqual(policy.validate_event(dict(base, name=name)), [])


def _dict_keys(node: ast.AST) -> set[str]:
    keys: set[str] = set()
    for child in ast.walk(node):
        if isinstance(child, ast.Dict):
            keys.update(k.value for k in child.keys if isinstance(k, ast.Constant) and isinstance(k.value, str))
    return keys


@unittest.skipUnless(os.environ.get("SYSTEM_HEALTH_SOURCE"), "set SYSTEM_HEALTH_SOURCE to a system_health.py to check source drift")
class SystemHealthSourceDriftTests(unittest.TestCase):
    """Every key the real producer emits must have a disposition in the gate fixture."""

    def test_inventory_covers_every_emitted_key(self) -> None:
        tree = ast.parse(Path(os.environ["SYSTEM_HEALTH_SOURCE"]).read_text(encoding="utf-8"))
        functions = {node.name: node for node in tree.body if isinstance(node, ast.FunctionDef)}
        segments_by_section: dict[str, set[str]] = {}
        for field in INVENTORY:
            head, _, rest = field["path"].partition(".")
            segments_by_section.setdefault(head, set()).update(part.rstrip("[]") for part in rest.split(".") if part)

        # full_health(): {'section': collect_x()} plus health['grade'] = {...}
        full = functions["full_health"]
        missing: list[str] = []
        for node in ast.walk(full):
            if isinstance(node, ast.Assign) and isinstance(node.value, ast.Dict):
                target = node.targets[0]
                if isinstance(target, ast.Name) and target.id == "health":
                    for key, value in zip(node.value.keys, node.value.values):
                        section = key.value
                        if section not in segments_by_section:
                            missing.append(section)
                            continue
                        if isinstance(value, ast.Call) and isinstance(value.func, ast.Name) and value.func.id in functions:
                            for emitted in _dict_keys(functions[value.func.id]) - segments_by_section[section]:
                                missing.append(f"{section}.{emitted}")
                elif isinstance(target, ast.Subscript) and isinstance(target.slice, ast.Constant):
                    section = target.slice.value
                    for emitted in _dict_keys(node.value) - segments_by_section.get(section, set()):
                        missing.append(f"{section}.{emitted}")
        self.assertEqual(missing, [], "system_health emits fields with no redaction disposition")


class GatewayRequirementTests(unittest.TestCase):
    def test_gateway_checkout_present_when_required(self) -> None:
        if os.environ.get("REQUIRE_GATEWAY_TESTS") != "1":
            self.skipTest("REQUIRE_GATEWAY_TESTS is not set")
        source = os.environ.get("PLATFORM_API_GATEWAY_SRC", "")
        self.assertTrue(source and (Path(source) / "book_api_gateway" / "server.py").is_file(),
                        "REQUIRE_GATEWAY_TESTS=1 but PLATFORM_API_GATEWAY_SRC is not a platform-api-gateway src dir")


@unittest.skipUnless(os.environ.get("PLATFORM_API_GATEWAY_SRC"), "set PLATFORM_API_GATEWAY_SRC to exercise the real gateway telemetry")
class GatewayTelemetryTests(unittest.TestCase):
    """Run platform-api-gateway's real request path and validate its telemetry events."""

    def setUp(self) -> None:
        sys.path.insert(0, os.environ["PLATFORM_API_GATEWAY_SRC"])
        from book_api_gateway.config import GatewayConfig
        from book_api_gateway.server import create_server

        self.events: list[dict[str, Any]] = []
        config = GatewayConfig(api_token="synthetic-gateway-token", upstream_base_url="http://127.0.0.1:9", upstream_timeout_seconds=0.2)
        self.server = create_server(config, telemetry_sink=self.events.append)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.base = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        sys.path.remove(os.environ["PLATFORM_API_GATEWAY_SRC"])

    def _call(self, path: str, headers: dict[str, str]) -> dict[str, Any]:
        before = len(self.events)
        try:
            urlopen(Request(self.base + path, headers=headers), timeout=5).read()
        except HTTPError as exc:
            with exc:
                exc.read()
        for _ in range(200):
            if len(self.events) > before:
                break
            threading.Event().wait(0.01)
        return policy.envelope_gateway_event(self.events[-1], observed_at="2026-10-15T08:00:00Z")

    def test_real_gateway_events_are_schema_valid(self) -> None:
        for path, headers in (
            ("/healthz", {}),
            ("/api/demo", {"Authorization": "Bearer synthetic-gateway-token"}),
            ("/api/demo", {"Authorization": "Bearer wrong-token"}),
        ):
            with self.subTest(path=path, auth=bool(headers)):
                event = self._call(path, headers)
                self.assertEqual(policy.validate_event(event), [])
                self.assertNotIn("synthetic-gateway-token", json.dumps(event))

    def test_gateway_field_set_matches_gate_inventory(self) -> None:
        event = self._call("/api/demo", {"Authorization": "Bearer synthetic-gateway-token"})
        emitted = set(event) - {"schema_version", "signal", "retention_class", "service", "environment", "observed_at", "level"}
        documented = {field["path"] for field in GATE["sources"]["gateway_request_completed"]["fields"]}
        self.assertEqual(emitted, documented)

    def test_client_supplied_ip_request_id_is_caught(self) -> None:
        # Gap G5: REQUEST_ID_RE accepts an IPv4 literal; only the value scan stops it.
        event = self._call("/healthz", {"X-Request-ID": "203.0.113.7"})
        self.assertEqual(event["request_id"], "203.0.113.7")
        errors = policy.validate_event(event)
        self.assertIn("$.request_id: forbidden value (ipv4)", errors)
        self.assertTrue(any(error.startswith("$.request_id does not match pattern") for error in errors))


def _pr1_runtime_available() -> bool:
    if not (ROOT / "src" / "platform_observability" / "__init__.py").is_file():
        return False
    return all(importlib.util.find_spec(name) is not None
               for name in ("fastapi", "httpx", "prometheus_client", "opentelemetry.sdk"))


@unittest.skipUnless(_pr1_runtime_available(), "PR #1 runtime (src/platform_observability + fastapi/otel/prometheus) not available")
class PR1RuntimeTelemetryTests(unittest.TestCase):
    """Validate the real output of platform_observability.instrument() (PR #1) against the schema."""

    ROUTES = ("/api/items/{item_id:int}", "/api/files/{path:path}", "/api/v1/things/", "/.well-known/health")

    def setUp(self) -> None:
        import logging

        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
            InMemorySpanExporter,
        )

        sys.path.insert(0, str(ROOT / "src"))
        self.addCleanup(sys.path.remove, str(ROOT / "src"))
        import platform_observability

        app = FastAPI()

        @app.get("/api/items/{item_id:int}")
        def item(item_id: int) -> dict[str, int]:
            return {"id": item_id}

        @app.get("/api/files/{path:path}")
        def files(path: str) -> dict[str, str]:
            return {"ok": "yes"}

        @app.post("/api/v1/things/")
        def things() -> dict[str, str]:
            return {"ok": "yes"}

        @app.get("/.well-known/health")
        def well_known() -> dict[str, str]:
            return {"ok": "yes"}

        self.exporter = InMemorySpanExporter()
        platform_observability.instrument(app, service_name="Shared_API", metrics_token="synthetic-metrics-token-0123",
                                          exporter=self.exporter)
        self.lines: list[dict[str, Any]] = []
        handler = logging.Handler()
        handler.emit = lambda record: self.lines.append(json.loads(record.getMessage()))  # type: ignore[method-assign]
        logger = logging.getLogger("platform_observability")
        logger.addHandler(handler)
        previous = logger.level
        logger.setLevel(logging.INFO)
        self.addCleanup(logger.removeHandler, handler)
        self.addCleanup(logger.setLevel, previous)
        with TestClient(app, raise_server_exceptions=False) as client:
            client.get("/api/items/42?email=synthetic%40example.invalid")
            client.get("/api/files/private/synthetic-customer.txt", headers={"Authorization": "Bearer synthetic-header"})
            client.post("/api/v1/things/", json={"amount": "THB 1,250"})
            client.get("/.well-known/health")
            client.get("/nope/12345")
            self.metrics = client.get("/metrics", headers={"Authorization": "Bearer synthetic-metrics-token-0123"}).text

    def test_access_log_lines_validate(self) -> None:
        self.assertEqual(len(self.lines), 5)
        for line in self.lines:
            with self.subTest(route=line.get("route")):
                event = policy.envelope_access_log(line, observed_at="2026-10-15T08:00:00Z")
                self.assertEqual(policy.validate_event(event), [])
        self.assertEqual({line["route"] for line in self.lines}, set(self.ROUTES) | {"unmatched"})

    def test_spans_validate(self) -> None:
        spans = self.exporter.get_finished_spans()
        self.assertEqual(len(spans), 5)
        for span in spans:
            attributes = {**dict(span.resource.attributes), **dict(span.attributes)}
            event = {
                "schema_version": policy.SCHEMA_VERSION, "signal": "trace", "retention_class": "trace-7d",
                "service": "Shared_API", "environment": "ci", "observed_at": "2026-10-15T08:00:00Z",
                "trace_id": format(span.context.trace_id, "032x"), "span_id": format(span.context.span_id, "016x"),
                "name": span.name, "kind": span.kind.name.lower(),
                "duration_seconds": (span.end_time - span.start_time) / 1e9,
                "status_code": span.status.status_code.name.lower(), "attributes": attributes,
            }
            with self.subTest(span=span.name):
                self.assertEqual(policy.validate_event(event), [])

    def test_metric_samples_validate_with_pod_instance(self) -> None:
        from prometheus_client.parser import text_string_to_metric_families

        types = {"_bucket": "histogram_bucket", "_sum": "histogram_sum", "_count": "histogram_count"}
        count = 0
        for family in text_string_to_metric_families(self.metrics):
            for sample in family.samples:
                kind = next((v for k, v in types.items() if sample.name.endswith(k)), "counter" if family.type == "counter" and sample.name.endswith("_total") else "gauge")
                labels = dict(sample.labels, job="shared-infra", instance="shared-api-7d9f8b6c5-x2x7q")
                event = {
                    "schema_version": policy.SCHEMA_VERSION, "signal": "metric", "retention_class": "metric-30d",
                    "service": "Shared_API", "environment": "ci", "observed_at": "2026-10-15T08:00:00Z",
                    "name": sample.name, "type": kind, "value": sample.value, "labels": labels,
                }
                with self.subTest(sample=sample.name, labels=sample.labels):
                    self.assertEqual(policy.validate_event(event), [])
                count += 1
        self.assertGreater(count, 10)
        for private in ("42", "synthetic-customer", "synthetic%40", "1,250", "12345"):
            self.assertNotIn(f'"{private}', self.metrics)


if __name__ == "__main__":
    unittest.main()
