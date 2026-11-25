// What the telemetry remembers between spans: the reader's session, the page they're on and its open page view.
import { trace, type Span, type Tracer } from "@opentelemetry/api";
import type { SessionProvider } from "@opentelemetry/web-common";
import type { PageInfo } from "./names";

export const SERVICE = "golden-dataset-studio-web";

export interface View {
  span: Span; id: string; page: PageInfo; route: string; implicit: boolean; start: number; lastActivity: number; inflight: number;
  calls: number; errors: number; polls: number; bytes: number; apiMs: number; slowest: number;
  quietTimer?: number; // ends the view once no call has run for IDLE_MS
  maxTimer?: number;   // ends it after MAX_VIEW_MS, whatever is still loading
}

export const state = {
  sessions: null as SessionProvider | null,
  page: null as PageInfo | null,
  entryPage: null as string | null,
  view: null as View | null,
  firstViewId: null as string | null,
};

export function tracer(): Tracer {
  return trace.getTracer(SERVICE);
}

// the route without its query: ?row= changes as rows are picked, and that is not a new page
export function routeNow(): string {
  return location.hash.split("?")[0];
}
