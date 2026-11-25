// Page views: one `page_view` span per route the reader opens, ended once the page's API calls have finished.
import { ROOT_CONTEXT, SpanStatusCode, type Attributes, type Span } from "@opentelemetry/api";
import { parseRoute } from "../shell/router";
import { pageInfo, type PageInfo } from "./names";
import { routeNow, state, tracer, type View } from "./state";
import { whoAndWhere } from "./who";

const IDLE_MS = 500;      // a page is ready once no API call has run for this long...
const MAX_VIEW_MS = 30000; // ...or after this long, whatever is still loading

export function pageView(page: PageInfo): void {
  if (state.view?.implicit && state.view.route === routeNow()) nameOpenView(state.view, page);
  else startView(page, false);
}

// the app hasn't said which page this is yet: the URL does
export function startViewFromAddress(): void {
  const route = parseRoute(location.hash);
  startView(pageInfo(true, route.catalog, route.tab, route.id, route.cls), true);
}

// leaving the page: end the view first (capture on window runs before the SDK's flush on document)
export function endViewWhenLeaving(): void {
  window.addEventListener("visibilitychange", () => { if (document.visibilityState === "hidden") endView("hidden"); },
    true);
  window.addEventListener("pagehide", () => endView("hidden"), true);
}

export function countCallEnd(view: View, callMs: number, ok: boolean, bytes: number): void {
  view.inflight--;
  view.apiMs += callMs;
  view.bytes += bytes;
  view.slowest = Math.max(view.slowest, callMs);
  view.lastActivity = performance.now();
  if (!ok) view.errors++;
  const stillTheCurrentView = state.view === view;
  if (stillTheCurrentView) settle();
}

// a request already opened this route's view (React runs a child's effects before its parent's): name it
function nameOpenView(view: View, page: PageInfo): void {
  view.implicit = false;
  view.page = page;
  state.page = page;
  if (state.entryPage !== null && view.span.spanContext().spanId === state.firstViewId) state.entryPage = page.page;
  view.span.setAttributes(whoAndWhere());
}

function startView(page: PageInfo, implicit: boolean): void {
  endView("navigated");
  // hard: the browser loaded the Studio from scratch (this is its first page); soft: the app swapped the screen
  const isHardLoad = state.entryPage === null;
  state.page = page;
  if (isHardLoad) state.entryPage = page.page;
  // a hard load's view starts when the browser started navigating (time 0), a soft one at the route change
  const viewStartMs = isHardLoad ? 0 : performance.now();
  const span = startPageViewSpan(isHardLoad, viewStartMs);
  if (isHardLoad) state.firstViewId = span.spanContext().spanId;
  const view = openView(span, page, implicit, viewStartMs);
  span.setAttribute("ce.page_view.id", view.id);
  view.maxTimer = window.setTimeout(() => endView("timeout"), MAX_VIEW_MS);
  settle();
}

function endView(reason: string): void {
  const view = state.view;
  if (!view) return;
  state.view = null;
  window.clearTimeout(view.quietTimer);
  window.clearTimeout(view.maxTimer);
  view.span.setAttributes(pageStats(view, reason));
  if (view.errors) view.span.setStatus({ code: SpanStatusCode.ERROR, message: `${view.errors} API call(s) failed` });
  const lastCallEndedAt = performance.timeOrigin + view.lastActivity; // the span ends when the page was ready
  view.span.end(lastCallEndedAt);
}

function settle(): void {
  const view = state.view;
  if (!view) return;
  window.clearTimeout(view.quietTimer); // a call ended: the quiet period starts over
  const noCallsInFlight = view.inflight === 0;
  if (noCallsInFlight) view.quietTimer = window.setTimeout(() => endView("ready"), IDLE_MS);
  const viewAgeMs = performance.now() - view.start;
  if (viewAgeMs > MAX_VIEW_MS) endView("timeout");
}

function startPageViewSpan(isHardLoad: boolean, viewStartMs: number): Span {
  const navigationKind = isHardLoad ? "hard" : "soft";
  const route = location.hash.replace(/^#/, "");
  return tracer().startSpan("page_view", {
    startTime: performance.timeOrigin + viewStartMs,
    attributes: { "ce.page_view.kind": navigationKind, "url.fragment": route },
  }, ROOT_CONTEXT);
}

function openView(span: Span, page: PageInfo, implicit: boolean, viewStartMs: number): View {
  state.view = {
    span, id: span.spanContext().spanId, page, route: routeNow(), implicit, start: viewStartMs,
    lastActivity: performance.now(), inflight: 0,
    calls: 0, errors: 0, polls: 0, bytes: 0, apiMs: 0, slowest: 0,
  };
  return state.view;
}

// "ready" = from the route change to the end of the page's last API call: what the reader waited for
function pageStats(view: View, reason: string): Attributes {
  return {
    "ce.page_view.end_reason": reason,
    "ce.page.ready.duration_ms": Math.round(view.lastActivity - view.start),
    "ce.stats.api.calls": view.calls,
    "ce.stats.api.errors": view.errors,
    "ce.stats.api.polls": view.polls,
    "ce.stats.api.bytes": view.bytes,
    "ce.stats.api.duration_ms": Math.round(view.apiMs),
    "ce.stats.api.slowest_ms": Math.round(view.slowest),
    "ce.stats.api.inflight": view.inflight,
    "ce.page.dom_nodes": document.getElementsByTagName("*").length,
  };
}
