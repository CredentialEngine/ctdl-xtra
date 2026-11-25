// The home page's xtra score views (LearningProgram spec §2), as plain functions of the score history
// (`GET /api/score-history`): the latest counts of a set of (catalog, property) pairs, their history as points, and
// what each of the four scopes lists. A row's counts are the sum of its pairs' latest scores, so exact is
// match ÷ values over everything it covers.
import type { ScoreHistory, ScoreLine, ScoreNumbers } from "../api/types";

export type Tree = "golden" | "silver";
export const TREES: Tree[] = ["golden", "silver"];
/** The outcomes a score view shows, in bar order: exact first, missing last (extra is the Evals tab's). */
export const SHOWN = ["match", "partial", "unsure", "wrong", "missing"] as const;
export type Shown = (typeof SHOWN)[number];
export type Counts = Record<Shown, number> & { values: number };
export const ZERO: Counts = { values: 0, match: 0, partial: 0, unsure: 0, wrong: 0, missing: 0 };

export type Pair = [catalog: string, column: string];

export function add(a: Counts, b: ScoreNumbers | Counts | null | undefined): Counts {
  if (!b) return a;
  const out = { ...a, values: a.values + (b.values ?? 0) };
  for (const k of SHOWN) out[k] = a[k] + (b[k] ?? 0);
  return out;
}

/** exact and partial as shares of the values (null with none) */
export const exactOf = (c: Counts | null) => (c && c.values ? c.match / c.values : null);
export const partialOf = (c: Counts | null) => (c && c.values ? c.partial / c.values : null);
export const pct = (x: number | null) => (x === null ? "—" : `${(100 * x).toFixed(1)}%`);

const linesOf = (h: ScoreHistory, [cat, col]: Pair): ScoreLine[] => h.history[cat]?.[col] ?? [];

/** The latest scores of the pairs, summed; null when none of them is scored. */
export function latest(h: ScoreHistory, pairs: Pair[], tree: Tree): Counts | null {
  let got: Counts | null = null;
  for (const p of pairs) {
    const ls = linesOf(h, p), l = ls[ls.length - 1]?.[tree];
    if (l) got = add(got ?? ZERO, l);
  }
  return got;
}

/** One point of a history: the pairs' latest scores as they stood after one score, and what moved: the golden
 * dataset (`golden`) or xtra's extract output (`output`). */
export interface Point { at: string; kind: "golden" | "output"; c: Counts; lines: ScoreLine[] }

/** The pairs' history, oldest first, its last `n` points. A score of several properties at once is one point (over
 * several catalogs, which score apart, a day is one point); each point sums every pair's latest score up to then, so
 * a score of one property doesn't drop the others. */
export function series(h: ScoreHistory, pairs: Pair[], tree: Tree, n = 7): Point[] {
  const cur = new Map<string, ScoreLine>();
  const out: Point[] = [];
  for (const group of groupRuns(scoreEvents(h, pairs))) {
    for (const e of group) cur.set(e.key, e.l);
    const c = sumLatest(cur, tree);
    if (c) out.push({ at: group[0].l.at, kind: kindOf(group), c, lines: group.map((e) => e.l) });
  }
  return out.slice(-n);
}

interface ScoreEvent { key: string; group: string; l: ScoreLine; prev: ScoreLine | null }

function scoreEvents(h: ScoreHistory, pairs: Pair[]): ScoreEvent[] {
  const byDay = new Set(pairs.map(([cat]) => cat)).size > 1;
  const events = pairs.flatMap(([cat, col]) => linesOf(h, [cat, col]).map((l, i, all) =>
    ({ key: `${cat}|${col}`, group: byDay ? l.at.slice(0, 10) : `${cat}|${l.score}`, l, prev: all[i - 1] ?? null })));
  events.sort((a, b) => a.l.at.localeCompare(b.l.at));
  return events;
}

// one group per run of consecutive events of the same score (or day)
function groupRuns(events: ScoreEvent[]): ScoreEvent[][] {
  const groups: ScoreEvent[][] = [];
  for (const e of events) {
    const last = groups[groups.length - 1];
    if (last && last[0].group === e.group) last.push(e); else groups.push([e]);
  }
  return groups;
}

function kindOf(group: ScoreEvent[]): Point["kind"] {
  const t = group[0].l.trigger;
  if (t === "golden-published") return "golden";
  if (t === "new-output") return "output";
  return group.some((e) => e.prev && e.prev.extract_run !== e.l.extract_run) ? "output" : "golden";
}

function sumLatest(cur: Map<string, ScoreLine>, tree: Tree): Counts | null {
  let c: Counts | null = null;
  for (const l of cur.values()) if (l[tree]) c = add(c ?? ZERO, l[tree]);
  return c;
}

/** The four scopes (spec §2): catalogs × properties, by whether one catalog and one property is picked. */
export type Scope = "all" | "catalog" | "property" | "one";
export const scopeOf = (oneCatalog: boolean, oneProperty: boolean): Scope =>
  oneCatalog ? (oneProperty ? "one" : "catalog") : oneProperty ? "property" : "all";

/** What a trigger says under a score (one catalog, one property). */
export const TRIGGER: Record<string, string> = {
  "golden-published": "Golden published", "new-output": "New extract output", manual: "Asked for",
};

/** The xtra-cli that scored it: "0.14.2 (4f2a1c9)". */
export function scoredWith(l: ScoreLine): string | null {
  const v = l.scored_with?.xtra_cli_version, c = l.scored_with?.xtra_cli_commit;
  if (!v && !c) return null;
  return [v, c ? `(${c.slice(0, 7)})` : null].filter(Boolean).join(" ");
}

/** A property's name as the score views show it: its CTDL term ("ceterms:name"), or its label with none. */
export const termOf = (p: ScoreHistory["properties"][number]) => (p.term ? p.term.replace(/>/g, " → ") : p.label);
export const TIER_WORD: Record<string, string> = { required: "required", phase1: "Phase 1", phase2: "Phase 2" };
