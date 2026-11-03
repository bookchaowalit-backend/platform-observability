# 03 — User flows

ไม่มี UI หรือ route ของตัวเอง flow หลักคือ flow ของ "ผู้ใช้" แต่ละประเภทตาม `02-use-cases.md`

## Flow A — Consuming service ติดตั้ง instrumentation

```mermaid
flowchart TD
  A["Service builds FastAPI app"] --> B["instrument(app, service_name=..., metrics_token=..., endpoint=...)"]
  B --> C{"service_name matches [A-Za-z0-9_.-]{1,64}?"}
  C -- no --> X1["ValueError invalid service name"]
  C -- yes --> D{"metrics_token None or 16-1024 printable ASCII?"}
  D -- no --> X2["ValueError metrics credential"]
  D -- yes --> E{"app.state.platform_observation already set?"}
  E -- yes --> X3["ValueError telemetry already configured"]
  E -- no --> F{"exporter given?"}
  F -- "InMemorySpanExporter" --> G["SimpleSpanProcessor (tests only)"]
  F -- "other type" --> X4["ValueError only the in-memory test exporter"]
  F -- none --> H{"endpoint given?"}
  H -- no --> I["Tracer with no exporter"]
  H -- yes --> J{"https, or http on loopback; no userinfo, query, fragment?"}
  J -- no --> X5["ValueError explicit HTTPS or loopback endpoint"]
  J -- yes --> K["BoundedProcessor(SafeHTTPExporter)"]
  G --> L["add_middleware(Observed); wrap lifespan to close provider"]
  I --> L
  K --> L
```

## Flow B — Scraper อ่าน /metrics

```mermaid
flowchart TD
  S["GET /metrics"] --> T{"metrics_token configured?"}
  T -- no --> N404["404"]
  T -- yes --> U{"Authorization length <= 2048 and equals Bearer token (compare_digest)?"}
  U -- no --> N401["401"]
  U -- yes --> OK["200 text/plain; version=0.0.4 from the app's own registry"]
```

## Flow C — Maintainer เปลี่ยน telemetry policy

```mermaid
flowchart TD
  M1["Edit schema/telemetry or scripts/telemetry_policy.py"] --> M2["Add or update fixtures/telemetry valid or invalid"]
  M2 --> M3["bash scripts/check.sh locally"]
  M3 --> M4["Push: Check workflow runs gateway parity tests with REQUIRE_GATEWAY_TESTS=1"]
  M4 --> M5{"green?"}
  M5 -- no --> M1
  M5 -- yes --> M6["Merge to main; record owner decision in docs/gates if a gate changes"]
```

Sources: `src/platform_observability/middleware.py`, `docs/shared-runtime.md`, `scripts/check.sh`, `.github/workflows/check.yml`, `docs/gates/BOO-160-telemetry-redaction-retention.md` §Verification

## Open questions

- ไม่มี
