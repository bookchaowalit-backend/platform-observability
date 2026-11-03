# 19 — Service dependency map

`contract.json` `depends_on: []`: ไม่พึ่ง platform อื่นใน runtime dependency ที่มีคือ library ภาษา Python และระบบภายนอกที่ consumer ต้องจัดให้

```mermaid
flowchart LR
  subgraph lib["platform_observability (in consumer process)"]
    core["instrument / Observed"]
  end
  core --> starlette["starlette >=0.46,<2"]
  core --> promc["prometheus-client >=0.20,<1"]
  core --> otel["opentelemetry-api / sdk / exporter-otlp-proto-common ==1.45.1"]
  core --> httpx["httpx >=0.27,<1"]
  core -->|"runtime, optional"| col["OTLP/HTTP collector"]
  prom["Prometheus (reference)"] -->|"scrapes"| core
  prom --> k8s["Kubernetes API EndpointSlice SD"]
  subgraph ci["CI-time only"]
    gw["platform-api-gateway 6e1fb34"]
    ciw["platform-ci-workflows 87dc5e1c"]
    canon["backend-core canonical contract schema (pin source)"]
  end
  subgraph consumers["Consumers"]
    kit["platform-infra-kit shared APIs"]
  end
  kit --> core
```

Sources: `contract.json`, `pyproject.toml`, `uv.lock`, `src/platform_observability/*.py`, `config/prometheus.yaml`, `.github/workflows/check.yml`, `scripts/check_schema_pin.py`, `docs/shared-runtime.md`

## Open questions

- ไม่มี
