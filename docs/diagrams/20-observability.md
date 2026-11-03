# 20 — Observability

repo นี้ **ผลิต** observability ให้คนอื่น แต่ไม่มี runtime ของตัวเองจึงไม่มี Sentry (waiver ใน `PRODUCT.md`: "nothing is built into an image or deployed from this repository") ภาพแรกคือ signal ที่ library ปล่อยจริงและสิ่งที่ reference config เฝ้าดู ภาพที่สองคือสัญญาณของ repo เอง

## Signals ที่ library ผลิต

```mermaid
flowchart LR
  req["Request in consumer"] --> m1["platform_requests_total service, method, route, status"]
  req --> m2["platform_request_duration_seconds histogram"]
  req --> sp["Server span METHOD route, attrs http.request.method, http.route, http.response.status_code"]
  req --> lg["JSON log: service, method, route, status, duration_seconds, correlation_id, trace_id"]
  fail["Export failure"] --> lg2["telemetry_export_failed / telemetry_exporter_shutdown_failed"]
  m1 --> scrape["Prometheus job shared-infra, every 15s"]
  m2 --> scrape
  scrape --> a1["SharedServiceUnavailable: up == 0 for 2m, critical"]
  scrape --> a2["SharedServiceErrors: 5xx ratio > 5% for 5m, warning"]
  scrape --> a3["SharedServiceLatency: p95 > 1s for 5m, warning"]
  sp --> col["OTLP collector"]
  a1 --> rx["Receiver: none configured"]
  a2 --> rx
  a3 --> rx
```

## Signals ของ repo เอง

```mermaid
flowchart LR
  push["Push / PR"] --> chk["Check workflow result"]
  chk --> ghn["GitHub Actions run status and notifications"]
  chk --> cov["Coverage gate 90%"]
  chk --> secs["Security scan SARIF/summary"]
```

ไม่มี uptime target, heartbeat หรือ PostHog สำหรับ repo นี้ (ไม่มี URL); ops record book-platforms-status (2026-11-03) บันทึก Sentry/uptime สำหรับ 8 platform services ที่ live แต่ไม่รวม observability

Sources: `src/platform_observability/middleware.py`, `src/platform_observability/export.py`, `config/prometheus.yaml`, `config/shared-alerts.yaml`, `docs/shared-runtime.md`, `PRODUCT.md`, `.github/workflows/check.yml`

## Open questions

- thresholds ใน `shared-alerts.yaml` เป็น "staging drill thresholds, not a promised service level": SLO จริงคืออะไร
- dashboards ถูก defer โดย owner decision BOO-160 option 4
