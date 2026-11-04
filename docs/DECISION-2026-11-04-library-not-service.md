# Decision 2026-11-04: observability stays a library, not a service

Decided by the owner on 2026-11-04 (recommendation accepted).

## Decision

`platform-observability` stays a shared instrumentation library plus the
reference scrape and rule configuration. No observability service, collector
or metrics scraper is deployed for the Book Platform services.

## Why

- The services run serverless on Railway (sleep on). A scraper polling
  `/metrics` would keep every one of them awake and turn a near-zero bill into
  always-on compute for all of them.
- What a service would give is already covered by hosted tools:
  - errors: Sentry project `platform-<svc>` on every live service, sending no
    free text (type, stack, route, tags only);
  - availability: `platform-uptime-worker` checks `/readyz` hourly and alerts on
    change;
  - security events: the posture monitor and the security-api audit log.
- One operator does not need dashboards that nobody watches; alerts on change
  are enough at this scale.

## Consequences

- Services keep using this library for request metrics and logs in-process;
  the Prometheus/K8s configuration stays a reference, not a deployment.
- The registry entry stays `local-scaffold` (no runtime to activate).
- Revisit when any of these is true: a service runs always-on with real
  traffic, a client contract requires latency SLOs or traces, or Sentry and the
  uptime checks miss an incident.
