# 02 — Use cases

Actors คือผู้ที่เรียกใช้ library หรือ contract จริง: ไม่มี end user และไม่มี auth level แบบ role ในโค้ด
auth เดียวใน runtime คือ Bearer `METRICS_TOKEN` ที่ `/metrics` (`middleware.py`)

```mermaid
flowchart LR
  owner(["Owner / agent maintainer"])
  svc(["Consuming FastAPI service (via platform-infra-kit)"])
  prom(["Prometheus scraper (reference config)"])
  otlp(["OTLP/HTTP trace collector"])
  ci(["GitHub Actions CI"])
  client(["HTTP client of the consuming service"])

  subgraph lib["platform-observability"]
    UC1["UC1 Instrument an app: instrument(app, service_name, metrics_token, endpoint)"]
    UC2["UC2 Record request metrics with bounded labels"]
    UC3["UC3 Record server span from W3C traceparent"]
    UC4["UC4 Write one redacted JSON access log line"]
    UC5["UC5 Serve /metrics to an authenticated scraper"]
    UC6["UC6 Export spans with bounded queue and timeouts"]
    UC7["UC7 Validate a telemetry event against the redaction schema"]
    UC8["UC8 Redact a raw system_health snapshot"]
    UC9["UC9 Validate contract.json, schema pin and README agreement"]
    UC10["UC10 Compare contract with solo-empire registry (local only)"]
    UC11["UC11 Evaluate reference alert rules"]
  end

  svc --> UC1
  client --> UC2
  client --> UC3
  UC2 --> UC4
  prom --> UC5
  prom --> UC11
  UC6 --> otlp
  UC3 --> UC6
  owner --> UC7
  owner --> UC8
  owner --> UC10
  ci --> UC7
  ci --> UC9
```

| Actor | ระดับการเข้าถึงในโค้ด | หลักฐาน |
|---|---|---|
| Consuming service | เรียก `instrument()` ได้ครั้งเดียวต่อ app (`telemetry already configured`) | `src/platform_observability/middleware.py` |
| Prometheus scraper | ต้องส่ง `Authorization: Bearer <METRICS_TOKEN>`; ไม่มี token = `/metrics` 404, ผิด = 401 | `middleware.py`, `config/prometheus.yaml` |
| HTTP client | ไม่รู้ว่าถูก instrument; ส่ง `traceparent`/`tracestate` ได้ (≤512 bytes) | `middleware.py` |
| OTLP collector | รับ POST protobuf; ต้องเป็น HTTPS ยกเว้น loopback | `middleware.py`, `export.py` |
| Owner / CI | รัน `scripts/*.py` และ `bash scripts/check.sh` | `scripts/`, `.github/workflows/check.yml` |

Sources: `src/platform_observability/middleware.py`, `src/platform_observability/export.py`, `config/prometheus.yaml`, `config/shared-alerts.yaml`, `scripts/telemetry_policy.py`, `scripts/check.py`, `scripts/check_registry_alignment.py`, `docs/shared-runtime.md`

## Open questions

- consumer จริงใน production: ไม่พบ `platform_observability` import ใน platform-* repo อื่น (ค้นใน worktree ของ Core 22 batch) และ `PRODUCT.md` บอกว่ายังไม่มี service ใช้: ใครจะเป็น consumer แรก
