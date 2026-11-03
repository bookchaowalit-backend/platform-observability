# 16 — Deployment

repo นี้ **ไม่มี hosted runtime** (ไม่มี Dockerfile, Railway, Vercel หรือ Worker config; `tests/test_build_hygiene.py` ยืนยันว่าไม่มี Dockerfile) "deployment" คือการที่ consumer ติดตั้ง wheel ที่ pin ตาม source SHA และ reference config สำหรับ Kubernetes staging

```mermaid
flowchart TD
  subgraph gh["GitHub: bookchaowalit-backend/platform-observability (public)"]
    main["main 60fac76"]
    pr1["PR 1 head e2d1ab3"]
  end
  subgraph kit["platform-infra-kit (consumer packaging)"]
    man["Wheel manifest: source SHA + sha256 per wheel"]
    whl["platform_observability-0.1.0-py3-none-any.whl"]
  end
  subgraph k8s["Reference target: Kubernetes namespace shared-staging (not deployed)"]
    api["Shared API pods, label app.kubernetes.io/part-of=shared-infra, port name http"]
    prom["Prometheus SA shared-prometheus"]
    sec["Secret file /run/secrets/shared_metrics_token"]
    rules["/etc/prometheus/shared-alerts.yaml"]
  end
  pr1 -->|"pinned e2d1ab3 in 2026-10-15 manifest"| man
  man --> whl
  whl -->|"offline install"| api
  prom -->|"EndpointSlice SD, scrape 15s"| api
  sec --> prom
  rules --> prom
  api -->|"OTEL_TRACES_ENDPOINT HTTPS"| col["OTLP collector (not provisioned)"]
```

| สิ่งที่ consumer ตั้งค่า | ที่มา |
|---|---|
| `METRICS_TOKEN` (ใส่เป็น `metrics_token`) | `docs/shared-runtime.md` |
| `OTEL_TRACES_ENDPOINT` (ใส่เป็น `endpoint`) | `docs/shared-runtime.md` |
| Python ≥ 3.12, deps pinned (`opentelemetry-*==1.45.1`) | `pyproject.toml`, `uv.lock` |

Sources: `pyproject.toml`, `uv.lock`, `config/prometheus.yaml`, `config/shared-alerts.yaml`, `config/discovery-rbac.yaml`, `docs/shared-runtime.md`, `tests/test_build_hygiene.py`; architecture-docs [`docs/superpowers/reports/2026-10-15-shared-infrastructure-wheels.json`](https://github.com/bookchaowalit/architecture-docs/blob/main/docs/superpowers/reports/2026-10-15-shared-infrastructure-wheels.json); ops record: book-platforms-status (2026-11-03) "observability is a library (no service)"

## Open questions

- wheel manifest ล่าสุดที่อ่านได้ pin `e2d1ab3` (head ของ PR #1 ก่อน merge) ไม่ใช่ main ปัจจุบัน: มี manifest ใหม่ที่ pin main หรือไม่
- 8 platform services ที่ live บน Railway ไม่ได้ import library นี้ (ค้นใน worktree Core 22 ไม่พบ): จะใช้ library กับ Railway services หรือคงไว้เป็น reference k8s เท่านั้น
