"""OpenTelemetry traces for the Studio: one wide span per request, a few sub-spans where they earn their keep.

Off unless the environment configures an OTLP endpoint (`OTEL_EXPORTER_OTLP_ENDPOINT` or
`OTEL_EXPORTER_OTLP_TRACES_ENDPOINT`) and the `otel` extra is installed (`uv sync --extra otel`). Off, every helper
here is a no-op that imports nothing, so local use, tests and a deployment without those variables behave exactly as
before. `OTEL_SDK_DISABLED=true` turns it off even when an endpoint is set.

Following Honeycomb's advice (wide events, few spans), the useful numbers go on the request's span as attributes:

- the FastAPI instrumentation makes the server span (`http.request.method`, `http.route`, `url.path`,
  `http.response.status_code`, `error.type`, exceptions);
- `install` wraps the app in a small ASGI middleware that adds, when the request ends: who (`user.id`, `user.roles`,
  `session.id`, from the W3C `baggage` header the web app sends), what (`ce.catalog.*`, `ce.rule.id`, `ce.page.stem`
  and the other path parameters, a few query parameters), how big (`http.response.body.size`), what storage it took
  (`ce.stats.storage.*`: reads, writes, bytes, `duration_ms`) and, on 4xx/5xx, the error's detail (`ce.error.detail`);
- route code adds what only it knows with `set({...})` (rows returned, verdicts, cache hits...);
- `span(name, {...})` makes a sub-span for work that takes real time: a cold extraction load, a publication, a
  score (scores and catalog adds run in threads after the request: they start a trace of their own, linked to it).

Everything that says where the Studio runs, and which change put it there, comes from outside the code:
`OTEL_RESOURCE_ATTRIBUTES` set at build or deploy time, and the collector's processors. The build adds the commit
(`vcs.ref.head.*`, `ce.vcs.commit.*`), its pull request if it has one (`vcs.change.*`, `ce.vcs.change.*`) and the
pipeline (`cicd.*`, `ce.cicd.*`); the deployment adds `deployment.*`, who deployed (`ce.deploy.*`) and, from the
Kubernetes downward API, the pod (`k8s.pod.*`, `k8s.node.name`, `k8s.namespace.name`, `host.name`). Values are
percent-encoded there (a pull request's title may hold `,` or `=`); the SDK decodes them.

`browser_config()` is what the web app needs to send its own spans: None when the server has no
`GOLDEN_DATASETS_OTEL_BROWSER_ENDPOINT`. `browser_page()` puts it in the app's index.html as an inline JSON script, so the
web app knows before its first request; off, index.html is served unchanged and the web app loads no telemetry code.
"""

from __future__ import annotations

import contextlib
import contextvars
import os
import sys
import threading
import time
from collections.abc import Callable, Iterator
from typing import Any
from urllib.parse import parse_qs

SERVICE_NAME = "golden-dataset-studio"
ENV_BROWSER_ENDPOINT = "GOLDEN_DATASETS_OTEL_BROWSER_ENDPOINT"  # e.g. /otlp/v1/traces (same origin as the Studio)
ENV_BROWSER_SAMPLE = "GOLDEN_DATASETS_OTEL_BROWSER_SAMPLE_RATE"  # 1 = every page view (the default), 10 = one in ten

#: Baggage keys the web app sends; copied onto every span of the request. Baggage comes from the browser, so it says
#: who the browser says it is: the Studio's profiles are not authenticated either (shell/reviewer.ts).
BAGGAGE_KEYS = ("user.id", "user.roles", "session.id", "ce.page", "ce.page_view.id")
#: Path parameters of the Studio's routes, recorded as `ce.<name>` (catalog gets its own `ce.catalog.*` attributes)
PATH_PARAMS = {"rule_id": "ce.rule.id", "stem": "ce.page.stem", "run_id": "ce.agent_run.id", "sid": "ce.score.id",
               "vid": "ce.golden.version", "course_key": "ce.course.key", "table": "ce.golden.table",
               "record_external_identifier": "ce.record.external_identifier", "cls": "ce.class",
               "column": "ce.property.column", "finding_id": "ce.finding.id",
               "version": "ce.ruleset.version", "sha256": "ce.asset.sha256"}
#: Query parameters worth keeping (values are short; `q` is what a reviewer typed in a search box)
QUERY_PARAMS = {"ext": "ce.extraction.id", "rule": "ce.rule.id", "offset": "ce.query.offset", "limit": "ce.query.limit",
                "q": "ce.query.q", "basis": "ce.score.basis", "tree": "ce.golden.tree", "a": "ce.compare.a",
                "b": "ce.compare.b", "column": "ce.score.column", "class": "ce.class"}
#: Requests made many times per page view, marked `ce.request.type` so a collector can drop the fast, successful ones:
#: `poll`, the web app's timers (live AI runs, every 3 s), and `asset`, a saved page's CSS, fonts and images.
POLL_ROUTES = ("/agent-runs/current", "/agent-runs/queue")
#: Not traced: health checks and the built web app's files (regexes, searched in the full URL)
EXCLUDED_URLS = r"/api/health$,//[^/]+/(assets|logos)/,//[^/]+/[^/]+\.(ico|svg|png|js|css|txt)$"
#: Resource attributes the web app's spans repeat (prefixes): the build (vcs.*, including the pull request's
#: vcs.change.*; cicd.*), the change and who made and shipped it (ce.vcs.*, ce.cicd.*, ce.deploy.*), the deployment and
#: the pod that served the page (k8s.*, host.name). Not process.* or telemetry.*: those describe this Python process.
BROWSER_RESOURCE_KEYS = ("service.version", "service.namespace", "deployment.", "vcs.", "cicd.", "k8s.", "host.",
                         "ce.vcs.", "ce.cicd.", "ce.deploy.")
MAX_VALUE = 256  # characters kept of a string attribute that comes from a request

_enabled = False
_tracer = None
# per request: counters summed into ce.storage.* (shared by the threads that copy the request's context) and the
# who/what attributes the request's sub-spans repeat
_counters: contextvars.ContextVar[dict | None] = contextvars.ContextVar("ce_counters", default=None)
_inherited: contextvars.ContextVar[dict | None] = contextvars.ContextVar("ce_inherited", default=None)
_counting = threading.Lock()  # a request's thread pool adds to its counters from several threads at once


def enabled() -> bool:
    return _enabled


def configured() -> bool:
    """True when the environment asks for traces: an OTLP endpoint, and the SDK not disabled."""
    if os.environ.get("OTEL_SDK_DISABLED", "").strip().lower() == "true":
        return False
    return bool(os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT") or os.environ.get("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT"))


# -- setup ------------------------------------------------------------------------------------------------------
def init(exporter=None) -> bool:
    """Start the tracer provider once per process. Returns whether telemetry is on. `exporter` (tests): send spans
    there instead of OTLP."""
    global _enabled, _tracer
    if _enabled:
        return True
    if exporter is None and not configured():
        return False
    try:
        from opentelemetry import trace
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor, SimpleSpanProcessor
    except ImportError:
        print("telemetry: OTEL_EXPORTER_OTLP_* is set but the otel extra isn't installed (uv sync --extra otel); "
              "no traces", file=sys.stderr)
        return False
    from . import __version__

    os.environ.setdefault("OTEL_SEMCONV_STABILITY_OPT_IN", "http")  # http.request.method, url.path... (stable names)
    provider = TracerProvider(resource=resource())  # sampler: OTEL_TRACES_SAMPLER, default parent-based always-on
    if exporter is None:
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

        provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
    else:
        provider.add_span_processor(SimpleSpanProcessor(exporter))
    trace.set_tracer_provider(provider)
    _tracer = trace.get_tracer("golden_datasets", __version__)
    _enabled = True
    return True


def resource():
    """This process's OpenTelemetry Resource: the code's defaults first, then OTEL_SERVICE_NAME and
    OTEL_RESOURCE_ATTRIBUTES (percent-decoded by the SDK), which win. Needs the otel extra."""
    from opentelemetry.sdk.resources import OTELResourceDetector, Resource

    from . import __version__

    return Resource.create({
        "service.name": SERVICE_NAME, "service.version": __version__,
        "process.runtime.name": sys.implementation.name, "process.runtime.version": sys.version.split()[0],
        "process.pid": os.getpid(),
    }).merge(OTELResourceDetector().detect())


def install(app, exporter=None) -> bool:
    """Trace the FastAPI app (call once, before it serves). No-op unless `init` turns telemetry on."""
    if not init(exporter):
        return False
    from opentelemetry import trace
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

    app.add_middleware(WideSpanMiddleware)
    # receive/send would add two spans per request that say nothing the server span doesn't
    FastAPIInstrumentor.instrument_app(app, excluded_urls=EXCLUDED_URLS, exclude_spans=["receive", "send"],
                                       tracer_provider=trace.get_tracer_provider())
    return True


def browser_config() -> dict | None:
    """What the web app needs to send spans, or None: no endpoint, no telemetry in the browser.
    `resource` is this server's deployment identity, so browser spans say which build, change, deployment and pod
    served them (the collector can't tell a browser span's pod: it comes through the Ingress)."""
    endpoint = os.environ.get(ENV_BROWSER_ENDPOINT)
    if not (_enabled and endpoint):
        return None
    from opentelemetry import trace

    keep = BROWSER_RESOURCE_KEYS
    attrs = getattr(trace.get_tracer_provider(), "resource", None)
    resource = {k: v for k, v in (attrs.attributes.items() if attrs else ()) if k.startswith(keep)}
    try:
        sample = max(1, int(os.environ.get(ENV_BROWSER_SAMPLE, "1")))
    except ValueError:
        sample = 1
    return {"endpoint": endpoint, "sample_rate": sample, "resource": resource}


def browser_page(index_html) -> str | None:
    """The web app's index.html with `browser_config()` inlined (`<script id="otel-config" type="application/json">`),
    or None when browser telemetry is off: then the file is served as it is."""
    cfg = browser_config()
    if cfg is None:
        return None
    import json
    from pathlib import Path

    html = Path(index_html).read_text(encoding="utf-8")
    data = json.dumps(cfg).replace("<", "\\u003c")  # nothing in it can close the script element
    tag = f'<script id="otel-config" type="application/json">{data}</script>'
    return html.replace("</head>", tag + "</head>", 1)


# -- helpers for app code (no-ops when telemetry is off) --------------------------------------------------------------
def set(attrs: dict[str, Any]) -> None:  # noqa: A001 - telemetry.set({...}) reads well at call sites
    """Add attributes to the current span (the request's, or a sub-span's): `{"ce.rows.returned": 40}`. None values
    are skipped."""
    if not _enabled:
        return
    from opentelemetry import trace

    current = trace.get_current_span()
    if current.is_recording():
        for k, v in attrs.items():
            if v is not None:
                current.set_attribute(k, _value(v))


def error(exc: BaseException) -> None:
    """Mark the current span failed by `exc` (an exception event, `error.type`, status ERROR) when the code handles the
    exception itself, so the instrumentation never sees it."""
    if not _enabled:
        return
    from opentelemetry import trace

    current = trace.get_current_span()
    if current.is_recording():
        current.record_exception(exc)
        current.set_attribute("error.type", type(exc).__qualname__)
        current.set_status(trace.Status(trace.StatusCode.ERROR, str(exc)[:MAX_VALUE]))


def count(name: str, n: float = 1) -> None:
    """Add `n` to the request's counter `name` (reported as `ce.<name>` on the request's span when it ends)."""
    if not _enabled:
        return
    c = _counters.get()
    if c is not None:
        with _counting:
            c[name] = c.get(name, 0) + n


def in_this_request(fn: Callable) -> Callable:
    """`fn`, to run in a worker thread (a `ThreadPoolExecutor`) as part of this request: its storage reads count on the
    request's span and its sub-spans are children of the current one. A pool's threads don't inherit the request's
    context, so without this a cold snapshot's parquet downloads, the biggest reads the Studio makes, went uncounted.
    Off, `fn` itself."""
    if not _enabled:
        return fn
    request_context = contextvars.copy_context()

    def run_in_request(*a, **kw):
        one_thread_copy = request_context.copy()  # a Context can be entered by one thread at a time
        return one_thread_copy.run(fn, *a, **kw)
    return run_in_request


@contextlib.contextmanager
def span(name: str, attrs: dict[str, Any] | None = None) -> Iterator[None]:
    """A sub-span of the current span, carrying the request's user and page."""
    if not _enabled:
        yield
        return
    with _tracer.start_as_current_span(name, attributes=_attrs(attrs or {})):
        yield


@contextlib.contextmanager
def job(name: str, attrs: dict[str, Any] | None = None, carried: dict | None = None) -> Iterator[None]:
    """The root span of background work a request started (a score, adding a catalog): a trace of its own, linked to
    the request's. Use it in the thread that does the work, with `carried=carry()` taken in the request."""
    if not _enabled:
        yield
        return
    from opentelemetry import context, trace

    carried = carried or {}
    links = [trace.Link(carried["span"])] if carried.get("span") else []
    token = context.attach(context.Context())  # a new trace, not a child of whatever this thread had
    try:
        with _tracer.start_as_current_span(name, links=links, attributes=_attrs(attrs or {}, carried.get("attrs"))):
            yield
    finally:
        context.detach(token)


def carry() -> dict:
    """What `job(..., carried=carry())` needs from the request that starts background work."""
    if not _enabled:
        return {}
    from opentelemetry import trace

    ctx = trace.get_current_span().get_span_context()
    return {"span": ctx if ctx.is_valid else None, "attrs": dict(_inherited.get() or {})}


def storage_op(kind: str):
    """Decorator for storage methods: counts calls, bytes and time into the request's `ce.stats.storage.*` (Honeycomb's
    advice: roll-up counts on the request's span rather than a span per blob read)."""
    def wrap(fn):
        def inner(self, *a, **kw):
            if not _enabled or _counters.get() is None:
                return fn(self, *a, **kw)
            started = time.perf_counter()
            where = "azure" if self.uri.startswith("azure://") else "local"
            try:
                out = fn(self, *a, **kw)
            finally:  # a missing file (FileNotFoundError) still took a round trip
                elapsed_ms = (time.perf_counter() - started) * 1000
                count(f"stats.storage.{where}.{kind}s")
                count(f"stats.storage.{where}.duration_ms", elapsed_ms)
            if kind == "read" and isinstance(out, bytes | bytearray):
                count(f"stats.storage.{where}.bytes_read", len(out))
            data = a[1] if len(a) > 1 else kw.get("data")
            if kind == "write" and isinstance(data, bytes | bytearray):
                count(f"stats.storage.{where}.bytes_written", len(data))
            return out
        inner.__name__, inner.__doc__, inner.__wrapped__ = fn.__name__, fn.__doc__, fn
        return inner
    return wrap


# -- the request middleware -------------------------------------------------------------------------------------
class WideSpanMiddleware:
    """Pure ASGI: runs inside the instrumentation's server span and adds the wide attributes when the request ends."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or not _enabled:
            await self.app(scope, receive, send)
            return
        from opentelemetry import trace

        server_span = trace.get_current_span()
        who = _who(scope)
        counters: dict = {}
        t1 = _counters.set(counters)
        t2 = _inherited.set(who)
        state = {"status": 0, "size": 0, "error_body": b"", "flushed": False}

        def flush() -> None:
            # the instrumentation ends the server span as it sends the last body chunk: set everything before that
            if state["flushed"] or not server_span.is_recording():
                return
            state["flushed"] = True
            who_asked = who                          # user.id, session.id, ce.page: from the browser's baggage
            what_they_asked = _what(scope)           # ce.catalog, ce.rule.id, ce.query.q...: from the URL
            storage_work = _storage(counters)        # ce.stats.storage.*: what the request read and wrote
            error_detail = _error(state)             # ce.error.detail, on a 4xx/5xx
            for key, value in {**who_asked, **what_they_asked, **storage_work, **error_detail}.items():
                server_span.set_attribute(key, value)
            server_span.set_attribute("http.response.body.size", state["size"])

        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                state["status"] = message["status"]
            elif message["type"] == "http.response.body":
                body = message.get("body", b"")
                state["size"] += len(body)
                if state["status"] >= 400 and len(state["error_body"]) < 2048:
                    state["error_body"] += body[:2048]
                is_last_chunk = not message.get("more_body", False)
                if is_last_chunk:
                    flush()
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            flush()  # no response was sent (an exception): the span is still open
            _counters.reset(t1)
            _inherited.reset(t2)


def _who(scope) -> dict:
    """user.id, user.roles, session.id, ce.page from the W3C baggage header (only these keys, values capped)."""
    raw = next((v.decode("latin-1") for k, v in scope.get("headers", []) if k == b"baggage"), "")
    out: dict = {}
    if raw:
        from urllib.parse import unquote

        for item in raw.split(",")[:32]:
            k, _, v = item.split(";")[0].partition("=")
            k, v = k.strip(), unquote(v.strip())
            if k in BAGGAGE_KEYS and v:
                out[k] = [r for r in v.split("|") if r][:8] if k == "user.roles" else v[:MAX_VALUE]
    return out


def _what(scope) -> dict:
    from .catalogs import info, resolve

    out: dict = {}
    params = scope.get("path_params") or {}
    if params.get("catalog"):
        folder = resolve(params["catalog"])
        meta = info(folder)
        out.update({"ce.catalog.folder": folder, "ce.catalog": meta["short"], "ce.catalog.platform": meta["platform"]})
    for k, v in params.items():
        if k in PATH_PARAMS:
            out[PATH_PARAMS[k]] = str(v)[:MAX_VALUE]
    qs = parse_qs(scope.get("query_string", b"").decode("latin-1"))
    for k, attr in QUERY_PARAMS.items():
        if qs.get(k) and attr not in out:
            out[attr] = qs[k][0][:MAX_VALUE]
    if params.get("catalog") and "ce.class" not in out:  # a catalog's routes serve Course unless ?class= says (ClassParam)
        out["ce.class"] = "course"
    path = scope.get("path", "")
    if path.endswith(POLL_ROUTES):
        out["ce.request.type"] = "poll"
    elif "sha256" in params:
        out["ce.request.type"] = "asset"
    return out


def _storage(counters: dict) -> dict:
    return {f"ce.{k}": (round(v, 1) if isinstance(v, float) else v) for k, v in counters.items()}


def _error(state: dict) -> dict:
    if state["status"] < 400 or not state["error_body"]:
        return {}
    import json

    try:
        detail = json.loads(state["error_body"]).get("detail")
    except (ValueError, AttributeError):
        return {}
    return {"ce.error.detail": str(detail)[:MAX_VALUE]} if detail else {}


def _value(v: Any):
    if isinstance(v, bool | int | float | str):
        return v[:MAX_VALUE * 4] if isinstance(v, str) else v
    if isinstance(v, list | tuple):
        return [x if isinstance(x, bool | int | float | str) else str(x) for x in v][:64]
    return str(v)[:MAX_VALUE * 4]


def _attrs(attrs: dict, base: dict | None = None) -> dict:
    out = dict(base if base is not None else (_inherited.get() or {}))
    out.update({k: _value(v) for k, v in attrs.items() if v is not None})
    return out
