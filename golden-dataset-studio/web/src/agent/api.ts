// Agent runs (docs/qrspi/k2-runs/03-spec.md; server: routes_agent.py): Claude improves rules on the remote agent,
// started from a run button and watched from the run bar. The run lives on the storage root, so every Studio and
// every browser sees the same one.
import type { EventBrief, ReviewMarks, RowStateName } from "../api/types";
import { signedOut } from "../shell/session";

export type RunState = "sending" | "waiting" | "running" | "finished" | "needs_you" | "failed" | "cancelled" | "timed_out" | "ended";
export const LIVE: RunState[] = ["sending", "waiting", "running"];
export type ScopeKind = "needs_work" | "rule" | "first_rules" | "rules";
/** `rules`: the rules to improve (one-rule-runs §3.1); `added`: rules Claude changed too, with why */
export interface RunScope { kind: ScopeKind; rule_id?: string | null; rules?: string[]; added?: { rule: string; because?: string }[] }

export interface AgentRun {
  run_id: string; catalog: string; scope: RunScope; started_by: string;
  created_at: string; updated_at: string; deadline: string; state: RunState;
  sent_at: string | null; next_try_at: string | null;
  k2: { url: string; agent: string; delivery_id: string | null };
  ruleset_before: number | null; ruleset_after: number | null;
  /** What the run's first publish was built on (after a rebase, later than ruleset_before); absent on older runs. */
  ruleset_base?: number | null;
  outcome: string | null; ended_at: string | null; ended_by: string | null; fallback_reason: string | null;
  /** The Studio address the run was started from (the report links back to it), and how many to-dos the report has. */
  studio_url?: string | null; to_do_count?: number | null;
  // one-rule-runs (05-api-contract.md §1)
  catalog_short?: string; rule_names?: Record<string, string>; annotations_as_of?: string | null;
  rulesets_published?: number[]; also_changed?: string[]; report_version?: number | null;
}
export interface RunNote { at: string; kind: "note" | "done" | "studio"; text: string; by: string }
/** A live run in `current` (contract §2.3): its notes, and where it stands in the queue. */
export interface LiveRun extends AgentRun {
  notes: RunNote[];
  queue: { place: number | null; start_in_min: number | null; left_min: number | null; minutes_so_far: number | null };
}
/** A rule's latest ended run (the sidebar's AI status). */
export interface RecentRun { run_id: string; state: RunState; outcome: string | null; started_by: string; created_at: string;
  ended_at: string | null; to_do_count: number | null }
export interface Slots { cap: number; live: { run: string; catalog: string; session: string | null; since: string }[];
  waiting: { run: string; catalog: string; since: string; place: number }[] }
export interface CurrentRun {
  /** the old shape: the first live run, else the latest that ended, and its notes */
  run: AgentRun | null; last: AgentRun | null; notes: RunNote[]; since: number; now: string;
  /** contract §2.3: every live run of the catalog, oldest first; per rule its latest ended run; the queue */
  runs?: LiveRun[]; recent?: Record<string, RecentRun>; slots?: Slots;
}
export interface AgentConfig {
  enabled: boolean; off_reason: string | null; agent_name: string; k2_url: string | null; agent: string | null;
  minutes: number; prompt_users: string[];
  /** how many runs work at once, across catalogs */ cap?: number;
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

/** The two rulesets to compare for a run that published: from what it built on to what it published, so another
 *  run's version in between (a rebase) isn't shown as this run's change. */
export function compareOf(r: AgentRun): { a: number; b: number } | null {
  if (r.ruleset_after == null || r.ruleset_before == null || r.ruleset_after <= r.ruleset_before) return null;
  const a = r.ruleset_base != null && r.ruleset_base < r.ruleset_after ? r.ruleset_base : r.ruleset_before;
  return { a, b: r.ruleset_after };
}

const published = (r: AgentRun) => r.ruleset_after != null && r.ruleset_before != null && r.ruleset_after > r.ruleset_before;

/** How an ended run ended, in a few words: all the run bar says (the report has the details). */
export function endedWords(r: AgentRun): string {
  // a run on named rules says which (one-rule-runs §1.3): "Claude published Credit Value in ruleset v10"
  const names = r.scope.kind === "rules" && r.rule_names ? andNames(ruleNames(r)) : "";
  switch (r.state) {
    case "finished":
      if (!published(r)) return names ? `Claude finished ${names} without publishing` : "Claude finished";
      return names ? `Claude published ${names} in ruleset v${r.ruleset_after}` : `Claude published ruleset v${r.ruleset_after}`;
    case "needs_you": {
      const n = r.to_do_count;
      if (names) return n ? `Claude needs ${n} decision${n === 1 ? "" : "s"} before it can publish ${names}` : `Claude needs you before it can publish ${names}`;
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

/** Open the Past AI runs panel from anywhere (App listens), optionally on one run, or on one rule's runs. */
export const OPEN_RUNS = "studio-open-runs";
export interface OpenRuns { run: string | null; rule?: string | null; ruleName?: string | null }
export function openRuns(runId?: string, rule?: { id: string; name: string }): void {
  window.dispatchEvent(new CustomEvent<OpenRuns>(OPEN_RUNS, { detail: { run: runId ?? null, rule: rule?.id ?? null, ruleName: rule?.name ?? null } }));
}

// --- one-rule-runs (docs/qrspi/one-rule-runs/03-spec.md, 05-api-contract.md) ---------------------------------------

/** The run's rules to improve, by name ("Credit Value"), from its record. */
export const ruleNames = (r: Pick<AgentRun, "scope" | "rule_names">): string[] =>
  (r.scope.rules ?? (r.scope.rule_id ? [r.scope.rule_id] : [])).map((id) => r.rule_names?.[id] ?? id);

/** A run in the queue (GET /api/agent-runs/queue, contract §2.8). */
export interface QueueRun {
  run: string; catalog: string; catalog_name?: string; rules: string[]; rule_names?: string[]; started_by: string; since: string;
  /** working */ minutes_so_far?: number; left_min?: number;
  /** waiting: 1 = next */ place?: number; start_in_min?: number;
}
export interface Queue { cap: number; working: QueueRun[]; waiting: QueueRun[]; median_min: number; from_runs: number; note?: string | null }

/** One rule in the "Run with Claude?" picker (GET /rules/picker, contract §2.7). */
export interface PickerRule {
  rule: string; name: string; kind?: string; status: string; reviewed: number; total: number;
  open?: number; comments?: number; new_since_run?: number;
  /** ticked by default */ ticked: boolean;
  /** the grey line: "3 open, 4 comments", "nothing open", or why it is held */ why: string;
  held_by?: { run_id: string; started_by: string; state?: string; since: string; minutes?: number } | null;
}
export interface Picker { rules: PickerRule[]; total_rules?: number; ticked?: number; note?: string | null }

/** An event brief in a report row's history (contract §2.6, §3.3). */
export interface HistEvent extends EventBrief {
  kind?: "verdict" | "comment"; run_at?: string | null; after_run?: boolean;
}

/** "Values changed: 1,062 of 1,062 courses. Compare v9 and v10" (contract §3.6), counted by the CLI. */
export interface ValuesChanged { count: number; of: number; base: number | null; published: number | null;
  compare_url?: string | null; text?: string | null }

/** A row card (contract §3.2): the Rules tab's row as it was when the run ended. */
export interface ReportRow {
  rule: string; rule_name?: string; legend?: string | null; kind?: string; course: string; title: string | null;
  page_stem: string; url: string; key?: string; occurrence_key: string | null;
  value: string | null; status: "found" | "empty" | "no_match" | "none" | "absent";
  value_before?: { version: number; value: string | null } | null;
  inferred?: { value: string; annotation: string; saves: "correct" | "expected" } | null;
  left_out?: { text: string; before?: string | null; after?: string | null }[];
  comment?: string | null;
  verdict?: EventBrief | null; state?: RowStateName | null; history?: HistEvent[];
  links?: { rules?: string; wrong?: string } | null;
}
export interface QuoteSource {
  kind: "note" | "page" | "value"; annotation_id?: string; author?: string; at?: string; rule?: string | null;
  course?: string | null; title?: string | null; before?: string | null; after?: string | null;
}
export type ToDoEvidence =
  | { kind: "quote"; quote: string; source?: QuoteSource | null }
  | { kind: "set"; label: string; rule: string; count: number; rows: ReportRow[];
      courses: { course: string; title: string | null; value: string | null; verdict: string | null }[]; link?: string | null };
export interface ReportToDo {
  ask: string; open?: boolean; rule?: string; rule_name?: string; about: ReportRow[]; evidence: ToDoEvidence[];
  options: { answer: string; text: string; link?: string | null }[];
}
export interface ReportInferred {
  rule: string; rule_name?: string; course: string; value: string; published: boolean;
  evidence?: { quote: string; source?: QuoteSource | null }[]; row: ReportRow;
}
export interface ReportRule {
  rule: string; name: string; goal?: boolean; outcome?: string | null; now?: string | null; why?: string | null;
  because?: { reads?: string; read_by?: string; name?: string } | null;
  values_changed?: ValuesChanged | null; rows: ReportRow[];
}
/** `report.resolved.json` (contract §3): the report with every reference replaced by its data. */
export interface ResolvedReport {
  version: number; run_id?: string;
  ending: "published" | "needs_you" | "failed"; outcome?: string | null; reason?: string | null;
  ruleset?: { started_on: number | null; based_on: number | null; published: number[]; latest?: number | null; ext?: string | null;
              compare?: { a: number; b: number; url?: string } | null } | null;
  facts?: { label: string; text: string }[];
  inferred: ReportInferred[]; to_do: ReportToDo[]; rules: ReportRule[]; also_changed: ReportRule[];
  notes?: string | null;
  revert?: { version: number; text: string } | null;
}
export const rowKey = (rule: string, course: string) => `${rule}|${course}`;

/** GET …/agent-runs/{id}/rows (contract §2.6): each report row as it is now, and the new feedback since the run. */
export interface ReportRowState extends ReviewMarks {
  rule: string; course: string; page_stem?: string; key?: string; occurrence_key?: string | null;
  value?: string | null; status?: ReportRow["status"];
  state: RowStateName | null; verdict: EventBrief | null; history: HistEvent[]; reattached?: boolean;
}
export interface ReportRows { run_id?: string; annotations_as_of: string | null; rules_touched?: string[]; new_feedback: number; rows: ReportRowState[] }

export interface RunDetail { run: AgentRun; notes: RunNote[]; summary: string | null; report?: ResolvedReport | null }

/** A start (contract §2.2): queued (always `waiting`), refused because a rule is held by a live run, or as before. */
export type StartResult2 =
  | { ok: true; run: AgentRun; queue: { place: number; start_in_min: number } | null }
  | { ok: false; kind: "held"; rule: string; rule_name: string; run: AgentRun | null; detail: string }
  | Exclude<StartResult, { ok: true }>;

export const agentApi2 = {
  queue: () => get<Queue>("/api/agent-runs/queue"),
  picker: (catalog: string) => get<Picker>(`/api/catalogs/${encodeURIComponent(catalog)}/rules/picker`),
  detail: (catalog: string, runId: string) => get<RunDetail>(`${c(catalog)}/${encodeURIComponent(runId)}`),
  rows: (catalog: string, runId: string) => get<ReportRows>(`${c(catalog)}/${encodeURIComponent(runId)}/rows`),
  ofRule: (catalog: string, rule: string, limit = 20) => get<AgentRun[]>(`${c(catalog)}?rule=${encodeURIComponent(rule)}&limit=${limit}`),
  revert: (catalog: string, version: number, author: string) =>
    get<{ version: number; reverted: number; rules?: { rule: string; name: string }[]; suite?: { line?: string } }>(
      `/api/catalogs/${encodeURIComponent(catalog)}/rulesets/${version}/revert`, json({ author })),
  async start(catalog: string, rules: string[], author: string): Promise<StartResult2> {
    let r: Response;
    try {
      r = await fetch(c(catalog), json({ scope: { kind: "rules", rules }, author, studio_url: location.origin + location.pathname }));
    } catch {
      return { ok: false, kind: "fallback", reason: "the Studio's server didn't answer" };
    }
    if (r.status === 401) signedOut();
    let body: Record<string, unknown> = {};
    try { body = await r.json(); } catch { /* not JSON */ }
    if (r.ok) return { ok: true, run: body.run as AgentRun, queue: (body.queue as { place: number; start_in_min: number }) ?? null };
    if (body.fallback === "prompt") return { ok: false, kind: "fallback", reason: String(body.reason ?? body.detail ?? "") };
    if (r.status === 409 && body.rule) {
      return { ok: false, kind: "held", rule: String(body.rule), rule_name: String(body.rule_name ?? body.rule),
               run: (body.run as AgentRun) ?? null, detail: String(body.detail ?? "") };
    }
    if (r.status === 409) return { ok: false, kind: "busy", run: (body.run as AgentRun) ?? null, detail: String(body.detail ?? "") };
    if (r.status >= 500) return { ok: false, kind: "fallback", reason: `the Studio's server answered ${r.status}` };
    return { ok: false, kind: "error", detail: String(body.detail ?? r.statusText) };
  },
};

/** "1st", "2nd", "3rd", "11th". */
export function ordinal(n: number): string {
  const t = n % 100;
  if (t >= 11 && t <= 13) return `${n}th`;
  return `${n}${["th", "st", "nd", "rd"][n % 10] ?? "th"}`;
}

/** The run bar's sentence for a run waiting in line (spec §1.7): "Your run on Description is 2nd in line. It should
 * start in about 6 min." */
export function waitingWords(run: LiveRun, me: string): string {
  const whose = run.started_by === me ? "Your run" : `${run.started_by}'s run`;
  const on = andNames(ruleNames(run));
  const place = run.queue?.place;
  const mins = run.queue?.start_in_min;
  if (!place) return `${whose} on ${on} is waiting for a free place.`;
  const start = mins == null ? "" : mins <= 0 ? " It should start in a moment." : ` It should start in about ${mins} min.`;
  return `${whose} on ${on} is ${ordinal(place)} in line.${start}`;
}

/** "Credit Value", "Subject Webpage and In Catalog", "A, B and C". */
export const andNames = (xs: string[]) => (xs.length < 2 ? xs.join("") : `${xs.slice(0, -1).join(", ")} and ${xs[xs.length - 1]}`);
