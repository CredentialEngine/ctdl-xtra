// The web app's OpenTelemetry, loaded only when the server says where to send spans (index.ts). Few, wide spans:
//
// - `page_view`: one per route the reader opens (a trace of its own). It starts at the route change (at navigation start
//   for the first one after a hard load) and ends when the page's API calls have finished (`ce.page.ready.duration_ms`),
//   with counts of what loading took (`ce.stats.api.*`) and how big the page got (`ce.page.dom_nodes`).
// - one client span per API call, a child of the page view while it is loading (else its own trace). Its `traceparent`
//   makes the server's span its child: one connected trace from the click to the storage read. Changes (POST, DELETE)
//   always start their own trace, named by `ce.action`. Timed polls get no span, only a count on the page view.
// - Honeycomb's Web SDK adds the web vitals (FCP, LCP, INP, CLS, TTFB spans), uncaught errors (`exception` spans),
//   browser and session attributes (`session.id` from a session kept in localStorage: 30 min idle, 12 h at most).
//
// Every span gets who and where: `user.id` and `user.roles` (the profile picked on "Who are you?"), `ce.page`,
// `ce.catalog`, `ce.rule.id`, `ce.page_view.id`, `ce.entry_page` (the page the browser loaded first). The same who and
// where go to the server as W3C baggage. Where the spans go and which build sent them come from GET /api/telemetry.
import { HoneycombWebSDK } from "@honeycombio/opentelemetry-web";
import {
  context, propagation, ROOT_CONTEXT, SpanKind, SpanStatusCode, trace, type Attributes, type Context, type Span,
} from "@opentelemetry/api";
import {
  createDefaultSessionIdGenerator, createLocalStorageSessionStore, createSessionManager,
} from "@opentelemetry/web-common";
import { parseRoute } from "../shell/router";
import { currentReviewer, currentRole } from "../shell/reviewer";
import { actionOf, pageInfo, POLL, urlTemplate, type PageInfo } from "./names";

export interface BrowserConfig { endpoint: string; sample_rate: number; resource: Record<string, string> }
export interface Impl { pageView(p: PageInfo): void }

const SERVICE = "golden-dataset-studio-web";
const IDLE_MS = 500;      // a page is ready once no API call has run for this long...
const MAX_VIEW_MS = 30000; // ...or after this long, whatever is still loading

interface View {
  span: Span; id: string; page: PageInfo; route: string; implicit: boolean; start: number; lastActivity: number; inflight: number;
  calls: number; errors: number; polls: number; bytes: number; apiMs: number; slowest: number;
  quietTimer?: number; // ends the view once no call has run for IDLE_MS
  maxTimer?: number;   // ends it after MAX_VIEW_MS, whatever is still loading
}

export async function init(cfg: BrowserConfig): Promise<Impl> {
  const sessions = createSessionManager({
    sessionIdGenerator: createDefaultSessionIdGenerator(), sessionStore: createLocalStorageSessionStore(),
    inactivityTimeout: 30 * 60, maxDuration: 12 * 3600,
  });
  await sessions.start(); // before any span: until then it hands out a temporary id, not the stored session
  let page: PageInfo | null = null;
  let entryPage: string | null = null;
  let view: View | null = null;

  const who = (): Attributes => {
    const role = currentRole();
    return {
      ...(currentReviewer() ? { "user.id": currentReviewer() } : {}), ...(role ? { "user.roles": [role] } : {}),
      ...(page ? { "ce.page": page.page, "ce.page.template": page.template } : {}),
      ...(page?.catalog ? { "ce.catalog": page.catalog } : {}), ...(page?.cls ? { "ce.class": page.cls } : {}),
      ...(page?.id ? { [page.page === "records" ? "ce.record.external_identifier" : "ce.rule.id"]: page.id } : {}),
      ...(view ? { "ce.page_view.id": view.id } : {}), ...(entryPage ? { "ce.entry_page": entryPage } : {}),
    };
  };

  new HoneycombWebSDK({
    serviceName: SERVICE,
    tracesEndpoint: new URL(cfg.endpoint, location.href).href,
    disableDefaultMetricExporter: true, // traces only: the numbers go on spans
    disableDefaultLogExporter: true,
    skipOptionsValidation: true, // no Honeycomb API key: the endpoint is the Studio's own collector
    sampleRate: cfg.sample_rate,
    resourceAttributes: cfg.resource,
    sessionProvider: sessions,
    instrumentations: [], // the SDK adds web vitals and global errors itself; fetch spans are made below
    // TTFB and CLS are floats, and TraceQL's quantile_over_time skips float attributes: integer copies for p75s
    webVitalsInstrumentationConfig: {
      ttfb: {
        applyCustomAttributes: (ttfb, span) => {
          const timeToFirstByteUs = Math.round(ttfb.value * 1000); // ms -> whole microseconds
          span.setAttribute("ce.ttfb.value_us", timeToFirstByteUs);
        },
      },
      cls: {
        applyCustomAttributes: (cls, span) => {
          const layoutShiftThousandths = Math.round(cls.value * 1000); // a score like 0.042 -> 42
          span.setAttribute("ce.cls.value_milli", layoutShiftThousandths);
        },
      },
    },
    spanProcessors: [{
      onStart: (span: Span) => span.setAttributes(who()),
      onEnd: () => {}, forceFlush: () => Promise.resolve(), shutdown: () => Promise.resolve(),
    }],
  }).start();
  const tracer = trace.getTracer(SERVICE);

  // -- page views ----------------------------------------------------------------------------------------------------
  function endView(reason: string) {
    const v = view;
    if (!v) return;
    view = null;
    window.clearTimeout(v.quietTimer);
    window.clearTimeout(v.maxTimer);
    // "ready" = from the route change to the end of the page's last API call: what the reader waited for
    const timeToReadyMs = Math.round(v.lastActivity - v.start);
    const slowestCallMs = Math.round(v.slowest);
    const totalCallTimeMs = Math.round(v.apiMs);
    const domNodeCount = document.getElementsByTagName("*").length;
    v.span.setAttributes({
      "ce.page_view.end_reason": reason,
      "ce.page.ready.duration_ms": timeToReadyMs,
      "ce.stats.api.calls": v.calls,
      "ce.stats.api.errors": v.errors,
      "ce.stats.api.polls": v.polls,
      "ce.stats.api.bytes": v.bytes,
      "ce.stats.api.duration_ms": totalCallTimeMs,
      "ce.stats.api.slowest_ms": slowestCallMs,
      "ce.stats.api.inflight": v.inflight,
      "ce.page.dom_nodes": domNodeCount,
    });
    if (v.errors) v.span.setStatus({ code: SpanStatusCode.ERROR, message: `${v.errors} API call(s) failed` });
    const lastCallEndedAt = performance.timeOrigin + v.lastActivity; // the span ends when the page was ready
    v.span.end(lastCallEndedAt);
  }
  function settle() {
    const v = view;
    if (!v) return;
    window.clearTimeout(v.quietTimer); // a call ended: the quiet period starts over
    const noCallsInFlight = v.inflight === 0;
    if (noCallsInFlight) v.quietTimer = window.setTimeout(() => endView("ready"), IDLE_MS);
    const viewAgeMs = performance.now() - v.start;
    if (viewAgeMs > MAX_VIEW_MS) endView("timeout");
  }
  // the route without its query: ?row= changes as rows are picked, and that is not a new page
  const routeNow = () => location.hash.split("?")[0];
  function pageView(p: PageInfo) {
    if (view?.implicit && view.route === routeNow()) {
      // a request already opened this route's view (React runs a child's effects before its parent's): name it
      view.implicit = false;
      view.page = p;
      page = p;
      if (entryPage !== null && view.span.spanContext().spanId === firstViewId) entryPage = p.page;
      view.span.setAttributes(who());
      return;
    }
    startView(p, false);
  }
  let firstViewId: string | null = null;
  function startView(p: PageInfo, implicit: boolean) {
    endView("navigated");
    // hard: the browser loaded the Studio from scratch (this is its first page); soft: the app swapped the screen
    const isHardLoad = entryPage === null;
    page = p;
    if (isHardLoad) entryPage = p.page;
    // a hard load's view starts when the browser started navigating (time 0), a soft one at the route change
    const viewStartMs = isHardLoad ? 0 : performance.now();
    const navigationKind = isHardLoad ? "hard" : "soft";
    const route = location.hash.replace(/^#/, "");
    const span = tracer.startSpan("page_view", {
      startTime: performance.timeOrigin + viewStartMs,
      attributes: { "ce.page_view.kind": navigationKind, "url.fragment": route },
    }, ROOT_CONTEXT);
    if (isHardLoad) firstViewId = span.spanContext().spanId;
    view = { span, id: span.spanContext().spanId, page: p, route: routeNow(), implicit, start: viewStartMs,
             lastActivity: performance.now(), inflight: 0,
             calls: 0, errors: 0, polls: 0, bytes: 0, apiMs: 0, slowest: 0 };
    span.setAttribute("ce.page_view.id", view.id);
    view.maxTimer = window.setTimeout(() => endView("timeout"), MAX_VIEW_MS);
    settle();
  }
  // leaving the page: end the view first (capture on window runs before the SDK's flush on document)
  window.addEventListener("visibilitychange", () => { if (document.visibilityState === "hidden") endView("hidden"); },
    true);
  window.addEventListener("pagehide", () => endView("hidden"), true);

  // -- API calls -----------------------------------------------------------------------------------------------------
  const original = window.fetch.bind(window);
  window.fetch = async (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
    const href = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
    const url = new URL(href, location.href);
    const isStudioApi = url.origin === location.origin && url.pathname.startsWith("/api/");
    const isTelemetryConfig = url.pathname === "/api/telemetry";
    if (!isStudioApi || isTelemetryConfig) return original(input, init); // not ours to trace
    const method = (init?.method ?? (input instanceof Request ? input.method : "GET")).toUpperCase();
    const template = urlTemplate(url.pathname);
    const action = actionOf(method, template);
    const poll = POLL.test(url.pathname);
    if (!action && !poll && (!view || view.route !== routeNow())) {
      const r = parseRoute(location.hash); // the app hasn't said which page this is yet: the URL does
      startView(pageInfo(true, r.catalog, r.tab, r.id, r.cls), true);
    }
    const v = view;
    // a read made while a page loads belongs to that page view; a change (POST, DELETE) is a trace of its own
    const parent: Context = !action && v ? trace.setSpan(ROOT_CONTEXT, v.span) : ROOT_CONTEXT;
    const spanName = action ? `${action}` : `${method} ${template}`;
    const span = poll ? null : tracer.startSpan(spanName, {
      kind: SpanKind.CLIENT,
      attributes: {
        "http.request.method": method, "url.full": url.href, "url.path": url.pathname, "url.template": template,
        "server.address": url.hostname, ...(action ? { "ce.action": action } : {}),
      },
    }, parent);
    // who and where travel as baggage, so the server's span carries them too
    let ctx = span ? trace.setSpan(parent, span) : parent;
    const w = who();
    const entries: Record<string, { value: string }> = {};
    for (const k of ["user.id", "ce.page", "ce.page_view.id"] as const) if (w[k]) entries[k] = { value: String(w[k]) };
    if (w["user.roles"]) entries["user.roles"] = { value: (w["user.roles"] as string[]).join("|") };
    const sid = sessions.getSessionId();
    if (sid) entries["session.id"] = { value: sid };
    ctx = propagation.setBaggage(ctx, propagation.createBaggage(entries));
    const headers = new Headers(init?.headers ?? (input instanceof Request ? input.headers : undefined));
    propagation.inject(ctx, headers, { set: (h, k, val) => h.set(k, val) });

    const countsTowardPage = v && !poll && !action; // the page's own reads: what "ready" waits for
    if (v && poll) v.polls++;
    if (countsTowardPage) {
      v.inflight++;
      v.calls++;
      window.clearTimeout(v.quietTimer); // a call started, so the page isn't quiet: no "ready" until it ends
    }
    const callStartedAt = performance.now();
    const done = (ok: boolean, bytes: number) => {
      const callMs = performance.now() - callStartedAt;
      if (countsTowardPage) {
        v.inflight--;
        v.apiMs += callMs;
        v.bytes += bytes;
        v.slowest = Math.max(v.slowest, callMs);
        v.lastActivity = performance.now();
        if (!ok) v.errors++;
        const stillTheCurrentView = view === v;
        if (stillTheCurrentView) settle();
      }
    };
    try {
      const r = await context.with(ctx, () => original(input, { ...init, headers }));
      const bytes = Number(r.headers.get("content-length") || 0);
      span?.setAttributes({ "http.response.status_code": r.status, ...(bytes ? { "http.response.body.size": bytes } : {}) });
      if (r.status >= 400) {
        span?.setAttribute("error.type", String(r.status));
        span?.setStatus({ code: SpanStatusCode.ERROR }); // a client span's 4xx is an error (semconv)
      }
      span?.end();
      done(r.ok, bytes);
      return r;
    } catch (e) {
      const name = e instanceof Error ? e.name : "Error";
      if (name === "AbortError") span?.setAttribute("ce.request.aborted", true);
      else {
        span?.setAttribute("error.type", name);
        span?.recordException(e as Error);
        span?.setStatus({ code: SpanStatusCode.ERROR, message: String(e) });
      }
      span?.end();
      done(name === "AbortError", 0);
      throw e;
    }
  };

  return { pageView };
}
