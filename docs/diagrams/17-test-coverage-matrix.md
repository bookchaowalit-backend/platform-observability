# 17 — Test coverage matrix

ระดับ test ที่มีจริง: **unit** (`tests/`, unittest, ไม่มี third-party deps), **integration** (`runtime_tests/`, pytest + FastAPI `TestClient` บน `instrument()` จริง, และ gateway parity ที่ import `platform-api-gateway` จริงใน CI), **e2e** ไม่มี (ไม่มี hosted runtime) coverage gate 90% ใน job `offline`

| Feature | Unit | Integration | E2E | Test files |
|---|---|---|---|---|
| Contract schema validation, README/surface agreement | ✅ | - | - | `tests/test_contract_check.py` |
| Schema sha256 pin | ✅ | - | - | `tests/test_drift_checks.py` `SchemaPinTests` |
| Registry alignment | ✅ (synthetic registry) | - | - | `tests/test_drift_checks.py` `RegistryAlignmentTests` |
| Telemetry schema shape (closed objects, keyword set) | ✅ | - | - | `tests/test_telemetry_policy.py` `SchemaShapeTests` |
| Valid / invalid fixtures (13 / 45) | ✅ | - | - | `FixtureTests`, `ForbiddenFieldTests`, `NoFalsePositiveTests` |
| Health snapshot redaction | ✅ | local only (`SYSTEM_HEALTH_SOURCE`) | - | `HealthRedactionTests`, `SystemHealthSourceDriftTests` |
| Retention and owner decision record | ✅ | - | - | `RetentionTests`, `OwnerDecisionTests`, `DashboardConsumerTests` |
| Gateway `request.completed` parity | - | ✅ CI job `contract` | - | `GatewayTelemetryTests`, `GatewayRequirementTests` |
| `instrument()` output validates against schema | - | ✅ | - | `PR1RuntimeTelemetryTests`, `PR1AccessLogShapeTests` |
| `/metrics` auth (missing, wrong, non-ASCII) | - | ✅ | - | `runtime_tests/test_telemetry.py` |
| Route-template labels, per-app registries | - | ✅ | - | `runtime_tests/test_telemetry.py` |
| Span redaction, trace context | - | ✅ | - | `runtime_tests/test_telemetry.py` |
| Exporter failure diagnostics, bounded shutdown | - | ✅ | - | `runtime_tests/test_telemetry.py` |
| Workflow SHA pins, no Dockerfile | ✅ | - | - | `tests/test_build_hygiene.py` |
| Prometheus scrape config / alert rules | **gap** | **gap** | **gap** | ไม่มี (`docs/shared-runtime.md`: rule evaluation ต้องทดสอบกับ Prometheus binary ก่อน rollout) |
| Discovery RBAC | **gap** | **gap** | **gap** | ไม่มี |
| Alert drill (migration gate) | **gap** | **gap** | **gap** | ไม่มี |
| Real OTLP collector connectivity | - | **gap** | **gap** | ใช้ `httpx` transport mock เท่านั้น |

Sources: `tests/*.py`, `runtime_tests/test_telemetry.py`, `pyproject.toml` (`testpaths`, coverage `source`), `.github/workflows/check.yml`, `docs/gates/BOO-160-telemetry-redaction-retention.md` §Verification, `docs/shared-runtime.md`

## Open questions

- ไม่มี
