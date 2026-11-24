"""Traces (telemetry.py): off unless configured; on, one wide server span per request, with who and what."""

from __future__ import annotations

import threading

import pytest
from fastapi.testclient import TestClient

from golden_datasets import telemetry
from golden_datasets.server.app import WEB_DIST, create_app

OTEL_ENV = ("OTEL_EXPORTER_OTLP_ENDPOINT", "OTEL_EXPORTER_OTLP_TRACES_ENDPOINT", "OTEL_SDK_DISABLED",
            telemetry.ENV_BROWSER_ENDPOINT)


@pytest.fixture
def no_otel_env(monkeypatch):
    for k in OTEL_ENV:
        monkeypatch.delenv(k, raising=False)


def test_off_without_an_endpoint(tmp_path, no_otel_env, monkeypatch):
    assert not telemetry.configured()
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://collector:4318")
    monkeypatch.setenv("OTEL_SDK_DISABLED", "true")
    assert not telemetry.configured()  # disabled wins over an endpoint
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_ENDPOINT")
    if telemetry.enabled():
        pytest.skip("another test in this process turned telemetry on")
    app = create_app(str(tmp_path))
    assert not any(m.cls is telemetry.WideSpanMiddleware for m in app.user_middleware)
    c = TestClient(app)
    if WEB_DIST.exists():  # the web app's page is served as built: no telemetry config, so no telemetry code loads
        assert c.get("/").content == (WEB_DIST / "index.html").read_bytes()
    # the helpers are no-ops
    telemetry.set({"ce.x": 1})
    telemetry.count("x")
    with telemetry.span("nothing"), telemetry.job("nothing", carried=telemetry.carry()):
        pass


_EXPORTER = None  # OpenTelemetry's global tracer provider is set once per process: one in-memory exporter for all


@pytest.fixture
def traced(tmp_path, no_otel_env, monkeypatch):
    """An app traced into memory; telemetry is turned back off afterwards."""
    global _EXPORTER
    pytest.importorskip("opentelemetry.sdk")
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

    if _EXPORTER is None:
        _EXPORTER = InMemorySpanExporter()
        monkeypatch.setattr(telemetry, "_enabled", False)
        assert telemetry.init(_EXPORTER)
    monkeypatch.setattr(telemetry, "_enabled", True)
    monkeypatch.setenv(telemetry.ENV_BROWSER_ENDPOINT, "/otlp/v1/traces")
    _EXPORTER.clear()
    app = create_app(str(tmp_path))
    yield TestClient(app), _EXPORTER
    FastAPIInstrumentor.uninstrument_app(app)


def _server_spans(exporter):
    return [s for s in exporter.get_finished_spans() if s.kind.name == "SERVER"]


def test_one_wide_span_per_request(traced):
    c, exporter = traced
    baggage = "user.id=Test%20User,user.roles=sme,session.id=s-123,ce.page=rules,evil=dropped"
    assert c.get("/api/profiles", headers={"baggage": baggage}).status_code == 200
    spans = exporter.get_finished_spans()
    assert len(spans) == 1  # no receive/send spans
    a = spans[0].attributes
    assert a["http.route"] == "/api/profiles" and a["http.request.method"] == "GET"
    assert a["http.response.status_code"] == 200 and a["http.response.body.size"] > 0
    assert a["user.id"] == "Test User" and a["user.roles"] == ("sme",) and a["session.id"] == "s-123"
    assert a["ce.page"] == "rules" and "evil" not in a


def test_catalog_errors_and_storage_on_the_span(traced):
    c, exporter = traced
    r = c.get("/api/catalogs/avc/rules", params={"q": "GEOG", "offset": 40})
    assert r.status_code == 404
    a = _server_spans(exporter)[-1].attributes
    assert a["http.route"] == "/api/catalogs/{catalog}/rules"
    assert a["ce.catalog"] == "avc" and a["ce.catalog.folder"] == "avc-elumenapp-com-catalog-2026-27-welcome"
    assert a["ce.query.q"] == "GEOG" and a["ce.query.offset"] == "40"
    assert a["ce.error.detail"] == r.json()["detail"]
    assert a["ce.stats.storage.local.stats"] >= 1  # the manifest lookup


def test_health_and_static_files_are_not_traced_and_polls_are_marked(traced):
    c, exporter = traced
    for path in ("/api/health", "/assets/index-abc.js", "/logos/avc.png", "/favicon.ico"):
        c.get(path)
    assert exporter.get_finished_spans() == ()
    c.get("/api/catalogs/avc/agent-runs/current")
    assert _server_spans(exporter)[-1].attributes["ce.request.type"] == "poll"
    c.get("/api/catalogs/avc/assets/" + "a" * 64)
    assert _server_spans(exporter)[-1].attributes["ce.request.type"] == "asset"
    c.get("/")  # the web app's page itself is traced (its server time)
    assert _server_spans(exporter)[-1].attributes["http.route"] == "/{path:path}"


def test_browser_config_carries_the_deployment(traced, tmp_path):
    c, _ = traced
    cfg = telemetry.browser_config()
    assert cfg["endpoint"] == "/otlp/v1/traces" and cfg["sample_rate"] == 1
    index = tmp_path / "index.html"
    index.write_text("<html><head><title>x</title></head><body></body></html>")
    page = telemetry.browser_page(index)
    assert '<script id="otel-config" type="application/json">{"endpoint": "/otlp/v1/traces"' in page
    assert page.index("otel-config") < page.index("</head>")
    assert cfg["resource"]["service.version"]
    assert not any(k.startswith(("process.", "telemetry.", "service.name")) for k in cfg["resource"])


def test_background_job_is_its_own_trace_linked_to_the_request(traced):
    _, exporter = traced
    with telemetry.span("request", {"user.id": "Test User"}):
        carried = telemetry.carry()

    def work():
        with telemetry.job("score.run", {"ce.score.id": "sc-1"}, carried=carried):
            telemetry.set({"ce.score.status": "done"})

    t = threading.Thread(target=work)
    t.start()
    t.join()
    request, job = exporter.get_finished_spans()[-2:]
    assert job.name == "score.run" and job.context.trace_id != request.context.trace_id
    assert job.links[0].context.span_id == request.context.span_id
    assert job.attributes["ce.score.status"] == "done" and job.attributes["ce.score.id"] == "sc-1"


def test_a_thread_pool_works_in_the_request(traced):
    """A pool's threads add to the request's counters and make children of its span (a cold snapshot's downloads)."""
    from concurrent.futures import ThreadPoolExecutor

    _, exporter = traced
    request_counters: dict = {}
    token = telemetry._counters.set(request_counters)
    try:
        with telemetry.span("snapshot.read_tables"):
            def read(name):
                telemetry.count("stats.storage.local.reads")
                with telemetry.span(f"read {name}"):
                    pass

            read_in_request = telemetry.in_this_request(read)
            with ThreadPoolExecutor(max_workers=4) as pool:
                list(pool.map(read_in_request, range(20)))
    finally:
        telemetry._counters.reset(token)
    assert request_counters == {"stats.storage.local.reads": 20}
    spans = exporter.get_finished_spans()
    parent = next(s for s in spans if s.name == "snapshot.read_tables")
    reads = [s for s in spans if s.name.startswith("read ")]
    assert len(reads) == 20 and all(s.parent.span_id == parent.context.span_id for s in reads)


def test_in_this_request_is_the_function_itself_when_off(no_otel_env):
    if telemetry.enabled():
        pytest.skip("another test in this process turned telemetry on")

    def read():
        return 1

    assert telemetry.in_this_request(read) is read
