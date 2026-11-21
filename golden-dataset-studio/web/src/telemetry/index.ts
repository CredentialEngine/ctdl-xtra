// Telemetry, off unless the server turns it on: GET /api/telemetry says where to send spans ({"browser": null} by
// default). Off, nothing else loads: the OpenTelemetry code is a separate chunk (otel.ts), imported only when on.
import type { PageInfo } from "./names";
import type { BrowserConfig, Impl } from "./otel";

export { pageInfo, type PageInfo } from "./names";

let impl: Impl | null = null;
let pending: PageInfo | null = null;
let started = false;

/** Ask the server once; if it has an endpoint, load the OpenTelemetry chunk and replay the current page view. */
export async function startTelemetry(): Promise<void> {
  if (started) return;
  started = true;
  try {
    const r = await fetch("/api/telemetry");
    const cfg = r.ok ? ((await r.json()) as { browser?: BrowserConfig | null }).browser : null;
    if (!cfg) return;
    const m = await import("./otel");
    impl = await m.init(cfg);
    if (pending) impl.pageView(pending);
  } catch {
    // no telemetry is not an error the reader should see
  }
}

/** The reader opened a page (a route); a no-op while telemetry is off. */
export function pageView(p: PageInfo): void {
  if (impl) impl.pageView(p);
  else pending = p;
}
