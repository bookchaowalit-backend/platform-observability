# 07 — C4 Component

ส่วนประกอบภายใน package `platform_observability` และ policy script

```mermaid
C4Component
  title platform_observability - Components
  Container_Ext(app, "Consuming FastAPI app", "ASGI")
  Container_Ext(otlp, "OTLP collector", "HTTPS")
  Container_Boundary(pkg, "platform_observability") {
    Component(instr, "instrument()", "function", "Validates service_name and metrics_token, stores Observation on app.state, adds middleware, wraps lifespan")
    Component(obsv, "Observation", "class", "Own CollectorRegistry, Counter platform_requests_total, Histogram platform_request_duration_seconds, TracerProvider")
    Component(mw, "Observed", "ASGI middleware", "Serves /metrics with Bearer check; per request: span, metrics, JSON log line")
    Component(proc, "BoundedProcessor", "SpanProcessor", "Queue 512, batch 64, one daemon thread, shutdown 2.5s")
    Component(exp, "SafeHTTPExporter", "httpx client", "Timeout 2s, no redirects, trust_env off, 1 connection, fixed failure log")
  }
  Container_Boundary(pol, "scripts/telemetry_policy.py") {
    Component(val, "validate_event / scan_forbidden", "functions", "Schema allow-list plus x-forbidden key and value scan")
    Component(red, "redact_health_snapshot", "function", "Maps system_health full_health() to health_snapshot")
    Component(env, "envelope_access_log / envelope_gateway_event", "functions", "Collector-side envelope for log lines")
  }

  Rel(app, instr, "Calls at startup")
  Rel(instr, obsv, "Creates")
  Rel(instr, mw, "add_middleware")
  Rel(mw, obsv, "Updates metrics and spans")
  Rel(obsv, proc, "add_span_processor when endpoint set")
  Rel(proc, exp, "export(batch)")
  Rel(exp, otlp, "POST protobuf")
  Rel(env, val, "Output must validate")
  Rel(red, val, "Output must validate")
```

Sources: `src/platform_observability/middleware.py`, `src/platform_observability/export.py`, `scripts/telemetry_policy.py`

## Open questions

- ไม่มี
