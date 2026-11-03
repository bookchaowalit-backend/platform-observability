# Core 22 SDLC diagram pack — platform-observability

ชุดภาพ Core 22 ตาม SDLC Diagram Catalog v2 วาดจากโค้ดและ config ใน repo นี้ (ณ `origin/main` `60fac76`, 2026-10-29; อ่านเมื่อ 2026-11-03)
repo นี้คือ **library + boundary contract** ของ capability `observability`: package `platform_observability` (`instrument(app, ...)`) ที่รันใน process ของ consumer, telemetry redaction policy (BOO-160) และ reference Prometheus config ไม่มี hosted runtime, database หรือ deploy ของตัวเอง

ทุกไฟล์มี `Sources:` ใต้ภาพ และ "Open questions" สำหรับสิ่งที่ยืนยันจากโค้ดไม่ได้

| # | Item | Status | File | Sources read |
|---|---|---|---|---|
| 01 | Business process As-Is / To-Be | done | [01-business-process.md](01-business-process.md) | `PRODUCT.md`, `README.md`, `contract.json`, `docs/UPGRADE-PLAN.md`, gate doc BOO-160 |
| 02 | Use cases | done | [02-use-cases.md](02-use-cases.md) | `src/platform_observability/*.py`, `config/*.yaml`, `scripts/*.py` |
| 03 | User flows | done | [03-user-flows.md](03-user-flows.md) | `middleware.py`, `docs/shared-runtime.md`, `scripts/check.sh`, `check.yml` |
| 04 | Traceability (RTM) | done | [04-traceability.md](04-traceability.md) | `PRODUCT.md`, `contract.json`, gate doc, `tests/`, `runtime_tests/`, `git log`, `gh pr list` |
| 05 | C4 Context | done | [05-c4-context.md](05-c4-context.md) | `README.md`, `contract.json`, `config/prometheus.yaml`, `check.yml`, architecture-docs shared-infra design |
| 06 | C4 Container | done | [06-c4-container.md](06-c4-container.md) | `pyproject.toml`, `src/`, `scripts/`, `schema/`, `config/` |
| 07 | C4 Component | done | [07-c4-component.md](07-c4-component.md) | `middleware.py`, `export.py`, `telemetry_policy.py` |
| 08 | ADRs | done (4) | [08-adr/](08-adr/) | `contract.json`, gate doc, `src/`, `check.yml`, `git log` |
| 09 | ERD | done (logical schema model, no DB) | [09-erd.md](09-erd.md) | `schema/telemetry/redacted-telemetry-event.v1.schema.json`, contract schema, `middleware.py` |
| 10 | Sequences | done | [10-sequences.md](10-sequences.md) | `middleware.py`, `export.py`, `config/prometheus.yaml`, `check.yml`, `tests/test_telemetry_policy.py` |
| 11 | State machines | done | [11-state-machines.md](11-state-machines.md) | `export.py`, contract schema `status` enum, gate fixture |
| 12 | API & integrations | done (+ reused [`docs/CONTRACT-SURFACE.md`](../CONTRACT-SURFACE.md)) | [12-api-integration.md](12-api-integration.md) | `middleware.py`, `export.py`, `scripts/`, `contract.json` |
| 13 | Threat model | done | [13-threat-model.md](13-threat-model.md) | `src/`, `config/discovery-rbac.yaml`, gate doc §Gaps, `check.yml`, `.gitleaksignore` |
| 14 | Backup & DR | done (Git only; telemetry excluded from backups by policy) | [14-backup-dr.md](14-backup-dr.md) | `docs/shared-runtime.md`, gate doc §Retention, shared-infra verification report |
| 15 | CI/CD pipeline | done | [15-cicd-pipeline.md](15-cicd-pipeline.md) | `.github/workflows/check.yml`, platform-ci-workflows `ci-python.yml` / `security.yml` @ `87dc5e1`, `gh run list` |
| 16 | Deployment | done (library pin/install, reference k8s) | [16-deployment.md](16-deployment.md) | `pyproject.toml`, `config/*.yaml`, `docs/shared-runtime.md`, shared-infra wheels report |
| 17 | Test coverage matrix | done | [17-test-coverage-matrix.md](17-test-coverage-matrix.md) | `tests/*.py`, `runtime_tests/test_telemetry.py`, `pyproject.toml` |
| 18 | Git & release workflow | done | [18-git-release-workflow.md](18-git-release-workflow.md) | `git log --first-parent`, `gh pr list`, `gh run list` |
| 19 | Service dependency map | done | [19-service-dependency-map.md](19-service-dependency-map.md) | `contract.json`, `pyproject.toml`, `uv.lock`, `check.yml` |
| 20 | Observability | done (+ reused [`docs/shared-runtime.md`](../shared-runtime.md)) | [20-observability.md](20-observability.md) | `middleware.py`, `export.py`, `config/shared-alerts.yaml`, `PRODUCT.md` |
| 21 | Incident response | done (CI flow real; alert flow design-only, no receiver) | [21-incident-response.md](21-incident-response.md) | `config/shared-alerts.yaml`, `docs/shared-runtime.md`, `gh run list` |
| 22 | DORA | done (5/5 computed as main-branch proxies; no deploys) | [22-dora.md](22-dora.md) | `git log`, `gh run list`, `gh pr list` |

## ADR list

- [ADR-0001](08-adr/ADR-0001-boundary-contract-repo-before-runtime.md) Boundary contract repo ก่อนย้าย runtime
- [ADR-0002](08-adr/ADR-0002-allow-list-telemetry-schema-and-retention.md) Allow-list telemetry schema และ retention 30/14/7/90 วัน
- [ADR-0003](08-adr/ADR-0003-in-process-instrumentation-library.md) In-process instrumentation library (Prometheus pull + OTLP push)
- [ADR-0004](08-adr/ADR-0004-shared-ci-uv-lock-and-sha-pins.md) Shared CI, uv lock, SHA pins, coverage gate 90%

## Reused docs

- [`docs/CONTRACT-SURFACE.md`](../CONTRACT-SURFACE.md) — interface list และ behaviour notes
- [`docs/shared-runtime.md`](../shared-runtime.md) — runtime telemetry design
- [`docs/gates/BOO-160-telemetry-redaction-retention.md`](../gates/BOO-160-telemetry-redaction-retention.md) — gate evidence, retention, gaps G1–G10
- [`docs/UPGRADE-PLAN.md`](../UPGRADE-PLAN.md) — backlog (To-Be)
