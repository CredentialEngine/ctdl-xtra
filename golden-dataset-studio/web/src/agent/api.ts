// Agent runs (docs/qrspi/k2-runs/03-spec.md; server: routes_agent.py): Claude improves rules on the remote agent,
// started from a run button and watched from the run bar. The run lives on the storage root, so every Studio and
// every browser sees the same one.
import { signedOut } from "../shell/session";

export type RunState = "sending" | "waiting" | "running" | "finished" | "needs_you" | "failed" | "cancelled" | "timed_out" | "ended";
export const LIVE: RunState[] = ["sending", "waiting", "running"];
export type ScopeKind = "needs_work" | "rule" | "first_rules";
export interface RunScope { kind: ScopeKind; rule_id?: string | null; rules?: string[] }

export interface AgentRun {
  run_id: string; catalog: string; scope: RunScope; started_by: string;
  created_at: string; updated_at: string; deadline: string; state: RunState;
  sent_at: string | null; next_try_at: string | null;
  k2: { url: string; agent: string; delivery_id: string | null };
  ruleset_before: number | null; ruleset_after: number | null;
  outcome: string | null; ended_at: string | null; ended_by: string | null; fallback_reason: string | null;
  /** The Studio address the run was started from (the report links back to it), and how many to-dos the report has. */
  studio_url?: string | null; to_do_count?: number | null;
}
export interface RunNote { at: string; kind: "note" | "done" | "studio"; text: string; by: string }
export interface CurrentRun { run: AgentRun | null; last: AgentRun | null; notes: RunNote[]; since: number; now: string }
export interface AgentConfig {
  enabled: boolean; off_reason: string | null; agent_name: string; k2_url: string | null; agent: string | null;
  minutes: number; prompt_users: string[];
}

/** A start either runs, is blocked by a live run, or falls back to the prompt (`reason` says why). */
export type StartResult =
  | { ok: true; run: AgentRun }
  | { ok: false; kind: "busy"; run: AgentRun | null; detail: string }
  | { ok: false; kind: "fallback"; reason: string }
  | { ok: false; kind: "error"; detail: string };

const c = (catalog: string) => `/api/catalogs/${encodeURIComponent(catalog)}/agent-runs`;
const json = (body: unknown): RequestInit =>
  ({ method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });

async function get<T>(path: string, init?: RequestInit): Promise<T> {
  const r = await fetch(path, init);
  if (r.status === 401) signedOut();
  if (!r.ok) {
    let detail = r.statusText;
    try { detail = (await r.json()).detail ?? detail; } catch { /* not JSON */ }
    throw new Error(String(detail));
  }
  return r.json() as Promise<T>;
}

export const agentApi = {
  config: () => get<AgentConfig>("/api/agent-runs/config"),
  current: (catalog: string, since = 0) => get<CurrentRun>(`${c(catalog)}/current?since=${since}`),
  cancel: (catalog: string, runId: string, author: string) =>
    get<{ run: AgentRun }>(`${c(catalog)}/${encodeURIComponent(runId)}/cancel`, json({ author })),
  end: (catalog: string, runId: string, author: string, outcome?: string) =>
    get<{ run: AgentRun }>(`${c(catalog)}/${encodeURIComponent(runId)}/end`, json({ author, outcome })),
  history: (catalog: string, limit = 50) => get<AgentRun[]>(`${c(catalog)}?limit=${limit}`),
  detail: (catalog: string, runId: string) =>
    get<{ run: AgentRun; notes: RunNote[]; summary: string | null }>(`${c(catalog)}/${encodeURIComponent(runId)}`),
  prompt: (catalog: string, runId: string) => get<{ text: string }>(`${c(catalog)}/${encodeURIComponent(runId)}/prompt`),
  async start(catalog: string, scope: RunScope, author: string): Promise<StartResult> {
    let r: Response;
    try {
      r = await fetch(c(catalog), json({ scope, author, studio_url: location.origin + location.pathname }));
    } catch {
      return { ok: false, kind: "fallback", reason: "the Studio's server didn't answer" };
    }
    if (r.status === 401) signedOut();
    let body: Record<string, unknown> = {};
    try { body = await r.json(); } catch { /* not JSON */ }
    if (r.ok) return { ok: true, run: body.run as AgentRun };
    if (body.fallback === "prompt") return { ok: false, kind: "fallback", reason: String(body.reason ?? body.detail ?? "") };
    if (r.status === 409) return { ok: false, kind: "busy", run: (body.run as AgentRun) ?? null, detail: String(body.detail ?? "") };
    if (r.status >= 500) return { ok: false, kind: "fallback", reason: `the Studio's server answered ${r.status}` };
    return { ok: false, kind: "error", detail: String(body.detail ?? r.statusText) };
  },
};

/** "12 min", "1 h 5 min", "40 s" between two ISO times. */
export function elapsed(from: string, to: string): string {
  const s = Math.max(0, Math.round((Date.parse(to) - Date.parse(from)) / 1000));
  if (s < 60) return `${s} s`;
  const m = Math.round(s / 60);
  return m < 60 ? `${m} min` : `${Math.floor(m / 60)} h ${m % 60} min`;
}

/** What a run is doing, in a few words: "improving 5 rules", "improving Course description", "writing the first rules". */
export function scopeWords(scope: RunScope): string {
  if (scope.kind === "first_rules") return "writing the first rules";
  if (scope.kind === "rule") return `improving ${scope.rule_id}`;
  const n = scope.rules?.length;
  return n ? `improving ${n} rule${n === 1 ? "" : "s"}` : "improving the rules that need work";
}

const published = (r: AgentRun) => r.ruleset_after != null && r.ruleset_before != null && r.ruleset_after > r.ruleset_before;

/** How an ended run ended, in a few words: all the run bar says (the report has the details). */
export function endedWords(r: AgentRun): string {
  switch (r.state) {
    case "finished": return published(r) ? `Claude published ruleset v${r.ruleset_after}` : "Claude finished";
    case "needs_you": {
      const n = r.to_do_count;
      return n ? `${n} thing${n === 1 ? "" : "s"} to fix before Claude can publish` : "Things to fix before Claude can publish";
    }
    case "failed": return "Claude couldn't finish";
    case "cancelled": return "Run cancelled";
    case "timed_out": return "Run timed out";
    case "ended": return "Run marked as ended";
    default: return r.state;
  }
}

/** The ended run's words with its outcome line, for the report and the run list (where details belong). */
export function endedLine(r: AgentRun): string {
  const w = endedWords(r);
  // an older run's free-text outcome often repeats the words ("Published ruleset v7: …"): keep only what it adds
  const o = (r.outcome ?? "").replace(/^Published ruleset v\d+:?\s*/i, "").trim();
  if (!o || o === w) return w;
  return o.startsWith(w) ? o : `${w}: ${o}`;
}

export const endedIcon = (r: AgentRun) => (r.state === "finished" ? "approved" : r.state === "needs_you" ? "question" : "needs work");

/** Open the Past AI runs panel from anywhere (App listens), optionally on one run. */
export const OPEN_RUNS = "studio-open-runs";
export function openRuns(runId?: string): void {
  window.dispatchEvent(new CustomEvent(OPEN_RUNS, { detail: runId ?? null }));
}
