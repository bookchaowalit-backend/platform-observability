"""Finite asynchronous export; collector payloads never enter diagnostics."""
import logging
import queue
import ssl
import threading
import time

import httpx
from opentelemetry.exporter.otlp.proto.common.trace_encoder import encode_spans
from opentelemetry.sdk.trace import ReadableSpan, SpanProcessor
from opentelemetry.sdk.trace.export import SpanExportResult

_LOG = logging.getLogger('platform_observability')


class SafeHTTPExporter:
    def __init__(self, endpoint, *, transport=None):
        self.endpoint = endpoint
        self.client = httpx.Client(timeout=2.0, follow_redirects=False, trust_env=False,
                                   verify=ssl.create_default_context(),
                                   limits=httpx.Limits(max_connections=1, max_keepalive_connections=1),
                                   transport=transport)

    def export(self, spans):
        try:
            payload = encode_spans(spans).SerializeToString()
            # Ignore response bodies, including arbitrarily large error pages.
            # No automatic retries or SDK exception/response-body diagnostics.
            with self.client.stream('POST', self.endpoint, content=payload,
                                    headers={'Content-Type': 'application/x-protobuf'}) as response:
                if 200 <= response.status_code < 300:
                    return SpanExportResult.SUCCESS
        # Fail closed on any encode/transport error; the exception text can echo
        # collector responses or span data, so it is deliberately never logged.
        except Exception:  # noqa: BLE001
            _LOG.warning('{"event":"telemetry_export_failed"}')
            return SpanExportResult.FAILURE
        _LOG.warning('{"event":"telemetry_export_failed"}')
        return SpanExportResult.FAILURE

    def shutdown(self):
        self.client.close()


class BoundedProcessor(SpanProcessor):
    def __init__(self, exporter, *, shutdown_timeout=2.5):
        self._exporter = exporter
        self._queue: queue.Queue[ReadableSpan] = queue.Queue(maxsize=512)
        self._stop = threading.Event()
        self._active = threading.Event()
        self._shutdown_timeout = shutdown_timeout
        self._thread = threading.Thread(target=self._run, name='platform-trace-export', daemon=True)
        self._thread.start()

    @property
    def queue_size(self):
        return self._queue.qsize()

    def on_start(self, span, parent_context=None):
        pass

    def on_end(self, span):
        if self._stop.is_set() or not span.context.trace_flags.sampled:
            return
        try:
            self._queue.put_nowait(span)
        except queue.Full:
            pass

    def _run(self):
        try:
            while not self._stop.is_set():
                try:
                    span = self._queue.get(timeout=.05)
                except queue.Empty:
                    continue
                self._active.set()
                batch = [span]
                while len(batch) < 64:
                    try:
                        batch.append(self._queue.get_nowait())
                    except queue.Empty:
                        break
                try:
                    self._exporter.export(batch)
                # The single export thread must survive any exporter error.
                except Exception:  # noqa: BLE001
                    _LOG.warning('{"event":"telemetry_export_failed"}')
                finally:
                    for _ in batch:
                        self._queue.task_done()
                    self._active.clear()
        finally:
            try:
                self._exporter.shutdown()
            # Best-effort close; never surface exception text from the exporter.
            except Exception:  # noqa: BLE001
                _LOG.warning('{"event":"telemetry_exporter_shutdown_failed"}')

    def shutdown(self):
        self._stop.set()
        # A stalled DNS/socket cannot indefinitely hold service shutdown.
        # The single daemon exporter may finish later; queued spans are dropped.
        self._thread.join(timeout=self._shutdown_timeout)
        while True:
            try:
                self._queue.get_nowait()
                self._queue.task_done()
            except queue.Empty:
                break

    def force_flush(self, timeout_millis=2500):
        deadline = time.monotonic() + min(2500, max(0, timeout_millis)) / 1000
        while time.monotonic() < deadline:
            if not self._queue.unfinished_tasks:
                return True
            self._stop.wait(.005)
        return not self._queue.unfinished_tasks
