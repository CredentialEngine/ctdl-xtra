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
    assert a["ce.class"] == "course"  # a catalog's routes serve Course unless ?class= says otherwise


def test_the_class_and_the_property_are_on_the_span(traced):
    c, exporter = traced
    c.get("/api/catalogs/avc/rules", params={"class": "learningprogram"})
    assert _server_spans(exporter)[-1].attributes["ce.class"] == "learningprogram"
    c.get("/api/properties/learningprogram/name/review")
    a = _server_spans(exporter)[-1].attributes
    assert a["http.route"] == "/api/properties/{cls}/{column}/review"
    assert (a["ce.class"], a["ce.property.column"]) == ("learningprogram", "name")


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


def _encode(value: str) -> str:
    """As the build and deploy scripts encode an OTEL_RESOURCE_ATTRIBUTES value: at most 200 characters, then
    percent-encoded, keeping only what reads well and can't split the list (no `,`, `=`, `%`, spaces or quotes)."""
    from urllib.parse import quote

    return quote(value[:200], safe="/:@.-_~")


def test_encoded_resource_attributes_arrive_intact_on_a_span(no_otel_env, monkeypatch):
    """A pull request's title or a commit's subject may hold `,` and `=`: percent-encoded in OTEL_RESOURCE_ATTRIBUTES,
    they reach the span's resource as written."""
    pytest.importorskip("opentelemetry.sdk")
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

    title = "Fix: a, b = c"
    message = "Studio: 100% of rules, \"quoted\" & more; key=value " + "x" * 300
    attrs = {
        "vcs.change.id": "471", "vcs.change.title": title, "vcs.change.state": "merged",
        "ce.vcs.change.url": "https://github.com/CredentialEngine/ctdl-xtra/pull/471",
        "ce.vcs.commit.message": message, "ce.vcs.commit.author": "Jane Q. Doe",
        "ce.vcs.commit.timestamp": "2026-11-24T22:59:42Z", "ce.deploy.triggered_by": "Jane Q. Doe",
        "k8s.pod.name": "golden-rules-studio-6d4f9-abcde", "host.name": "node-1",
    }
    encoded = ",".join(f"{k}={_encode(v)}" for k, v in attrs.items())
    assert "," not in _encode(title) and "=" not in _encode(title)
    monkeypatch.setenv("OTEL_RESOURCE_ATTRIBUTES", encoded)
    exporter = InMemorySpanExporter()
    provider = TracerProvider(resource=telemetry.resource())
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    with provider.get_tracer("test").start_as_current_span("request"):
        pass
    got = exporter.get_finished_spans()[0].resource.attributes
    assert got["vcs.change.title"] == "Fix: a, b = c"
    assert got["ce.vcs.commit.message"] == message[:200] and len(got["ce.vcs.commit.message"]) == 200
    assert {k: got[k] for k in attrs} == {**attrs, "ce.vcs.commit.message": message[:200]}
    assert got["service.name"] == telemetry.SERVICE_NAME


def test_browser_spans_carry_the_change_the_deployment_and_the_pod(traced, monkeypatch):
    """The web app's resource repeats the server's change, deployment and Kubernetes identity (the collector can't add
    k8s.* to a browser span), but not what only describes the Python process."""
    from opentelemetry import trace
    from opentelemetry.sdk.resources import Resource

    server = {
        "service.name": "golden-dataset-studio", "service.version": "0.1.0", "service.namespace": "ctdl-xtra",
        "deployment.environment.name": "production", "deployment.id": "local-20261124T000000Z",
        "deployment.name": "abc1234-otel", "vcs.ref.head.revision": "abc1234", "vcs.change.id": "471",
        "vcs.change.title": "Fix: a, b = c", "vcs.change.state": "merged", "ce.vcs.change.url": "https://x/pull/471",
        "ce.vcs.change.author": "a", "ce.vcs.change.merged_by": "b", "ce.vcs.change.merged_at": "2026-11-24T00:00:00Z",
        "ce.vcs.commit.author": "a", "ce.vcs.commit.message": "Fix: a, b = c", "ce.vcs.commit.timestamp": "t",
        "cicd.pipeline.name": "build-otel.sh", "ce.cicd.triggered_by": "a", "ce.deploy.triggered_by": "b",
        "ce.deploy.pipeline.run.url": "https://x/runs/1", "k8s.pod.name": "p", "k8s.pod.uid": "u",
        "k8s.node.name": "n", "k8s.namespace.name": "ns", "host.name": "n", "ce.k8s.pod.ip": "10.0.0.1",
        "process.pid": 1, "telemetry.sdk.language": "python",
    }
    monkeypatch.setattr(trace.get_tracer_provider(), "_resource", Resource(server))
    browser = telemetry.browser_config()["resource"]
    dropped = {"service.name", "ce.k8s.pod.ip", "process.pid", "telemetry.sdk.language"}
    assert browser == {k: v for k, v in server.items() if k not in dropped}


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


def test_a_call_to_azure_blob_storage_is_a_client_span_and_a_local_file_is_not(traced):
    """The service map's edge from the Studio to the bucket, and which blobs a slow request waited on."""
    _, exporter = traced

    class Fake:
        uri, account, container_name = "azure://https://acct.blob.core.windows.net/box/pre", "acct", "box"

        @telemetry.storage_op("read")
        def read_bytes(self, path):
            return b"12345"

        @telemetry.storage_op("list")
        def list(self, prefix):
            return ["a", "b"]

    class Local(Fake):
        uri = "/tmp/root"

    token = telemetry._counters.set({})
    try:
        with telemetry.span("request"):
            Fake().read_bytes("cat/manifest.json")
            Fake().list("cat/rules/")
            Local().read_bytes("cat/manifest.json")
    finally:
        telemetry._counters.reset(token)
    spans = {s.name: s for s in exporter.get_finished_spans()}
    read, listed = spans["azure.blob.read"], spans["azure.blob.list"]
    assert read.kind.name == "CLIENT" and read.parent.span_id == spans["request"].context.span_id
    a = read.attributes
    assert (a["peer.service"], a["server.address"], a["ce.storage.container"], a["ce.storage.path"], a["ce.storage.bytes"]) \
        == ("azure-blob-storage", "acct.blob.core.windows.net", "box", "cat/manifest.json", 5)
    assert listed.attributes["ce.storage.items"] == 2
    assert [s.name for s in exporter.get_finished_spans()].count("azure.blob.read") == 1  # the local read made none


def test_a_file_from_the_disk_cache_is_not_a_call_to_azure_and_a_download_is(traced):
    """`local_path` answers from its disk cache most of the time: only a download is drawn as a call to the bucket.
    The host comes from the client's URL, so Azurite's is 127.0.0.1:10000, not a made-up blob.core.windows.net."""
    _, exporter = traced

    class Service:
        url = "http://127.0.0.1:10000/devstoreaccount1"

    class Fake:
        uri, account, container_name, service = "azure://http://127.0.0.1:10000/devstoreaccount1/box", "x", "box", Service()

        @telemetry.storage_op("local_path", call_span=False)
        def local_path(self, path, cached):
            if not cached:
                with telemetry.azure_call(self, "download", path) as call:
                    call.set_attribute("ce.storage.bytes", 7)
            return path

    token = telemetry._counters.set({})
    try:
        with telemetry.span("request"):
            Fake().local_path("cat/matches.parquet", cached=True)
            Fake().local_path("cat/occurrences.parquet", cached=False)
    finally:
        telemetry._counters.reset(token)
    calls = [s for s in exporter.get_finished_spans() if s.kind.name == "CLIENT"]
    assert [s.name for s in calls] == ["azure.blob.download"]
    a = calls[0].attributes
    assert (a["ce.storage.path"], a["ce.storage.bytes"], a["server.address"], a["server.port"]) \
        == ("cat/occurrences.parquet", 7, "127.0.0.1", 10000)
