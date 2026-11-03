# 10 — Sequences

## S1 — Request ผ่าน instrumented service

```mermaid
sequenceDiagram
  participant C as HTTP client
  participant M as Observed middleware
  participant A as FastAPI app
  participant O as Observation
  participant P as BoundedProcessor
  participant L as Logger platform_observability
  C->>M: HTTP request (optional traceparent, tracestate)
  M->>M: Normalise method to known set or OTHER
  M->>M: Extract W3C context (headers up to 512 bytes)
  M->>O: start_as_current_span HTTP, kind SERVER, record_exception false
  M->>A: call app with observed_send
  A-->>M: http.response.start status
  M-->>C: response passthrough
  M->>M: route = scope.route.path or unmatched
  M->>O: requests.inc, duration.observe
  M->>O: span name METHOD route, attrs method/route/status, ERROR if >= 500
  O->>P: on_end(span), put_nowait or drop when queue full
  M->>L: one JSON line service, method, route, status, duration, correlation_id, trace_id
```

## S2 — Prometheus scrape

```mermaid
sequenceDiagram
  participant Pr as Prometheus
  participant M as Observed middleware
  participant R as CollectorRegistry
  Pr->>M: GET /metrics, Authorization Bearer token from credentials_file
  alt no metrics_token configured
    M-->>Pr: 404
  else header too long or mismatch
    M-->>Pr: 401
  else match via compare_digest
    M->>R: generate_latest
    M-->>Pr: 200 text/plain version 0.0.4
  end
```

## S3 — Span export

```mermaid
sequenceDiagram
  participant T as platform-trace-export thread
  participant Q as Queue max 512
  participant E as SafeHTTPExporter
  participant X as OTLP collector
  loop until stop is set
    T->>Q: get with 50 ms timeout
    T->>Q: drain up to 64 spans
    T->>E: export(batch)
    E->>X: POST protobuf, timeout 2s, no redirect
    alt 2xx
      X-->>E: SUCCESS
    else other status or exception
      E->>E: log telemetry_export_failed only
    end
  end
  Note over T,Q: shutdown joins 2.5s then drops remaining spans
```

## S4 — CI gateway parity check

```mermaid
sequenceDiagram
  participant G as GitHub Actions contract job
  participant GW as platform-api-gateway at 6e1fb34
  participant S as scripts/check.sh
  participant T as tests/test_telemetry_policy.py
  G->>GW: actions/checkout to .ci/platform-api-gateway
  G->>S: run with PLATFORM_API_GATEWAY_SRC and REQUIRE_GATEWAY_TESTS=1
  S->>S: check.py, check_schema_pin.py
  S->>T: unittest discover
  T->>GW: import gateway, capture request.completed events
  T->>T: envelope_gateway_event then validate_event
  T-->>G: fail if invalid or field set drifts
```

Sources: `src/platform_observability/middleware.py`, `src/platform_observability/export.py`, `config/prometheus.yaml`, `.github/workflows/check.yml`, `scripts/check.sh`, `tests/test_telemetry_policy.py` (`GatewayTelemetryTests`)

## Open questions

- ไม่มี
