// The Evals tab's arithmetic and wording: outcome counts, rates, the golden side's names, and why a column isn't scored.
import type { ColumnSummary, ExtractOutputs, OutcomeCounts, ScoreBasis, ScoreBrief, ScoreDoc, ScoreOutcome } from "../api/types";
import { fmt } from "../shell/ui";

/** Every outcome, worst first (sme-fixes spec §8.1): the golden side's five, then `extra` (a candidate with no golden
 * partner). Scores from before sme-fixes have no unsure or extra (0). */
export const OUTCOMES: ScoreOutcome[] = ["missing", "wrong", "partial", "unsure", "match", "extra"];
/** What `values` counts: the golden units. */
export const GOLDEN_OUTCOMES: ScoreOutcome[] = OUTCOMES.filter((o) => o !== "extra");
/** The order of a bar's segments, left to right (bottom to top): matches first, the striped extras last. */
export const BAR_ORDER: ScoreOutcome[] = ["match", "partial", "unsure", "wrong", "missing", "extra"];
/** Each outcome's rule (xtra's scorer, Evals spec §2, sme-fixes spec §8.1), in the tab's terms: a **candidate** is a
 * value in xtra's extract output; a **golden value** is one the golden side holds. */
export const OUTCOME_RULE: Record<ScoreOutcome, string> = {
  match: "a candidate identical to the golden value", partial: "paired with a candidate, similarity ≥ 0.8",
  wrong: "paired with a candidate, similarity < 0.8", missing: "a golden value with no candidate",
  unsure: "golden says not on the page; xtra made no claim", extra: "a candidate with no golden value",
};
export const SIMILARITY = "Text is compared ignoring case and spacing, and again without punctuation, keeping the higher score. Numbers either match or are wrong. A list of objects (durations) pairs by description; an object is exact only when every field is.";
/** The two terms an unscored column's facts use. */
export const CANDIDATES_TIP = "Candidates: the values in xtra's extract output for this property.";
export const HUMAN = "human-reviewed";

export type Output = ExtractOutputs["outputs"][number];
export type Counts = Partial<Record<ScoreOutcome, number>>;
type AnyCounts = Counts | OutcomeCounts | null | undefined;

/** The two facts that say why a column isn't scored (it is only when it has both candidates and golden values): its
 * candidates in this extract output, and its golden values (rule-matched values on the Rule-matched side). `full` is
 * the sentence, `short` the chip's text. */
export interface Fact { term: string; short: string; full: string; tip: string }
type Wording = Pick<Fact, "short" | "full">;

export function unscoredFacts(key: string, col: ColumnSummary | undefined, doc: ScoreDoc, basis: ScoreBasis,
  implied: string[]): { candidates: Fact; golden: Fact } {
  return { candidates: candidatesFact(key, doc), golden: goldenFact(key, col, basis, implied) };
}

/** The score that shows an output against the chosen golden side: with Human-reviewed, the newest score of the
 * human-reviewed values (`human-reviewed`, or the latest version, whose human-reviewed tree each review rewrites);
 * with Rule-matched, the newest of the chosen golden dataset. A done score first, then a running one, then the rest. */
export function scoreFor(o: Output, basis: ScoreBasis, golden: string, latest: string | null): ScoreBrief | undefined {
  const mine = o.scores.filter((s) => basis === "human" ? s.golden === HUMAN || s.golden === latest : s.golden === golden)
    .sort((a, b) => b.created_at.localeCompare(a.created_at));
  return mine.find((s) => s.status === "done" && outcomesOf(s, basis)) ?? mine.find((s) => s.status === "running") ?? mine[0];
}

export function outcomesOf(brief: ScoreBrief, basis: ScoreBasis) {
  return basis === "human" ? brief.human_outcomes : brief.rule_outcomes;
}

/** A value as the tab shows it: an object (a duration) as its fields, `description: … · timeRequired: …`. */
export function shown(v: string | null | undefined): string {
  if (!v || !v.startsWith("{")) return v ?? "";
  try {
    const o = JSON.parse(v) as Record<string, unknown>;
    return Object.entries(o).map(([k, x]) => `${k.split(":").pop()}: ${String(x)}`).join(" · ");
  } catch { return v; }
}

/** The golden side's name: the golden dataset (human-reviewed values), a version's silver dataset (rule-matched values). */
export const goldenName = (id: string) =>
  id === HUMAN ? "Golden dataset (human-reviewed)" : /^ruleset-v\d+$/.test(id) ? `Silver dataset ${id}` : `draft ${id}`;
export const goldenTerm = (basis: ScoreBasis) => (basis === "human" ? "Golden values" : "Rule-matched values");
export const goldenTip = (basis: ScoreBasis) => basis === "human"
  ? "Golden values: the values a person reviewed (the golden dataset)."
  : "Rule-matched values: the values the Studio's rules matched, with the human-reviewed ones (the silver dataset).";
/** A column with a CTDL term is written with its prefix-free path ("creditValue>minValue"); a property with none is its
 * label ("Learning Type"), which has a space. */
export const hasCtdlTerm = (key: string) => !/\s/.test(key);

export const num = (c: AnyCounts, o: ScoreOutcome) => (c as Counts | null | undefined)?.[o] ?? 0;
export const total = (c: AnyCounts) => OUTCOMES.reduce((t, o) => t + num(c, o), 0);
/** The candidates: every outcome with a value in xtra's extract output. */
export const candidateCount = (c: AnyCounts) => num(c, "match") + num(c, "partial") + num(c, "wrong") + num(c, "extra");

/** match ÷ golden values (found; the exact match rate). */
export const rateOf = (c: Counts | null | undefined) => {
  const n = GOLDEN_OUTCOMES.reduce((t, o) => t + num(c, o), 0);
  return c && n ? num(c, "match") / n : null;
};
/** match ÷ candidates (right), or null when nothing was extracted. */
export const rightOf = (c: AnyCounts) => {
  const n = candidateCount(c);
  return c && n ? num(c, "match") / n : null;
};
export const pct = (x: number | null | undefined) => (x === null || x === undefined ? "–" : `${Math.round(x * 100)}%`);

function candidatesFact(key: string, doc: ScoreDoc): Fact {
  const n = doc.candidates?.[key] ?? 0;
  return { term: "Candidates", tip: CANDIDATES_TIP, ...candidatesWording(n, extractsProperty(key, doc)) };
}

function goldenFact(key: string, col: ColumnSummary | undefined, basis: ScoreBasis, implied: string[]): Fact {
  const term = goldenTerm(basis);
  return { term, tip: goldenTip(basis), ...goldenWording(key, col, basis, implied, term.toLowerCase()) };
}

function extractsProperty(key: string, doc: ScoreDoc): boolean {
  const known = doc.xtra_extracts;
  return hasCtdlTerm(key) && (known ? known.includes(key) : !(doc.not_scored ?? []).includes(key));
}

function candidatesWording(n: number, extracts: boolean): Wording {
  if (n > 0) return { short: fmt(n), full: `${fmt(n)} candidate${n === 1 ? "" : "s"}` };
  if (extracts) return { short: "none in this output", full: "No candidates in this output" };
  return { short: "none · xtra doesn't extract it", full: "No candidates: xtra doesn't extract this property" };
}

function goldenWording(key: string, col: ColumnSummary | undefined, basis: ScoreBasis, implied: string[], noun: string): Wording {
  if (!hasCtdlTerm(key)) return { short: "Studio only: no CTDL property", full: "Studio only: no CTDL property" };
  if (implied.includes(key)) return { short: "not read from the page", full: "Not read from the page" };
  const count = goldenCount(col, basis);
  if (count > 0) return countedWording(count, ruleStatus(col), noun);
  return noGoldenWording(col, ruleStatus(col), noun);
}

function goldenCount(col: ColumnSummary | undefined, basis: ScoreBasis): number {
  return col ? (basis === "human" ? col.human : col.human + col.rule) : 0;
}

function ruleStatus(col: ColumnSummary | undefined): string | null {
  if (!col || col.no_rule) return null;
  return col.status === "needs work" || col.status === "in review" ? col.status : null;
}

function countedWording(count: number, status: string | null, noun: string): Wording {
  return { short: `${fmt(count)}${status ? ` · Studio rule ${status}` : ""}`,
    full: `${fmt(count)} ${count === 1 ? noun.replace(/s$/, "") : noun}${status ? ` · the Studio rule is ${status}` : ""}` };
}

function noGoldenWording(col: ColumnSummary | undefined, status: string | null, noun: string): Wording {
  if (!col || col.no_rule) return { short: "none · no Studio rule yet", full: `No ${noun}: no Studio rule yet` };
  if (status) return { short: `none · Studio rule ${status}`,
    full: `No ${noun}: the Studio rule ${status === "needs work" ? "needs work" : "is in review"}` };
  return { short: "none", full: `No ${noun}` };
}
