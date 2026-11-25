// The spans otel.ts makes, recorded end to end: page views, API calls, changes, polls, failures and leaving the page.
import { propagation, trace, type Span } from "@opentelemetry/api";
import { CompositePropagator, W3CBaggagePropagator, W3CTraceContextPropagator } from "@opentelemetry/core";
import {
  BasicTracerProvider, InMemorySpanExporter, SimpleSpanProcessor, type ReadableSpan, type SpanProcessor,
} from "@opentelemetry/sdk-trace-base";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { pageInfo } from "./names";

const sdk = vi.hoisted(() => ({ config: null as null | { spanProcessors: unknown[] } }));
vi.mock("@honeycombio/opentelemetry-web", () => ({
  HoneycombWebSDK: class { constructor(config: { spanProcessors: unknown[] }) { sdk.config = config; } start() {} },
}));
vi.mock("@opentelemetry/web-common", () => ({
  createDefaultSessionIdGenerator: () => ({}),
  createLocalStorageSessionStore: () => ({}),
  createSessionManager: () => ({ start: async () => {}, getSessionId: () => "session-1" }),
}));
vi.mock("../shell/reviewer", () => ({ currentReviewer: () => "Ada", currentRole: () => "sme" }));

const exporter = new InMemorySpanExporter();
const whoProcessor: SpanProcessor = {
  onStart: (span, parent) => (sdk.config!.spanProcessors[0] as SpanProcessor).onStart(span, parent),
  onEnd: () => {}, forceFlush: () => Promise.resolve(), shutdown: () => Promise.resolve(),
};
trace.setGlobalTracerProvider(new BasicTracerProvider({
  spanProcessors: [whoProcessor, new SimpleSpanProcessor(exporter)],
}));
const sent: { url: string; headers: Record<string, string> }[] = [];
let respond: (url: string) => Promise<Response>;
const realFetch = window.fetch;

async function startOtel() {
  window.fetch = (async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    sent.push({ url, headers: Object.fromEntries(new Headers(init?.headers).entries()) });
    return respond(url);
  }) as typeof fetch;
  const { init } = await import("./otel");
  return init({ endpoint: "/otlp/v1/traces", sample_rate: 1, resource: {} });
}

function describeSpans() {
  const ids = new Map<string, string>();
  const name = (id: string | undefined) => {
    if (!id) return undefined;
    if (!ids.has(id)) ids.set(id, `span-${ids.size + 1}`);
    return ids.get(id);
  };
  const spans = exporter.getFinishedSpans();
  spans.forEach((s) => name(s.spanContext().spanId));
  return spans.map((s: ReadableSpan) => ({
    name: s.name, kind: s.kind, id: name(s.spanContext().spanId), parent: name(s.parentSpanContext?.spanId),
    status: s.status, events: s.events.map((e) => e.name),
    attributes: Object.fromEntries(Object.entries(s.attributes).map(([k, v]) => [k, k === "ce.page_view.id" ? name(String(v)) : v])),
  }));
}

function describeHeaders() {
  return sent.map(({ url, headers }) => ({
    url, traceparent: !!headers.traceparent, baggage: headers.baggage?.replace(/ce\.page_view\.id=[0-9a-f]+/, "ce.page_view.id=…"),
  }));
}

function ok(body = "{}") { return Promise.resolve(new Response(body, { headers: { "content-length": String(body.length) } })); }

beforeEach(() => {
  vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout", "performance", "Date"] });
  propagation.setGlobalPropagator(new CompositePropagator({
    propagators: [new W3CTraceContextPropagator(), new W3CBaggagePropagator()],
  }));
  location.hash = "#/c/avc/course/rules/course-title";
  respond = () => ok();
});

afterEach(() => {
  vi.useRealTimers();
  vi.resetModules();
  propagation.disable();
  exporter.reset();
  sent.length = 0;
  window.fetch = realFetch;
});

describe("otel", () => {
  it("names the hard load's view after its first request, then ends it when the page is ready", async () => {
    const otel = await startOtel();
    await fetch("/api/catalogs/avc/rules/course-title/rows");
    otel.pageView(pageInfo(true, "avc", "rules", "course-title", "course"));
    await fetch("/api/catalogs/avc/agent-runs/current");
    respond = () => ok("not found!");
    await fetch("/api/catalogs/avc/rules/x", { method: "GET" }).then(() => undefined);
    await vi.advanceTimersByTimeAsync(600);
    expect(describeSpans()).toMatchSnapshot();
    expect(describeHeaders()).toMatchSnapshot();
  });

  it("starts a soft view on navigation, keeps changes in their own trace and records failures", async () => {
    const otel = await startOtel();
    otel.pageView(pageInfo(true, "avc", "rules", null, "course"));
    location.hash = "#/c/avc/course/records/2166?row=3";
    otel.pageView(pageInfo(true, "avc", "records", "2166", "course"));
    respond = () => Promise.resolve(new Response("", { status: 500 }));
    await fetch("/api/catalogs/avc/courses/2166");
    respond = () => ok();
    await fetch("/api/catalogs/avc/annotations", { method: "POST", body: "{}" });
    respond = () => Promise.reject(Object.assign(new Error("stop"), { name: "AbortError" }));
    await expect(fetch("/api/catalogs/avc/golden/v1")).rejects.toThrow();
    respond = () => Promise.reject(new TypeError("offline"));
    await expect(fetch("/api/catalogs/avc/scores/s1/values")).rejects.toThrow();
    respond = () => ok();
    await fetch("https://example.org/api/elsewhere");
    await fetch("/api/telemetry");
    await vi.advanceTimersByTimeAsync(600);
    expect(describeSpans()).toMatchSnapshot();
    expect(describeHeaders()).toMatchSnapshot();
  });

  it("ends a view when the reader leaves, and one that never settles after 30 s", async () => {
    const otel = await startOtel();
    otel.pageView(pageInfo(true, null, "rules", null));
    window.dispatchEvent(new Event("pagehide"));
    location.hash = "#/c/avc/course/evals";
    otel.pageView(pageInfo(true, "avc", "evals", null, "course"));
    respond = () => new Promise<Response>(() => {});
    void fetch("/api/catalogs/avc/golden");
    await vi.advanceTimersByTimeAsync(31_000);
    expect(describeSpans()).toMatchSnapshot();
  });

  it("adds integer copies of the TTFB and CLS vitals", async () => {
    await startOtel();
    const vitals = (sdk.config as unknown as { webVitalsInstrumentationConfig: Record<string, {
      applyCustomAttributes: (metric: { value: number }, span: Span) => void }> }).webVitalsInstrumentationConfig;
    const attributes: Record<string, unknown> = {};
    const span = { setAttribute: (k: string, v: unknown) => { attributes[k] = v; } } as unknown as Span;
    vitals.ttfb.applyCustomAttributes({ value: 12.3456 }, span);
    vitals.cls.applyCustomAttributes({ value: 0.042 }, span);
    expect(attributes).toEqual({ "ce.ttfb.value_us": 12346, "ce.cls.value_milli": 42 });
  });
});
