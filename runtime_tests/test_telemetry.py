import importlib
import json
import logging

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest
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
    app, exporter = fixture()
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
