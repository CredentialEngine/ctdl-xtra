// API calls: one client span per call to the Studio's API, carrying the trace context and the who and where to the
// server. A page's own reads are children of its page view; a change (POST, DELETE) is a trace of its own.
import {
  context, propagation, ROOT_CONTEXT, SpanKind, SpanStatusCode, trace, type Context, type Span,
} from "@opentelemetry/api";
import { actionOf, POLL, urlTemplate } from "./names";
import { countCallEnd, startViewFromAddress } from "./pageViews";
import { routeNow, state, tracer, type View } from "./state";
import { baggageEntries } from "./who";

interface ApiCall {
  input: RequestInfo | URL; init?: RequestInit;
  url: URL; method: string; template: string; action: string | null; poll: boolean;
}
type CallEnd = (ok: boolean, bytes: number) => void;

let sendUntraced: typeof fetch = window.fetch;

export function traceApiCalls(): void {
  sendUntraced = window.fetch.bind(window);
  window.fetch = async (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
    const url = new URL(hrefOf(input), location.href);
    if (!isTraced(url)) return sendUntraced(input, init);
    return traceCall(describeCall(input, init, url));
  };
}

async function traceCall(call: ApiCall): Promise<Response> {
  if (opensUnnamedPage(call)) startViewFromAddress();
  const view = state.view;
  const parent = parentOf(call, view);
  const span = call.poll ? null : startCallSpan(call, parent);
  const callContext = withBaggage(span ? trace.setSpan(parent, span) : parent);
  return sendTraced(call, view, callContext, span);
}

async function sendTraced(call: ApiCall, view: View | null, callContext: Context, span: Span | null): Promise<Response> {
  const headers = headersCarrying(callContext, call);
  const endCall = countTowardPage(call, view);
  try {
    const response = await context.with(callContext, () => sendUntraced(call.input, { ...call.init, headers }));
    const bytes = Number(response.headers.get("content-length") || 0);
    endCallSpan(span, response, bytes);
    endCall(response.ok, bytes);
    return response;
  } catch (error) {
    endFailedCallSpan(span, error);
    endCall(errorName(error) === "AbortError", 0);
    throw error;
  }
}

function hrefOf(input: RequestInfo | URL): string {
  return typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
}

function isTraced(url: URL): boolean {
  const isStudioApi = url.origin === location.origin && url.pathname.startsWith("/api/");
  const isTelemetryConfig = url.pathname === "/api/telemetry";
  return isStudioApi && !isTelemetryConfig;
}

function describeCall(input: RequestInfo | URL, init: RequestInit | undefined, url: URL): ApiCall {
  const method = (init?.method ?? (input instanceof Request ? input.method : "GET")).toUpperCase();
  const template = urlTemplate(url.pathname);
  return { input, init, url, method, template, action: actionOf(method, template), poll: POLL.test(url.pathname) };
}

function opensUnnamedPage(call: ApiCall): boolean {
  return !call.action && !call.poll && (!state.view || state.view.route !== routeNow());
}

// a read made while a page loads belongs to that page view; a change (POST, DELETE) is a trace of its own
function parentOf(call: ApiCall, view: View | null): Context {
  return !call.action && view ? trace.setSpan(ROOT_CONTEXT, view.span) : ROOT_CONTEXT;
}

function startCallSpan(call: ApiCall, parent: Context): Span {
  const { url, method, template, action } = call;
  return tracer().startSpan(action ? `${action}` : `${method} ${template}`, {
    kind: SpanKind.CLIENT,
    attributes: {
      "http.request.method": method, "url.full": url.href, "url.path": url.pathname, "url.template": template,
      "server.address": url.hostname, ...(action ? { "ce.action": action } : {}),
    },
  }, parent);
}

// who and where travel as baggage, so the server's span carries them too
function withBaggage(callContext: Context): Context {
  return propagation.setBaggage(callContext, propagation.createBaggage(baggageEntries()));
}

function headersCarrying(callContext: Context, call: ApiCall): Headers {
  const { input, init } = call;
  const headers = new Headers(init?.headers ?? (input instanceof Request ? input.headers : undefined));
  propagation.inject(callContext, headers, { set: (h, k, val) => h.set(k, val) });
  return headers;
}

// the page's own reads are what "ready" waits for; polls are only counted
function countTowardPage(call: ApiCall, view: View | null): CallEnd {
  if (view && call.poll) view.polls++;
  if (!view || call.poll || call.action) return () => {};
  view.inflight++;
  view.calls++;
  window.clearTimeout(view.quietTimer); // a call started, so the page isn't quiet: no "ready" until it ends
  const callStartedAt = performance.now();
  return (ok, bytes) => countCallEnd(view, performance.now() - callStartedAt, ok, bytes);
}

function endCallSpan(span: Span | null, response: Response, bytes: number): void {
  if (!span) return;
  span.setAttributes({ "http.response.status_code": response.status, ...(bytes ? { "http.response.body.size": bytes } : {}) });
  if (response.status >= 400) {
    span.setAttribute("error.type", String(response.status));
    span.setStatus({ code: SpanStatusCode.ERROR }); // a client span's 4xx is an error (semconv)
  }
  span.end();
}

function endFailedCallSpan(span: Span | null, error: unknown): void {
  if (!span) return;
  const name = errorName(error);
  if (name === "AbortError") span.setAttribute("ce.request.aborted", true);
  else {
    span.setAttribute("error.type", name);
    span.recordException(error as Error);
    span.setStatus({ code: SpanStatusCode.ERROR, message: String(error) });
  }
  span.end();
}

function errorName(error: unknown): string {
  return error instanceof Error ? error.name : "Error";
}
