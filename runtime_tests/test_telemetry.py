import importlib
import json
import logging

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter


def instrument(*args, **kwargs):
    try:
        api = importlib.import_module('platform_observability')
    except ModuleNotFoundError:
        pytest.fail('shared telemetry instrumentation is missing')
    return api.instrument(*args, **kwargs)


def fixture():
    app = FastAPI()

    @app.get('/files/{file_id}')
    def file(file_id: str):
        return {'id': file_id}

    @app.get('/broken')
    def broken():
        raise RuntimeError('synthetic-private-payload')

    exporter = InMemorySpanExporter()
    instrument(app, service_name='media', metrics_token='synthetic-metrics-token', exporter=exporter)
    return app, exporter


def test_metrics_are_authenticated_and_use_route_templates():
    app, _exporter = fixture()
    with TestClient(app) as client:
        assert client.get('/files/private-customer-id?token=private-query').status_code == 200
        assert client.get('/metrics').status_code == 401
        response = client.get('/metrics', headers={'Authorization': 'Bearer synthetic-metrics-token'})
        assert response.status_code == 200
        assert '/files/{file_id}' in response.text
        assert 'private-customer-id' not in response.text
        assert 'private-query' not in response.text
        assert 'platform_request_duration_seconds_bucket' in response.text


def test_spans_exclude_queries_headers_payloads_and_exception_details(caplog):
    app, exporter = fixture()
    with caplog.at_level(logging.INFO, logger='platform_observability'), TestClient(app, raise_server_exceptions=False) as client:
        client.get('/files/private-customer-id?secret=private-query', headers={'Authorization': 'Bearer private-header'})
        assert client.get('/broken').status_code == 500
        spans = exporter.get_finished_spans()
        assert len(spans) == 2
        serialized = json.dumps([{'name': s.name, 'attributes': dict(s.attributes),
                                  'events': [str(e) for e in s.events]} for s in spans])
        for private in ['private-customer-id', 'private-query', 'private-header', 'synthetic-private-payload']:
            assert private not in serialized
        records = [r.getMessage() for r in caplog.records if r.name == 'platform_observability']
        assert records
        assert all(json.loads(r)['route'] in ['/files/{file_id}', '/broken'] for r in records)
        assert all('private' not in r for r in records)


def test_independent_apps_do_not_share_or_duplicate_metric_registries():
    first, _ = fixture()
    second, _ = fixture()
    with TestClient(first) as a, TestClient(second) as b:
        a.get('/files/one')
        b.get('/files/two')
        b.get('/files/three')
        headers = {'Authorization': 'Bearer synthetic-metrics-token'}
        assert 'platform_requests_total{method="GET",route="/files/{file_id}",service="media",status="200"} 1.0' in a.get('/metrics', headers=headers).text
        assert 'platform_requests_total{method="GET",route="/files/{file_id}",service="media",status="200"} 2.0' in b.get('/metrics', headers=headers).text


def test_missing_metrics_credential_disables_endpoint():
    app = FastAPI()
    instrument(app, service_name='workflow')
    with TestClient(app) as client:
        assert client.get('/metrics').status_code == 404


def test_non_ascii_metrics_authorization_is_rejected_without_server_error():
    app, _ = fixture()
    with TestClient(app, raise_server_exceptions=False) as client:
        assert client.get('/metrics', headers=[(b'authorization', b'Bearer \xff')]).status_code == 401


def test_valid_trace_context_links_the_request_span_without_copying_headers(caplog):
    app, exporter = fixture()
    trace_id = '1234567890abcdef1234567890abcdef'
    with caplog.at_level(logging.INFO, logger='platform_observability'), TestClient(app) as client:
        client.get('/files/one', headers={'traceparent': f'00-{trace_id}-1234567890abcdef-01',
                                         'baggage': 'private-customer=synthetic-private'})
        span = exporter.get_finished_spans()[0]
        assert span.context.trace_id == int(trace_id, 16)
        assert span.parent.span_id == int('1234567890abcdef', 16)
        records = [json.loads(r.getMessage()) for r in caplog.records if r.name == 'platform_observability']
        assert records[0]['trace_id'] == trace_id
        assert 'synthetic-private' not in str(records) + str(span.attributes)


def test_arbitrary_synchronous_exporter_is_rejected():
    class NetworkExporter:
        def export(self, spans):
            raise AssertionError('must never be invoked on the request thread')
    with pytest.raises(ValueError, match='in-memory'):
        instrument(FastAPI(), service_name='data', exporter=NetworkExporter())


def test_otlp_failure_diagnostics_never_include_response_or_exception_payload(caplog):
    import httpx
    from opentelemetry.sdk.trace.export import SpanExportResult

    from platform_observability.export import SafeHTTPExporter
    app, memory = fixture()
    with TestClient(app) as client:
        client.get('/files/one')
        spans = memory.get_finished_spans()
        for failing in (False, True):
            def transport(request, failing=failing):
                if failing:
                    raise httpx.ConnectError('synthetic-private-exception')
                return httpx.Response(400, text='synthetic-private-response')
            exporter = SafeHTTPExporter('https://collector.example.invalid/v1/traces',
                                         transport=httpx.MockTransport(transport))
            with caplog.at_level(logging.WARNING):
                assert exporter.export(spans) is SpanExportResult.FAILURE
            exporter.shutdown()
    assert 'synthetic-private' not in caplog.text


def test_batch_export_and_shutdown_are_bounded_when_exporter_stalls():
    import threading
    import time

    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SpanExportResult

    from platform_observability.export import BoundedProcessor
    entered, release = threading.Event(), threading.Event()
    class Stalled:
        def export(self, spans):
            entered.set()
            release.wait(2)
            return SpanExportResult.SUCCESS
        def shutdown(self):
            pass
    provider = TracerProvider(shutdown_on_exit=False)
    processor = BoundedProcessor(Stalled(), shutdown_timeout=.05)
    provider.add_span_processor(processor)
    try:
        started = time.monotonic()
        with provider.get_tracer('test').start_as_current_span('one'):
            pass
        assert time.monotonic() - started < .1
        assert entered.wait(1)
        # Queue is finite even while the only export worker is blocked.
        for _ in range(600):
            with provider.get_tracer('test').start_as_current_span('queued'):
                pass
        assert processor.queue_size <= 512
        started = time.monotonic()
        provider.shutdown()
        assert time.monotonic() - started < .25
    finally:
        release.set()
