# Shared runtime telemetry

Status: implemented locally; no production collector or alert delivery enabled.

`platform_observability.instrument(app, service_name=..., metrics_token=...,
endpoint=...)` instruments a FastAPI service before its first request. The
portable `platform-infra-kit` runtime attaches it to all seven shared APIs.
Each application has its own registry and tracer provider, shut down with its
lifespan. Metrics credentials are supplied explicitly through `METRICS_TOKEN`;
absence disables `/metrics`, wrong credentials return401, and malformed binary
credentials cannot cause500. The request route itself remains uninstrumented
to avoid recursive scrape metrics.

Metrics include `platform_requests_total` and
`platform_request_duration_seconds` histogram buckets. Labels are bounded to
service, known HTTP method, server route template and status. Unknown routes
use `unmatched`; file IDs, workspace IDs, URL/query/header/body and exception
text are excluded from metrics, spans and the library's structured logs.
Infrastructure access logs need their own equivalent policy; the reference
launcher disables Uvicorn access logging.

`OTEL_TRACES_ENDPOINT` is the full explicit OTLP/HTTP trace URL. HTTPS is
required except loopback fixtures. The installed OpenTelemetry exporter uses
its documented certificate environment settings for a private CA. There is no
automatic exception stack recording. Export queues are bounded at512 spans,
64 per batch, two-second export timeout; a disconnected collector can lose
telemetry without granting access or blocking paid-work admission.

`config/prometheus.yaml` is a private-network reference scrape configuration.
Mount the same explicitly provisioned scrape credential in each API and the
Prometheus credential file. Use per-service jobs/files if credentials differ.
Keep this monitoring endpoint behind network policy; do not publish it through
the public ingress. EndpointSlice discovery scrapes individual API replicas;
set its namespace and bind the Prometheus service account with the accompanying
read-only discovery Role. The API pods themselves have no service-account
token. Discovery follows the [official Prometheus configuration](https://prometheus.io/docs/prometheus/latest/configuration/configuration/#kubernetes_sd_config).
Rule evaluation must be tested with the selected Prometheus
binary before rollout. Dashboard queries combine replica counters with `sum`;
latency uses histogram buckets rather than averaging replica percentiles.

Reference alerts detect unavailable scrape targets, sustained service errors
and high request latency. Their thresholds are staging drill thresholds, not a
promised service level. Route a synthetic failure to a test receiver, verify
notification and recovery, and record ownership/retention before enabling live
receivers. This change sends no notifications.

Local verification: install `.[test]`, run `python -m pytest`, then
`bash scripts/check.sh`. The real multi-process HTTP acceptance and restore
drill live in `platform-infra-kit`. Prometheus/Grafana deployment, rule-engine
validation, OTLP collector connectivity and actual receiver delivery require
their explicit staging environment; none is inferred from unit tests.
