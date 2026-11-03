# 06 — C4 Container

"container" ของ library คือหน่วยที่ส่งมอบแยกกัน: Python package, CLI scripts, schema/fixtures และ reference config

```mermaid
C4Container
  title platform-observability - Containers
  System_Ext(svc, "Consuming FastAPI service", "Imports the wheel")
  System_Ext(prom, "Prometheus", "Reference scraper")
  System_Ext(otlp, "OTLP collector", "HTTPS")
  Person(owner, "Owner / CI", "Runs checks")

  System_Boundary(b, "platform-observability repo") {
    Container(pkg, "platform_observability package", "Python 3.12, starlette, prometheus-client, opentelemetry-sdk 1.45.1, httpx", "instrument(), Observed middleware, BoundedProcessor, SafeHTTPExporter")
    Container(cli, "Contract and policy scripts", "Python stdlib", "check.py, check_schema_pin.py, check_registry_alignment.py, telemetry_policy.py")
    ContainerDb(schema, "Schemas and fixtures", "JSON files", "book-platform.contract.v1 schema + sha256 pin, redacted-telemetry-event.v1, fixtures/telemetry, fixtures/gates")
    Container(cfg, "Reference config", "YAML", "prometheus.yaml, shared-alerts.yaml, discovery-rbac.yaml")
  }

  Rel(svc, pkg, "In-process import")
  Rel(prom, svc, "Scrapes /metrics")
  Rel(pkg, otlp, "POST /v1/traces protobuf")
  Rel(owner, cli, "Runs")
  Rel(cli, schema, "Reads and validates")
  Rel(prom, cfg, "Loads scrape and rule files")
```

Sources: `pyproject.toml`, `src/platform_observability/__init__.py`, `src/platform_observability/middleware.py`, `src/platform_observability/export.py`, `scripts/*.py`, `schema/`, `fixtures/`, `config/*.yaml`

## Open questions

- ไม่มี
