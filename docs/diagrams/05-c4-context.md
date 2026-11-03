# 05 — C4 Context

library นี้ไม่ได้รันเอง ภาพ context จึงวาง library ไว้ "ภายใน" service ที่ใช้มัน และแสดงระบบรอบข้างที่ config อ้างถึง

```mermaid
C4Context
  title platform-observability - System Context
  Person(owner, "Owner / agent", "Edits contract, policy and library; records gate decisions")
  System(obs, "platform-observability", "Python library instrument() + telemetry redaction policy + contract checks + reference Prometheus config")
  System_Ext(svc, "Consuming FastAPI services", "Shared APIs started by platform-infra-kit; library runs in-process")
  System_Ext(kit, "platform-infra-kit", "Builds hashed offline wheels and the reference deployment")
  System_Ext(prom, "Prometheus", "Reference scrape config, k8s EndpointSlice discovery, namespace shared-staging")
  System_Ext(otlp, "OTLP/HTTP collector", "Explicit HTTPS trace endpoint OTEL_TRACES_ENDPOINT")
  System_Ext(gw, "platform-api-gateway", "Source of request.completed events, checked out pinned in CI")
  System_Ext(solo, "solo-empire", "Control plane; registry platforms.yaml; former infra/self-hosted-stack")
  System_Ext(gha, "GitHub Actions", "Check workflow + shared ci-python and security workflows")

  Rel(owner, obs, "Commits, runs scripts/check.sh")
  Rel(kit, obs, "Builds wheel from pinned source SHA")
  Rel(svc, obs, "Calls instrument(app)")
  Rel(prom, svc, "GET /metrics with Bearer token")
  Rel(svc, otlp, "POST protobuf spans")
  Rel(gha, obs, "Runs checks on push and PR")
  Rel(gha, gw, "Checks out 6e1fb34 for parity tests")
  Rel(owner, solo, "Registry alignment check, local read-only")
```

Sources: `README.md`, `PRODUCT.md`, `contract.json`, `docs/shared-runtime.md`, `config/prometheus.yaml`, `.github/workflows/check.yml`, `scripts/check_registry_alignment.py`; architecture-docs [`docs/superpowers/specs/2026-10-15-shared-infrastructure-design.md`](https://github.com/bookchaowalit/architecture-docs/blob/main/docs/superpowers/specs/2026-10-15-shared-infrastructure-design.md) (capability owners table)

## Open questions

- ไม่มี collector, Prometheus หรือ Grafana ที่ host จริงที่ยืนยันได้จาก repo: ระบบภายนอกในภาพเป็น "reference/staging" ตาม `docs/shared-runtime.md`
