// What the Rules tab knows without React: its list of rules (the default rule, All classes, a rule's new summary),
// the rows' names in toasts, the key hints, and how an approval's score is followed.
import { api } from "../api/client";
import type { ClassSummary, RulesResponse, RuleSummary } from "../api/types";
import { samplePrefs } from "../shell/Sample";
import type { ClassSlug } from "../shell/router";
import { fmt, toast } from "../shell/ui";
import type { RowX } from "./api";
import { shortTitle } from "./logic";

/** How long after the last verdict the "Annotated by" counts are fetched again. */
export const ANNOTATORS_SETTLE_MS = 1500;
export const FIRST_PAGE = 100;
export const MORE = 200;
export const PREFETCH = 4;
export const DEFAULT_PREFS = samplePrefs("auto");  // Autostratify (sme-fixes §9); the drawer stays shut until opened

export function defaultRule(rules: RulesResponse | null): string | null {
  if (!rules) return null;
  const all = rules.groups.flatMap((g) => g.rules);
  return (all.find((r) => r.rule_id === "course-description") ?? all.find((r) => r.kind === "property") ?? all[0])?.rule_id ?? null;
}

/** All classes: one list from each class's, its groups tagged with their class; the active class's extraction and
 * ruleset are the list's. Every group starts folded but the one that holds the open rule (mockup w4-rules-all-classes). */
export function mergeClasses(each: { cls: ClassSlug; rules: RulesResponse }[], mine: ClassSlug, active: string | null): RulesResponse {
  const own = each.find((x) => x.cls === mine) ?? each[0];
  return {
    extraction: own?.rules.extraction ?? "", ruleset_version: own?.rules.ruleset_version ?? 0, cls: own?.cls,
    groups: each.flatMap(({ cls, rules }) => rules.groups.map((g) => ({
      ...g, cls, collapsed: !(active && g.rules.some((r) => r.rule_id === active)) }))),
  };
}

/** A class's heading with All classes: "8 required, 37 properties, 30 of 43 rules approved". */
export function classHead(c: ClassSummary, rules: RulesResponse | null) {
  const required = rules?.groups.filter((g) => g.cls === c.slug && g.id === "required").reduce((n, g) => n + g.rules.length, 0) ?? 0;
  const approved = c.rules_approved ? `${fmt(c.rules_approved)} of ${fmt(c.rules_total)} rules approved` : "0 approved";
  return { name: c.name, sub: `${required ? `${required} required, ` : ""}${fmt(c.properties)} properties, ${approved}` };
}

export function replaceSummary(rules: RulesResponse, s: RuleSummary): RulesResponse {
  return { ...rules, groups: rules.groups.map((g) => {
    if (!g.rules.some((r) => r.rule_id === s.rule_id)) return g;
    const items = g.rules.map((r) => (r.rule_id === s.rule_id ? { ...r, ...s } : r));
    return { ...g, rules: items, approved: items.filter((r) => r.status === "approved").length };
  }) };
}

export const KEY_HINTS = (
  <span className="key-hints">
    <kbd>Tab</kbd>next <kbd>1</kbd>correct <kbd>2</kbd>wrong <kbd>3</kbd>comment <kbd>H</kbd>select text{" "}
    <kbd>Enter</kbd>save <kbd>Esc</kbd>cancel
  </span>
);
/** A repeating record locator's rows: one per page, its courses inside (sme-fixes §3). */
export const PAGE_KEY_HINTS = (
  <span className="key-hints" data-testid="page-key-hints">
    <kbd>Tab</kbd>next course, then page <kbd>Enter</kbd>into a page <kbd>Esc</kbd>up to the page <kbd>1</kbd>correct
    (a page: all) <kbd>2</kbd>wrong <kbd>3</kbd>comment
  </span>
);

/** A row as a toast names it: its record key, else its page's title. */
export const rowName = (r: RowX) => r.record_external_identifier ?? shortTitle(r.page_title, 40);

export const updateRow = (rows: RowX[], i: number, change: (r: RowX) => RowX) => rows.map((x, j) => (j === i ? change(x) : x));

/** "ruleset-v9" → "ruleset v9". */
export const versionName = (id?: string) => (id ?? "").replace(/^ruleset-v/, "ruleset v");

/** After an approval's publish: wait for its score, then say how it went. */
export function followScore(cat: string, id: string, version: string, tries = 0): void {
  setTimeout(async () => {
    const d = await api.scoreDoc(cat, id).catch(() => null);
    if (!d) return;
    if (d.status === "running") { if (tries < 200) followScore(cat, id, version, tries + 1); return; }
    if (d.status !== "done") { toast(`xtra score of ${version} ${d.status}${d.error ? `: ${d.error}` : ""}`); return; }
    toastScore(d, version);
  }, 3000);
}

function toastScore(d: NonNullable<Awaited<ReturnType<typeof api.scoreDoc>>>, version: string): void {
  const basis = d.results.human ? "human" : "rule";
  const res = d.results[basis];
  if (res?.exact_match_rate == null) return;
  toast(`xtra score of ${version}: ${Math.round(100 * res.exact_match_rate)}% exact, ${basis === "human" ? "human-reviewed" : "rule-matched"}`
    + ` (${fmt(res.outcomes.match)} of ${fmt(res.values)})`, 5000);
}
