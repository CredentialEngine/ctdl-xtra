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
import { currentReviewer, currentRole } from "../shell/reviewer";
import { actionOf, POLL, urlTemplate, type PageInfo } from "./names";

export interface BrowserConfig { endpoint: string; sample_rate: number; resource: Record<string, string> }
export interface Impl { pageView(p: PageInfo): void }

const SERVICE = "golden-dataset-studio-web";
const IDLE_MS = 500;      // a page is ready once no API call has run for this long...
const MAX_VIEW_MS = 30000; // ...or after this long, whatever is still loading

interface View {
  span: Span; id: string; page: PageInfo; start: number; lastActivity: number; inflight: number;
  calls: number; errors: number; polls: number; bytes: number; apiMs: number; slowest: number; timer?: number;
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
      ...(page?.catalog ? { "ce.catalog": page.catalog } : {}),
      ...(page?.id ? { [page.page === "records" ? "ce.course.key" : "ce.rule.id"]: page.id } : {}),
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
    window.clearTimeout(v.timer);
    v.span.setAttributes({
      "ce.page_view.end_reason": reason, "ce.page.ready.duration_ms": Math.round(v.lastActivity - v.start),
      "ce.stats.api.calls": v.calls, "ce.stats.api.errors": v.errors, "ce.stats.api.polls": v.polls,
      "ce.stats.api.bytes": v.bytes, "ce.stats.api.duration_ms": Math.round(v.apiMs),
      "ce.stats.api.slowest_ms": Math.round(v.slowest), "ce.stats.api.inflight": v.inflight,
      "ce.page.dom_nodes": document.getElementsByTagName("*").length,
    });
    if (v.errors) v.span.setStatus({ code: SpanStatusCode.ERROR, message: `${v.errors} API call(s) failed` });
    v.span.end(performance.timeOrigin + v.lastActivity);
  }
  function settle() {
    const v = view;
    if (!v) return;
    window.clearTimeout(v.timer);
    if (v.inflight === 0) v.timer = window.setTimeout(() => endView("ready"), IDLE_MS);
    if (performance.now() - v.start > MAX_VIEW_MS) endView("timeout");
  }
  function pageView(p: PageInfo) {
    endView("navigated");
    const hard = entryPage === null;
    page = p;
    if (hard) entryPage = p.page;
    const start = hard ? 0 : performance.now(); // the first page view starts with the navigation
    const span = tracer.startSpan("page_view", {
      startTime: performance.timeOrigin + start,
      attributes: { "ce.page_view.kind": hard ? "hard" : "soft", "url.fragment": location.hash.replace(/^#/, "") },
    }, ROOT_CONTEXT);
    view = { span, id: span.spanContext().spanId, page: p, start, lastActivity: performance.now(), inflight: 0,
             calls: 0, errors: 0, polls: 0, bytes: 0, apiMs: 0, slowest: 0 };
    span.setAttribute("ce.page_view.id", view.id);
    view.timer = window.setTimeout(() => endView("timeout"), MAX_VIEW_MS);
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
    if (url.origin !== location.origin || !url.pathname.startsWith("/api/") || url.pathname === "/api/telemetry") {
      return original(input, init);
    }
    const method = (init?.method ?? (input instanceof Request ? input.method : "GET")).toUpperCase();
    const template = urlTemplate(url.pathname);
    const action = actionOf(method, template);
    const poll = POLL.test(url.pathname);
    const v = view;
    const parent: Context = !action && v ? trace.setSpan(ROOT_CONTEXT, v.span) : ROOT_CONTEXT;
    const span = poll ? null : tracer.startSpan(action ? `${action}` : `${method} ${template}`, {
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

    if (v && poll) v.polls++;
    if (v && !poll && !action) { v.inflight++; v.calls++; }
    const t0 = performance.now();
    const done = (ok: boolean, bytes: number) => {
      const ms = performance.now() - t0;
      if (v && !poll && !action) {
        v.inflight--; v.apiMs += ms; v.bytes += bytes; v.slowest = Math.max(v.slowest, ms);
        v.lastActivity = performance.now();
        if (!ok) v.errors++;
        if (view === v) settle();
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
