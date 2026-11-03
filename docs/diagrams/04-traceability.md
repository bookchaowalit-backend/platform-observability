# 04 — Traceability (RTM)

ไม่มี `specs/` ใน repo requirement มาจาก `PRODUCT.md` (Measures, Capabilities), `contract.json` (`migration_gates`), gate doc BOO-160 และ `docs/shared-runtime.md`
release ของ repo นี้คือ "merge เข้า main ที่ Check เขียว" (ไม่มี deploy)

| ID | Requirement | แหล่ง | Code module | Test file | Release / workflow |
|---|---|---|---|---|---|
| R1 | `contract.json` valid กับ vendored schema | `PRODUCT.md` Measures | `scripts/check.py` | `tests/test_contract_check.py` | `check.yml` job `contract`, `offline` |
| R2 | vendored schema ตรงกับ sha256 pin | `PRODUCT.md` Capabilities | `scripts/check_schema_pin.py` | `tests/test_drift_checks.py` (`SchemaPinTests`) | `check.yml` step "Verify vendored schema" |
| R3 | drift contract ↔ registry = 0 | `PRODUCT.md` Measures | `scripts/check_registry_alignment.py` | `tests/test_drift_checks.py` (`RegistryAlignmentTests`) | local only (not in CI, `docs/UPGRADE-PLAN.md`) |
| R4 | README และ CONTRACT-SURFACE สอดคล้องกับ contract | `README.md` | `scripts/check.py` `_semantic_errors` | `tests/test_contract_check.py` | `check.yml` |
| R5 | gate "telemetry redaction": allow-list schema, ไม่มี free text | `contract.json` `migration_gates`; gate doc option 1 | `schema/telemetry/redacted-telemetry-event.v1.schema.json`, `scripts/telemetry_policy.py` | `tests/test_telemetry_policy.py` (`SchemaShapeTests`, `FixtureTests`, `ForbiddenFieldTests`, `NoFalsePositiveTests`) | PR #2 → `e1b2a86` |
| R6 | gate "retention policy": 30/14/7/90 days | gate doc option 2 | `fixtures/gates/telemetry-redaction-retention.json` | `tests/test_telemetry_policy.py` (`RetentionTests`, `OwnerDecisionTests`) | PR #3 → `99313d2` |
| R7 | health snapshot ตัดยอดเงินและข้อมูลส่วนตัว | gate doc option 3 | `scripts/telemetry_policy.py` `redact_health_snapshot` | `tests/test_telemetry_policy.py` (`HealthRedactionTests`) | `e1b2a86` |
| R8 | gateway `request.completed` ผ่าน schema | gate doc §Logs | `scripts/telemetry_policy.py` `envelope_gateway_event` | `tests/test_telemetry_policy.py` (`GatewayTelemetryTests`, `GatewayRequirementTests`) | `check.yml` job `contract` (gateway pinned `6e1fb34`) |
| R9 | metric labels bounded (service, method, route template, status) | `docs/shared-runtime.md` | `src/platform_observability/middleware.py` | `runtime_tests/test_telemetry.py` (`test_metrics_are_authenticated_and_use_route_templates`, `test_independent_apps_...`) | merge `47a91c1` |
| R10 | `/metrics` ต้องมี credential; ไม่มี = ปิด | `docs/shared-runtime.md` | `middleware.py` `Observed` | `runtime_tests/test_telemetry.py` (`test_missing_metrics_credential_disables_endpoint`, `test_non_ascii_metrics_authorization_...`) | `47a91c1` |
| R11 | span ไม่มี query/header/payload/exception text | `docs/shared-runtime.md` | `middleware.py` | `runtime_tests/test_telemetry.py` (`test_spans_exclude_...`, `test_valid_trace_context_...`) | `47a91c1` |
| R12 | export bounded: queue 512, batch 64, timeout 2s, shutdown 2.5s, ไม่มี diagnostics จาก response | `docs/shared-runtime.md` | `src/platform_observability/export.py` | `runtime_tests/test_telemetry.py` (`test_otlp_failure_diagnostics_...`, `test_batch_export_and_shutdown_are_bounded_...`, `test_arbitrary_synchronous_exporter_is_rejected`) | `47a91c1` |
| R13 | output จริงของ `instrument()` ผ่าน redaction schema | gate doc §PR #1 | `middleware.py` + `telemetry_policy.envelope_access_log` | `tests/test_telemetry_policy.py` (`PR1AccessLogShapeTests`, `PR1RuntimeTelemetryTests`) | `47a91c1` |
| R14 | workflow actions ถูก SHA pin | commit `5ca3296` | `.github/workflows/check.yml` | `tests/test_build_hygiene.py` | merge `60fac76` |
| R15 | coverage ≥ 90% | `check.yml` comment (ADR-0004 ratchet) | `src/`, `scripts/` | ทั้ง suite | `check.yml` job `offline` |
| R16 | gate "alert drill" | `contract.json` `migration_gates` | `config/shared-alerts.yaml` (reference only) | **ไม่มี** | ไม่มี |

Sources: `PRODUCT.md`, `contract.json`, `docs/UPGRADE-PLAN.md`, `docs/shared-runtime.md`, `docs/gates/BOO-160-telemetry-redaction-retention.md`, `scripts/*.py`, `src/platform_observability/*.py`, `tests/*.py`, `runtime_tests/test_telemetry.py`, `.github/workflows/check.yml`, `git log --first-parent origin/main`, `gh pr list`

## Open questions

- R16 alert drill ยังไม่มีหลักฐานหรือ test (`docs/shared-runtime.md`: "This change sends no notifications")
- R3 ไม่รันใน CI เพราะต้องใช้ solo-empire แบบ private: จะยอมรับเป็น local-only ต่อไปหรือไม่
