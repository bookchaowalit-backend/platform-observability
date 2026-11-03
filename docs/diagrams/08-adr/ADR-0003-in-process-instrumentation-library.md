# ADR-0003 — ส่งมอบเป็น in-process instrumentation library (Prometheus pull + OTLP push) ไม่ใช่ service

- **Status:** accepted (retro-documented)
- **วันที่:** PR #1 branch `codex/shared-infrastructure-20261015` (head `e2d1ab3`, 2026-10-15), merge เข้า main `47a91c1` (2026-10-23)

## Context

shared infrastructure design (architecture-docs 2026-10-15) ให้ platform-observability เป็นเจ้าของ "redacted telemetry defaults and collector/dashboard/alert configuration" สำหรับ shared APIs ที่ platform-infra-kit รัน

## Decision

- `instrument(app, ...)` เพิ่ม ASGI middleware `Observed` ใน FastAPI แต่ละตัว พร้อม `CollectorRegistry` และ `TracerProvider` แยกต่อ app
- metrics เป็น pull: `/metrics` ที่ต้องใช้ Bearer `METRICS_TOKEN`; labels จำกัดที่ service, method, route template, status
- traces เป็น push ไป OTLP/HTTP ที่ระบุชัด (HTTPS ยกเว้น loopback) ผ่าน `BoundedProcessor` + `SafeHTTPExporter` ที่จำกัด queue, timeout และไม่ log ข้อความจาก response/exception
- ไม่ record exception อัตโนมัติ; ห้าม inject exporter อื่นนอกจาก `InMemorySpanExporter`
- ใน repo ให้เพียง reference config (Prometheus k8s EndpointSlice, alert rules, RBAC) ไม่ deploy อะไร

## Consequences

- collector หลุด = telemetry หาย แต่ไม่ block request (`docs/shared-runtime.md`)
- ไม่มี Sentry ใน repo นี้ (waiver ใน `PRODUCT.md`)
- consumer ต้อง pin wheel ตาม source SHA (platform-infra-kit wheel manifest)

## Evidence

`src/platform_observability/middleware.py`, `src/platform_observability/export.py`, `docs/shared-runtime.md`, `config/*.yaml`, `runtime_tests/test_telemetry.py`, `PRODUCT.md`; architecture-docs [`docs/superpowers/reports/2026-10-15-shared-infrastructure-wheels.json`](https://github.com/bookchaowalit/architecture-docs/blob/main/docs/superpowers/reports/2026-10-15-shared-infrastructure-wheels.json)
