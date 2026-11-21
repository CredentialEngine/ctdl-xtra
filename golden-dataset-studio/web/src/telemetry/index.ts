// Telemetry, off unless the server turns it on. The server then puts its config in index.html
// (<script id="otel-config" type="application/json">); without it nothing else loads: the OpenTelemetry code is a
// separate chunk (otel.ts), imported only when on. main.tsx renders once `startTelemetry()` settles, so the app's first
// requests already carry its trace context (with no config it settles at once).
import type { PageInfo } from "./names";
import type { BrowserConfig, Impl } from "./otel";

export { pageInfo, type PageInfo } from "./names";

let impl: Impl | null = null;
let pending: PageInfo | null = null;
let started: Promise<void> | null = null;

/** The server's telemetry config, or null (off). */
export function readConfig(doc: Document = document): BrowserConfig | null {
  const el = doc.getElementById("otel-config");
  if (!el?.textContent) return null;
  try { return JSON.parse(el.textContent) as BrowserConfig; } catch { return null; }
}

/** Start telemetry if the page says so; resolves when it's running, or at once when it's off. Never rejects. */
export function startTelemetry(): Promise<void> {
  if (started) return started;
  const cfg = readConfig();
  started = !cfg ? Promise.resolve() : import("./otel")
    .then((m) => m.init(cfg))
    .then((i) => { impl = i; if (pending) i.pageView(pending); })
    .catch(() => { /* no telemetry is not an error the reader should see */ });
  return started;
}

/** The reader opened a page (a route); a no-op while telemetry is off. */
export function pageView(p: PageInfo): void {
  if (impl) impl.pageView(p);
  else pending = p;
}
