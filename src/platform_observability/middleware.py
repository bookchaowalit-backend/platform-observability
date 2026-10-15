"""Observe fixed route templates; never collect URLs, tenant IDs or payloads."""
from contextlib import asynccontextmanager
import ipaddress
import json
import logging
import re
import secrets
import time
from urllib.parse import urlsplit
from uuid import uuid4

from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, SimpleSpanProcessor
from opentelemetry.trace import SpanKind, Status, StatusCode
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator
from prometheus_client import CollectorRegistry, Counter, Histogram, generate_latest
from starlette.responses import Response

_LOG = logging.getLogger('platform_observability')
_ROUTE = re.compile(r'[A-Za-z0-9_/.{}:-]{1,256}')


class Observation:
    def __init__(self, service, metrics_token, exporter=None, endpoint=None):
        self.service, self.metrics_token = service, metrics_token
        self.registry = CollectorRegistry()
        self.requests = Counter('platform_requests_total', 'Completed requests',
                                ['service', 'method', 'route', 'status'], registry=self.registry)
        self.duration = Histogram('platform_request_duration_seconds', 'Request duration',
                                  ['service', 'method', 'route'], registry=self.registry,
                                  buckets=(.005, .01, .025, .05, .1, .25, .5, 1, 2.5, 5, 10))
        self.provider = TracerProvider(resource=Resource.create({'service.name': service}))
        if exporter is not None:
            self.provider.add_span_processor(SimpleSpanProcessor(exporter))
        elif endpoint:
            parsed = urlsplit(endpoint)
            loopback = parsed.hostname == 'localhost'
            try:
                loopback = loopback or ipaddress.ip_address(parsed.hostname or '').is_loopback
            except ValueError:
                pass
            if (parsed.scheme != 'https' and not (parsed.scheme == 'http' and loopback)) or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
                raise ValueError('telemetry requires an explicit HTTPS or loopback endpoint')
            from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
            self.provider.add_span_processor(BatchSpanProcessor(
                OTLPSpanExporter(endpoint=endpoint, timeout=2), max_queue_size=512,
                max_export_batch_size=64, schedule_delay_millis=500, export_timeout_millis=2000))
        self.tracer = self.provider.get_tracer('platform_observability')

    def close(self):
        self.provider.shutdown()


class Observed:
    def __init__(self, app, observation):
        self.app, self.observation = app, observation

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            return await self.app(scope, receive, send)
        observation = self.observation
        if scope.get('path') == '/metrics':
            if not observation.metrics_token:
                return await Response(status_code=404)(scope, receive, send)
            supplied = next((v for k, v in scope.get('headers', []) if k.lower() == b'authorization'), b'')
            expected = ('Bearer ' + observation.metrics_token).encode('ascii')
            if len(supplied) > 2048 or not secrets.compare_digest(supplied, expected):
                return await Response(status_code=401)(scope, receive, send)
            return await Response(generate_latest(observation.registry),
                                  media_type='text/plain; version=0.0.4')(scope, receive, send)
        method = scope.get('method', 'OTHER')
        if method not in {'GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'HEAD', 'OPTIONS'}:
            method = 'OTHER'
        status, started, correlation = 500, time.monotonic(), str(uuid4())

        async def observed_send(message):
            nonlocal status
            if message['type'] == 'http.response.start':
                status = message['status']
            await send(message)

        # Automatic exception recording includes exception text/stack frames,
        # which may contain customer data. Record only a generic error status.
        carrier = {k.decode('ascii'): v.decode('ascii', errors='ignore')
                   for k, v in scope.get('headers', []) if k in {b'traceparent', b'tracestate'} and len(v) <= 512}
        context = TraceContextTextMapPropagator().extract(carrier)
        with observation.tracer.start_as_current_span('HTTP', kind=SpanKind.SERVER,
                context=context, record_exception=False, set_status_on_exception=False) as span:
            try:
                await self.app(scope, receive, observed_send)
            finally:
                route = getattr(scope.get('route'), 'path', 'unmatched')
                if not isinstance(route, str) or not _ROUTE.fullmatch(route):
                    route = 'unmatched'
                elapsed = max(0, time.monotonic() - started)
                observation.requests.labels(observation.service, method, route, str(status)).inc()
                observation.duration.labels(observation.service, method, route).observe(elapsed)
                span.update_name(method + ' ' + route)
                span.set_attributes({'http.request.method': method, 'http.route': route,
                                     'http.response.status_code': status})
                if status >= 500:
                    span.set_status(Status(StatusCode.ERROR))
                _LOG.info(json.dumps({'service': observation.service, 'method': method,
                    'route': route, 'status': status, 'duration_seconds': round(elapsed, 6),
                    'correlation_id': correlation, 'trace_id': format(span.get_span_context().trace_id, '032x')}, separators=(',', ':')))


def instrument(app, *, service_name: str, metrics_token: str | None = None, exporter=None, endpoint: str | None = None):
    """Attach independent telemetry, closing its exporter with the app lifespan."""
    if not isinstance(service_name, str) or not re.fullmatch(r'[A-Za-z0-9_.-]{1,64}', service_name):
        raise ValueError('invalid service name')
    if metrics_token is not None and (not isinstance(metrics_token, str) or not 16 <= len(metrics_token) <= 1024 or any(ord(c) <= 32 or ord(c) > 126 for c in metrics_token)):
        raise ValueError('metrics credential must be explicitly configured')
    if getattr(app.state, 'platform_observation', None) is not None:
        raise ValueError('telemetry already configured')
    observation = Observation(service_name, metrics_token, exporter, endpoint)
    app.state.platform_observation = observation
    app.add_middleware(Observed, observation=observation)
    original = app.router.lifespan_context

    @asynccontextmanager
    async def lifespan(application):
        try:
            async with original(application) as state:
                yield state
        finally:
            observation.close()
    app.router.lifespan_context = lifespan
    return app
