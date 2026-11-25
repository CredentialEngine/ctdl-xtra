// The web app's OpenTelemetry, loaded only when the server says where to send spans (index.ts). Few, wide spans:
//
// - `page_view`: one per route the reader opens (a trace of its own). It starts at the route change (at navigation start
//   for the first one after a hard load) and ends when the page's API calls have finished (`ce.page.ready.duration_ms`),
//   with counts of what loading took (`ce.stats.api.*`) and how big the page got (`ce.page.dom_nodes`). pageViews.ts
// - one client span per API call, a child of the page view while it is loading (else its own trace). Its `traceparent`
//   makes the server's span its child: one connected trace from the click to the storage read. Changes (POST, DELETE)
//   always start their own trace, named by `ce.action`. Timed polls get no span, only a count on the page view.
//   apiCalls.ts
// - Honeycomb's Web SDK adds the web vitals (FCP, LCP, INP, CLS, TTFB spans), uncaught errors (`exception` spans),
//   browser and session attributes (`session.id` from a session kept in localStorage: 30 min idle, 12 h at most).
//
// Every span gets who and where: `user.id` and `user.roles` (the profile picked on "Who are you?"), `ce.page`,
// `ce.catalog`, `ce.rule.id`, `ce.page_view.id`, `ce.entry_page` (the page the browser loaded first). The same who and
// where go to the server as W3C baggage (who.ts). Where the spans go and which build sent them come from
// GET /api/telemetry.
import { HoneycombWebSDK } from "@honeycombio/opentelemetry-web";
import type { Span } from "@opentelemetry/api";
import {
  createDefaultSessionIdGenerator, createLocalStorageSessionStore, createSessionManager, type SessionProvider,
} from "@opentelemetry/web-common";
import { traceApiCalls } from "./apiCalls";
import type { PageInfo } from "./names";
import { endViewWhenLeaving, pageView } from "./pageViews";
import { SERVICE, state } from "./state";
import { whoAndWhere } from "./who";

export interface BrowserConfig { endpoint: string; sample_rate: number; resource: Record<string, string> }
export interface Impl { pageView(p: PageInfo): void }

export async function init(config: BrowserConfig): Promise<Impl> {
  state.sessions = await startSessions();
  new HoneycombWebSDK(sdkOptions(config, state.sessions)).start();
  endViewWhenLeaving();
  traceApiCalls();
  return { pageView };
}

async function startSessions(): Promise<SessionProvider> {
  const sessions = createSessionManager({
    sessionIdGenerator: createDefaultSessionIdGenerator(), sessionStore: createLocalStorageSessionStore(),
    inactivityTimeout: 30 * 60, maxDuration: 12 * 3600,
  });
  await sessions.start(); // before any span: until then it hands out a temporary id, not the stored session
  return sessions;
}

function sdkOptions(config: BrowserConfig, sessions: SessionProvider) {
  return {
    serviceName: SERVICE,
    tracesEndpoint: new URL(config.endpoint, location.href).href,
    disableDefaultMetricExporter: true, // traces only: the numbers go on spans
    disableDefaultLogExporter: true,
    skipOptionsValidation: true, // no Honeycomb API key: the endpoint is the Studio's own collector
    sampleRate: config.sample_rate,
    resourceAttributes: config.resource,
    sessionProvider: sessions,
    instrumentations: [], // the SDK adds web vitals and global errors itself; fetch spans are made in apiCalls.ts
    webVitalsInstrumentationConfig: integerVitals(),
    spanProcessors: [whoAndWhereProcessor()],
  };
}

// TTFB and CLS are floats, and TraceQL's quantile_over_time skips float attributes: integer copies for p75s
function integerVitals() {
  return {
    ttfb: { applyCustomAttributes: addTimeToFirstByteUs },
    cls: { applyCustomAttributes: addLayoutShiftMilli },
  };
}

function whoAndWhereProcessor() {
  return {
    onStart: (span: Span) => span.setAttributes(whoAndWhere()),
    onEnd: () => {}, forceFlush: () => Promise.resolve(), shutdown: () => Promise.resolve(),
  };
}

function addTimeToFirstByteUs(ttfb: { value: number }, span: Span): void {
  const timeToFirstByteUs = Math.round(ttfb.value * 1000); // ms -> whole microseconds
  span.setAttribute("ce.ttfb.value_us", timeToFirstByteUs);
}

function addLayoutShiftMilli(cls: { value: number }, span: Span): void {
  const layoutShiftThousandths = Math.round(cls.value * 1000); // a score like 0.042 -> 42
  span.setAttribute("ce.cls.value_milli", layoutShiftThousandths);
}
