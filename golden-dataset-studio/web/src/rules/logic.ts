// Pure helpers of the Rules and Records tabs (no React, no fetch): wording, verdict events, keyboard, page tabs.
import type { EventBrief, Expected, NewEvent, Polarity, ReviewMarks, RowItem, RowStateName, RuleKind, RuleSummary, Verdict } from "../api/types";
import type { CapturedSelection } from "../pagepane";
import { reasonLabel } from "./claims";

// --- wording ---------------------------------------------------------------------------------------------------
/** "AVC course title - Antelope Valley College …" → the part a tab or a row has room for. */
export const shortTitle = (t: string | null | undefined, n = 60) =>
  (t || "").replace(/\s+[-|–]\s+Antelope Valley College.*$/, "").slice(0, n);

/** What one row is, in the rows bar: "1,062 courses", "2,751 courses found", "197 pages". */
export function unitWord(kind: RuleKind, locator: string | null): string {
  if (kind === "page") return "pages";
  if (kind === "locator") return "courses found";
  return locator && locator !== "locator-course-page" ? "course lines" : "courses";
}

/** Where a property rule looks, under its title: "Description · course pages". */
export function whereWord(locator: string | null): string {
  if (!locator || locator === "locator-course-page") return "course pages";
  if (locator === "locator-program-requirement") return "course lines on program pages";
  return locator.replace(/^locator-/, "").replace(/-/g, " ");
}

/** A long selection as the row shows it: the start and the end, never more than ~260 characters. */
export function clip(text: string, max = 260): string {
  const t = text.trim();
  return t.length > max ? `${t.slice(0, 140)} … ${t.slice(-100)}` : t;
}

/** The uncovered-code signal's detail, `'CFE 201' in “CFE 201 fulfils CORE 8 Requirements” is outside …`. */
export function parseMark(detail: string): { code: string; line: string } {
  const code = /'([^']+)'/.exec(detail)?.[1] ?? "";
  const line = /“([^”]*)”/.exec(detail)?.[1] ?? detail;
  return { code, line };
}

/** Why Approve is greyed out (spec §7.2), or null when it can be approved. A property with no rule yet has nothing to
 * approve (property-rules spec §4.6). */
export function approveBlocked(s: Pick<RuleSummary, "open_wrong" | "open_missing"> & Partial<Pick<RuleSummary, "no_rule">>): string | null {
  if (s.no_rule) return "No rule yet: this property has no rule to approve. Write one (Generate rules, or Improve) to approve it.";
  const n = s.open_wrong + s.open_missing;
  if (!n) return null;
  return `Can't approve yet: ${n.toLocaleString("en-US")} ${n === 1 ? "course is" : "courses are"} marked wrong or missing. ` +
    "A rule is approved only when none of its courses is. Fix it with “Improve rules with AI”, or change those verdicts.";
}

/** Search (m4): a rule matches by its name, its CTDL term without prefixes ("creditValue>minValue"), its subtitle, and its
 * parent's name. Case doesn't matter; an empty search matches every rule. */
export function matchesRule(r: RuleSummary, query: string): boolean {
  const q = query.trim().toLowerCase();
  if (!q) return true;
  const term = (r.ctdl_property ?? "").replace(/[a-z]+:/gi, "");
  return [r.title, r.subtitle, term, r.parent_label ?? ""].some((x) => x.toLowerCase().includes(q));
}

// --- row state ---------------------------------------------------------------------------------------------------
/** States whose verdict still applies to the value shown: the row "has a verdict" and fades back (spec §7.2).
 *  `fixed` and `changed-since-correct` need a fresh look, so they stay bright. */
const SETTLED = new Set<RowStateName>(["correct", "wrong", "still-wrong", "question", "missing"]);
export const isSettled = (state: RowStateName | null | undefined) => !!state && SETTLED.has(state);

/** Which of the three controls is lit. */
export function controlOn(state: RowStateName | null | undefined): "correct" | "wrong" | "question" | null {
  if (state === "correct") return "correct";
  if (state === "wrong" || state === "still-wrong" || state === "missing") return "wrong";
  if (state === "question") return "question";
  return null;
}

export interface HistItem {
  cls: "good" | "bad" | "note" | "expert" | "comment" | "muted"; text: string; author?: string;
  /** made on a diff (Evals, Compare): what it was compared with, e.g. "while comparing with xtra's extract output, 28 Oct" */
  compared?: string;
  /** the annotation it shows (a report's link can point at it: ?note=) */
  id?: string;
  /** a comment pinned to text on the page: its bubble's number there */
  n?: number;
  /** a comment Claude wrote in an AI run: "(v10, AI run Nov 6)" after the name, the run linked (one-rule-runs §1.6) */
  run?: { id: string; version: number | null; at: string };
  /** when it happened, shown after `text` as a relative time ("12 minutes ago") whose tooltip is the full date and
   * time zone; `after` follows it (", after this run.") */
  when?: string; after?: string;
}

/** "Nov 5, 2026, 6:28 PM MST": the full date and time with the time zone (the tooltip of a relative time). */
export const fullTime = (at: string) => new Date(at).toLocaleString("en-US", {
  month: "short", day: "numeric", year: "numeric", hour: "numeric", minute: "2-digit", timeZoneName: "short" });

/** A time as people say it: "just now", "12 minutes ago", "3 hours ago", "yesterday", "4 days ago", then "Oct 21"
 * (with the year when it isn't this year). Never a bare clock time, which says nothing without its time zone. */
export function ago(at: string | null | undefined, now = Date.now()): string {
  const t = at ? Date.parse(at) : NaN;
  if (Number.isNaN(t)) return "";
  const m = Math.floor((now - t) / 60_000);
  if (m < 1) return "just now";
  if (m < 60) return m === 1 ? "1 minute ago" : `${m} minutes ago`;
  const dayStart = (x: number) => { const d = new Date(x); d.setHours(0, 0, 0, 0); return d.getTime(); };
  const days = Math.round((dayStart(now) - dayStart(t)) / 86_400_000);
  const h = Math.floor(m / 60);
  if (days === 0 || h < 6) return h === 1 ? "1 hour ago" : `${h} hours ago`;
  if (days === 1) return "yesterday";
  if (days < 7) return `${days} days ago`;
  const d = new Date(t);
  return d.toLocaleDateString("en-US", { month: "short", day: "numeric",
    ...(d.getFullYear() !== new Date(now).getFullYear() ? { year: "numeric" } : {}) });
}

/** "Nov 6" (the browser's time zone). */
export const monthDay = (at: string) => new Date(at).toLocaleDateString("en-US", { month: "short", day: "numeric" });
const isAi = (e: EventBrief) => e.author_role === "ai" || (!!e.run_id && e.author === "Claude");

/** The short line a note or a verdict made on a diff carries (Evals spec §4.2). */
export function comparedLine(e: Pick<EventBrief, "compared_with" | "at"> | null | undefined, now = Date.now()): string | undefined {
  const c = e?.compared_with;
  if (!c) return undefined;
  const what = c.kind === "extract" ? "xtra's extract output" : c.kind === "ruleset" ? `ruleset v${c.ruleset}` : "another value";
  return `while comparing with ${what}, ${shortWhen(e!.at, now)}`;
}

/** The history line under a row: what happened to its verdict across versions, notes, comments, questions. */
export function historyItems(r: { state: RowStateName | null; verdict: EventBrief | null; reattached?: boolean;
  comments: EventBrief[]; page_questions?: EventBrief[] }): HistItem[] {
  const out: HistItem[] = [];
  const v = r.verdict;
  const who = v?.author ?? "Someone";
  switch (r.state) {
    case "fixed":
      out.push({ cls: "good", text: `Fixed: ${who} marked the previous version wrong; this matches the text he selected.` });
      break;
    case "still-wrong":
      out.push({ cls: "bad", text: `Still wrong: ${who} marked the previous version wrong; the new value still differs from the text he selected.` });
      break;
    case "changed-since-correct":
      out.push({ cls: "bad", text: `Changed: ${who} marked the previous version correct, but the value has changed since.` });
      break;
    default:
  }
  if (r.reattached && v) out.push({ cls: "muted", text: `Re-attached: ${who}'s verdict was made before the record locator changed.` });
  const vc = v && r.state !== "fixed" ? comparedLine(v) : undefined;
  const vid = v?.annotation_id;
  if (v && (r.state === "wrong" || r.state === "still-wrong" || r.state === "missing") && v.expected?.text) {
    out.push({ cls: "note", text: `expected “${clip(v.expected.text, 90)}”`, compared: v.note ? undefined : vc, id: vid });
  }
  if (v?.reasons?.length && (r.state === "wrong" || r.state === "still-wrong")) out.push({ cls: "note", text: `Why wrong: ${v.reasons.map(reasonLabel).join(", ")}` });
  if (v?.note) {
    if (r.state === "question") out.push({ cls: "expert", text: `Question for the institution: “${v.note}”`, id: vid });
    else if (r.state !== "fixed") out.push({ cls: "note", author: v.author, text: `“${v.note}”`, compared: vc, id: vid });
  } else if (r.state === "question") out.push({ cls: "expert", text: "Waiting for the institution's answer" });
  for (const q of r.page_questions ?? []) {
    out.push({ cls: "expert", text: q.note ? `Question for the institution: “${q.note}”` : "Question for the institution (no note yet)", id: q.annotation_id });
  }
  let pinned = 0;  // comments pinned to text on the page: numbered like their bubbles there
  for (const c of r.comments) {
    const n = c.anchor?.css_path ? ++pinned : undefined;
    if (!c.note) continue;
    if (isAi(c)) { out.push(aiItem(c)); continue; }
    out.push({ cls: "comment", author: c.author, text: `“${c.note}”`, compared: comparedLine(c), n, id: c.annotation_id });
  }
  return out;
}

/** Claude's comment from an AI run: "Claude (v10, AI run Nov 6): …", the run linked (one-rule-runs §1.6). */
function aiItem(c: EventBrief & { run_at?: string | null }): HistItem {
  return { cls: "note", author: c.author, text: c.note ?? "", id: c.annotation_id,
           run: c.run_id ? { id: c.run_id, version: c.ruleset_version ?? null, at: c.run_at ?? c.at } : undefined };
}

/** A report row's history line (one-rule-runs §1.4, §1.6; contract §2.6): every live verdict and comment, oldest
 * first. A verdict's note, Claude's comments with their run, and what people did after the run said as such, with a
 * relative time whose tooltip has the date and time zone: "Jared Diener marked it correct 12 minutes ago, after this run." */
export function reportHistory(events: (EventBrief & { run_at?: string | null; after_run?: boolean; kind?: string })[]): HistItem[] {
  const out: HistItem[] = [];
  let pinned = 0;
  for (const x of events) {
    // the CLI's resolved report names an item's type `kind` (contract §3.3); `…/rows` sends `type`
    const e = x.type ? x : { ...x, type: x.kind as EventBrief["type"] };
    if (e.type === "comment") {
      const n = e.anchor?.css_path ? ++pinned : undefined;
      if (!e.note) continue;
      if (isAi(e)) { out.push(aiItem(e)); continue; }
      out.push({ cls: "comment", author: e.author, text: `“${e.note}”`, n, id: e.annotation_id,
                 ...(e.after_run ? { when: e.at, after: ", after this run." } : {}) });
      continue;
    }
    if (e.type !== "verdict") continue;
    const note = e.note ? `“${e.note}”` : e.expected?.text ? `expected “${clip(e.expected.text, 90)}”` : "";
    if (e.after_run) {
      out.push({ cls: e.verdict === "correct" ? "good" : e.verdict === "wrong" ? "bad" : "note",
                 text: `${e.author} ${verdictWords(e)}`, when: e.at, after: `, after this run.${note ? ` ${note}` : ""}`,
                 id: e.annotation_id });
    } else if (e.verdict === "question") {
      out.push({ cls: "expert", text: e.note ? `Question for the institution: “${e.note}”` : "Waiting for the institution's answer", id: e.annotation_id });
    } else if (note) out.push({ cls: "note", author: e.author, text: note, id: e.annotation_id });
  }
  return out;
}

/** "marked it correct", "marked it wrong", "marked it Not on the page", "asked the institution". */
export function verdictWords(e: Pick<EventBrief, "verdict" | "reasons">): string {
  if (e.verdict === "correct") return "marked it correct";
  if (e.verdict === "wrong") return e.reasons?.includes("not_on_page") ? "marked it Not on the page" : "marked it wrong";
  if (e.verdict === "question") return "asked the institution";
  return `marked it ${e.verdict ?? ""}`.trim();
}

/** A row's mark in a table: "Correct", "Wrong", "Not on the page", "Question for the institution", "Not reviewed". */
export function markWord(e: Pick<EventBrief, "verdict" | "reasons"> | null | undefined): string {
  if (!e?.verdict) return "Not reviewed";
  if (e.verdict === "correct") return "Correct";
  if (e.verdict === "wrong") return e.reasons?.includes("not_on_page") ? "Not on the page" : "Wrong";
  if (e.verdict === "question") return "Question for the institution";
  return e.verdict === "missing" ? "Missing" : e.verdict;
}

// --- events ------------------------------------------------------------------------------------------------------
export type DraftMode = "wrong" | "comment";
/** Text compared the way the server compares values (review.norm): runs of whitespace are one space. */
export const norm = (v: string | null | undefined): string => (v ?? "").replace(/\s+/g, " ").trim();

/** A piece of the reviewer's answer selected on the page: `in` the answer (the default) or `out` of it (sme-fixes §1). */
export type Piece = CapturedSelection & { polarity?: Polarity };

/** A draft verdict or comment. `captures`: the right value as the reviewer selected it on the page, one or more
 * pieces (a value can be split across the page: two paragraphs with a heading between them), in page order, each in
 * or out of the answer. `anchor`: the text a comment is about (💬 on the highlight bar). */
export interface Draft { mode: DraftMode; captures: Piece[]; note: string; question: boolean; anchor?: CapturedSelection | null;
  /** "Why wrong?" flags ticked after ✕ (sme-fixes §6, claims.ts REASONS) */
  reasons?: string[] }

export const newDraft = (mode: DraftMode, verdict: EventBrief | null, state: RowStateName | null): Draft => ({
  mode, captures: [],
  // editing a question shows its note; anything else starts empty
  note: mode === "comment" && state === "question" ? verdict?.note ?? "" : "",
  question: mode === "comment" && state === "question",
});

function overlaps(a: CapturedSelection, b: CapturedSelection): boolean {
  if (a.doc_start != null && a.doc_end != null && b.doc_start != null && b.doc_end != null)
    return a.doc_start < b.doc_end && b.doc_start < a.doc_end;
  return a.css_path === b.css_path && a.char_start < b.char_end && b.char_start < a.char_end;
}

/** Add a selected piece: it replaces any piece it overlaps (selecting again fixes a piece); pieces stay in page order. */
export function addCapture<C extends CapturedSelection>(cs: C[], c: C): C[] {
  const kept = cs.filter((x) => !overlaps(x, c));
  return [...kept, c].sort((a, b) => (a.doc_start ?? Infinity) - (b.doc_start ?? Infinity));
}

const located = (c: CapturedSelection) => ({ text: c.text, css_path: c.css_path, char_start: c.char_start, char_end: c.char_end,
  quote: { prefix: c.prefix, exact: c.text, suffix: c.suffix } });
const isOut = (c: Piece) => c.polarity === "out";

/** The pieces with the one at `c`'s place marked `polarity` (✕ Not in answer on a piece just added); text that isn't a
 * piece yet (the value found, hovered) is added as one. */
export function markPiece(cs: Piece[], c: CapturedSelection, polarity: Polarity): Piece[] {
  const at = (x: Piece) => x.css_path === c.css_path && x.char_start === c.char_start && x.char_end === c.char_end;
  return cs.some(at) ? cs.map((x) => (at(x) ? { ...x, polarity } : x)) : addCapture(cs, { ...c, polarity });
}

/** The value found without the text marked "not in the answer". */
export function withoutOut(value: string | null | undefined, outs: string[]): string {
  let v = value ?? "";
  for (const o of outs) { const t = o.trim(); if (t) v = v.replace(t, ""); }
  return v.replace(/[ \t]+\n/g, "\n").replace(/\n{3,}/g, "\n\n").trim();
}

/** The `expected` of a wrong verdict: one piece in the answer as before; several pieces → the `in` ones' text joined
 * by line breaks in page order (what the rule should extract), located at the first piece, every piece in `segments`
 * with its polarity. With only `out` pieces, the text is the value found (`value`) without them. */
export function expectedOf(c: Piece | Piece[] | null, value?: string | null): Expected | null {
  const cs = c === null ? [] : Array.isArray(c) ? c : [c];
  if (!cs.length) return null;
  const ins = cs.filter((x) => !isOut(x));
  const e: Expected = { ...located(ins[0] ?? cs[0]), located_by: "highlight in the Studio" };
  if (cs.length > 1 || !ins.length) {
    e.text = ins.length ? ins.map((x) => x.text.trim()).join("\n") : withoutOut(value, cs.map((x) => x.text));
    e.segments = cs.map((x) => ({ ...located(x), polarity: isOut(x) ? "out" as const : "in" as const }));
  }
  return e;
}

export type Target = NewEvent["target"];

/** A row's annotation target: a match (property rule), an occurrence (record locator) or a page (page rule). */
export function rowTarget(kind: RuleKind, ruleId: string, row: { occurrence_key: string | null; page_stem: string }): Target {
  if (kind === "property") return { kind: "match", rule_id: ruleId, occurrence_key: row.occurrence_key, page_stem: row.page_stem };
  if (kind === "locator") return { kind: "occurrence", rule_id: ruleId, occurrence_key: row.occurrence_key, page_stem: row.page_stem };
  return { kind: "page", rule_id: ruleId, page_stem: row.page_stem };
}

/** The event a saved draft (or a ✓) becomes. A changed verdict supersedes the previous one (spec §4.3). */
export function verdictEvent(author: string, target: Target, prev: EventBrief | null,
  what: { verdict: "correct" } | { draft: Draft }, value?: string | null): NewEvent {
  const supersedes = prev && prev.type === "verdict" ? prev.annotation_id : null;
  if ("verdict" in what) return { type: "verdict", author, target, verdict: "correct", supersedes };
  const d = what.draft;
  const note = d.note.trim() || null;
  if (d.mode === "comment" && !d.question) {
    const a = d.anchor;
    return { type: "comment", author, target, note,
             ...(a ? { anchor: { css_path: a.css_path, char_start: a.char_start, char_end: a.char_end, text: a.text } } : {}) };
  }
  const verdict: Verdict = d.mode === "comment" ? "question" : "wrong";
  // a ✗ with a comment pinned to text: the note is that comment (pinnedComment), saved after the verdict
  return { type: "verdict", author, target, verdict, note: verdict === "wrong" && d.anchor ? null : note, supersedes,
           expected: verdict === "wrong" ? expectedOf(d.captures, value) : null,
           ...(verdict === "wrong" && d.reasons?.length ? { reasons: d.reasons } : {}) };
}

/** The comment pinned to text that goes with a ✗ (the comment bubble on the highlight bar, then ✓ or ✕): a comment
 * event with its anchor, or null when there is no pinned text or nothing written. */
export function pinnedComment(author: string, target: Target, d: Draft): NewEvent | null {
  const a = d.anchor, note = d.note.trim();
  if (d.mode !== "wrong" || !a || !note) return null;
  return { type: "comment", author, target, note, anchor: { css_path: a.css_path, char_start: a.char_start, char_end: a.char_end, text: a.text } };
}

// --- course blocks: one row per page (sme-fixes §3) --------------------------------------------------------------
/** A page's rows of a repeating record locator: rows `start`…`end - 1` (they come grouped by page). */
export interface PageGroup { stem: string; start: number; end: number }
export type Level = "page" | "course";

export function pageGroups(rows: { page_stem: string }[]): PageGroup[] {
  const out: PageGroup[] = [];
  rows.forEach((r, i) => {
    const last = out[out.length - 1];
    if (last && last.stem === r.page_stem && last.end === i) last.end = i + 1;
    else out.push({ stem: r.page_stem, start: i, end: i + 1 });
  });
  return out;
}

export const groupOf = (gs: PageGroup[], i: number) => gs.find((g) => i >= g.start && i < g.end) ?? null;

/** The subject of a page's courses ("INTD" for INTD100, INTD102): their course keys' common letters. */
export function subjectOf(keys: (string | null)[]): string {
  const ps = keys.map((k) => /^[A-Z]+/.exec(k ?? "")?.[0] ?? "").filter(Boolean);
  if (!ps.length) return "";
  return ps.every((p) => p === ps[0]) ? ps[0] : "";
}

/** Tab / Shift+Tab / Esc in a repeating locator's rows: Tab and Shift+Tab move between the courses inside a page
 * (Shift+Tab on its first course goes up to the page row; Tab after its last course moves on to the next page row);
 * at page level they move between pages; Enter goes down into a page's first course; Esc goes back up to the page. */
export function moveIn(gs: PageGroup[], sel: number, level: Level, a: "next" | "prev" | "down" | "up"): { sel: number; level: Level } {
  const g = groupOf(gs, sel);
  if (!g) return { sel, level };
  const gi = gs.indexOf(g);
  if (a === "up") return { sel: g.start, level: "page" };
  if (a === "down") return level === "page" ? { sel: g.start, level: "course" } : { sel, level };
  if (level === "page") {
    const to = gs[a === "next" ? gi + 1 : gi - 1];
    return to ? { sel: to.start, level: "page" } : { sel: g.start, level: "page" };
  }
  if (a === "next") return sel + 1 < g.end ? { sel: sel + 1, level } : gs[gi + 1] ? { sel: gs[gi + 1].start, level: "page" } : { sel, level };
  return sel > g.start ? { sel: sel - 1, level } : { sel: g.start, level: "page" };
}

/** "Add a course / page this rule missed" (spec §7.2): a `missing` verdict with no occurrence. */
export function missingEvent(author: string, kind: RuleKind, ruleId: string, pageStem: string,
  capture: CapturedSelection | null, note: string): NewEvent {
  return {
    type: "verdict", author, verdict: "missing", note: note.trim() || null,
    target: kind === "locator" ? { kind: "occurrence", rule_id: ruleId, occurrence_key: null, page_stem: pageStem }
      : { kind: "page", rule_id: ruleId, page_stem: pageStem },
    expected: kind === "locator" ? expectedOf(capture) : null,
  };
}

/** The brief the rows keep, made from the event the server stored. */
export function briefOf(e: { annotation_id: string; type: EventBrief["type"]; verdict: Verdict | null; author: string; at: string;
  note: string | null; expected: Expected | null; target: { rule_version_seen?: number | null; value_seen?: string | null } }): EventBrief {
  return { annotation_id: e.annotation_id, type: e.type, verdict: e.verdict, author: e.author, at: e.at, note: e.note,
           expected: e.expected, rule_version_seen: e.target.rule_version_seen ?? null, value_seen: e.target.value_seen ?? null };
}

/** Apply a stored event to a row (no refetch: a verdict must show within the §10 budget). */
export function applyEvent<R extends { state: RowStateName | null; verdict: EventBrief | null; comments: EventBrief[]; reattached?: boolean }>(
  row: R, ev: EventBrief): R {
  if (ev.type === "comment") return { ...row, comments: [...row.comments, ev] };
  if (ev.type !== "verdict" || !ev.verdict) return row;
  return { ...row, verdict: ev, state: ev.verdict, reattached: false };
}

// --- list items (property-rules spec §4.4) ---------------------------------------------------------------------------
/** A verdict on one item of a list property's row: ✓ correct or ✕ wrong, targeting that item by its `value_index`. */
export function itemEvent(author: string, ruleId: string, row: { occurrence_key: string | null; page_stem?: string },
  valueIndex: number, verdict: "correct" | "wrong", supersedes: string | null): NewEvent {
  return { type: "verdict", author, verdict, supersedes,
           target: { kind: "match", rule_id: ruleId, occurrence_key: row.occurrence_key, item: true, value_index: valueIndex } };
}

/** An item the rule missed: a missing verdict on the row, with the text selected on the page as expected. */
export function missingItemEvent(author: string, ruleId: string, occurrenceKey: string | null, capture: CapturedSelection,
  note = ""): NewEvent {
  return { type: "verdict", author, verdict: "missing", note: note.trim() || null, expected: expectedOf(capture),
           target: { kind: "match", rule_id: ruleId, occurrence_key: occurrenceKey, item: true } };
}

/** The row's items with one item's verdict applied (no refetch). A ✓ by an expert makes the item human-reviewed. */
export function applyItem<R extends { items?: RowItem[] }>(row: R, valueIndex: number, ev: EventBrief, role: string | null): R {
  const items = (row.items ?? []).map((it) => it.value_index !== valueIndex ? it
    : { ...it, state: ev.verdict === "correct" ? "correct" as const : "wrong" as const, verdict: ev,
        human: role === "sme" && ev.verdict === "correct" });
  return { ...row, items };
}

/** The row's missing items with one more added (no refetch). */
export function applyMissingItem<R extends { missing_items?: EventBrief[] }>(row: R, ev: EventBrief): R {
  return { ...row, missing_items: [...(row.missing_items ?? []), ev] };
}

// --- human-reviewed / engineer-checked (Evals spec §4.3, §6.7) ---------------------------------------------------
/** An expert can confirm a value only an engineer checked: Confirm (or 1) is an ordinary ✓ by the expert. */
export const canConfirm = (r: ReviewMarks, role: string | null) => !!r.engineer_checked && role === "sme";

/** A verdict just saved, on the row's marks (as review.py computes them). An expert's ✓ makes the value
 * human-reviewed; an engineer's ✓ leaves an expert's standing, else waits for an expert; any other verdict clears both. */
export function applyReview<R extends ReviewMarks>(row: R, ev: EventBrief, role: string | null): R {
  if (ev.type !== "verdict") return row;
  if (ev.verdict !== "correct") return { ...row, human_reviewed: false, engineer_checked: false, human: null };
  if (role === "sme") return { ...row, human_reviewed: true, engineer_checked: false, human: ev };
  return row.human_reviewed ? row : { ...row, engineer_checked: true, checked: ev };
}

/** "just now" within a minute, else "21 Oct" (the browser's time zone). */
export function shortWhen(at: string | null | undefined, now = Date.now()): string {
  const t = at ? Date.parse(at) : NaN;
  if (Number.isNaN(t) || now - t < 60_000) return "just now";
  return new Date(t).toLocaleDateString("en-GB", { day: "numeric", month: "short" });
}

/** The "Annotated by" filter's choices besides a person (review.py NOBODY, WAITING), as the dropdown names them. */
export const BY_NOBODY = "nobody";
export const BY_WAITING = "waiting";
/** Any subject matter expert / any engineer: every value someone of that role annotated (not only those waiting). */
export const BY_EXPERTS = "experts";
export const BY_ENGINEERS = "engineers";
/** "Anyone", as older links wrote it. "Anyone" is the default now (sme-fixes §9): no `by` in the URL means Anyone. */
export const BY_ANYONE = "anyone";
/** The subject matter expert who annotated the most values (Jared, on AVC): the Rules tab's default "Annotated by"
 * until sme-fixes §9 made it Anyone. */
export function defaultAnnotator(people: { name: string; role: string; values: number }[] | undefined): string | null {
  const top = (people ?? []).filter((p) => p.role === "sme" && p.values > 0).sort((a, b) => b.values - a.values)[0];
  return top?.name ?? null;
}
export function byLabel(by: string | null): string {
  if (!by) return "Anyone";
  if (by === BY_NOBODY) return "Not annotated yet";
  if (by === BY_WAITING) return "Any engineer · waiting for an expert";
  if (by === BY_EXPERTS) return "Any subject matter expert";
  if (by === BY_ENGINEERS) return "Any engineer";
  return by;
}

/** What a rule's count in the rule list means while the "Annotated by" filter is on (its delayed tooltip). */
export function filterCountTip(n: number, by: string | null, verdict: string | null): string {
  const rows = `${n.toLocaleString("en-US")} ${n === 1 ? "row" : "rows"}`;
  const how = verdict === "correct" ? " (✓ correct)" : verdict === "wrong" ? " (✕ wrong)" : verdict === "note" ? " (with a note)" : "";
  if (by === BY_NOBODY) return `${rows} nobody has annotated yet`;
  if (by === BY_WAITING) return `${rows} checked by an engineer, waiting for an expert${how}`;
  if (by === BY_EXPERTS) return `${rows} annotated by a subject matter expert${how}`;
  if (by === BY_ENGINEERS) return `${rows} annotated by an engineer${how}`;
  if (!by) return `${rows} annotated by anyone${how}`;
  return `${rows} annotated by ${by}${how}`;
}

// --- keyboard ----------------------------------------------------------------------------------------------------
export type KeyAction = "next" | "prev" | "correct" | "wrong" | "comment" | "select" | "save" | "cancel" | null;

/** Keys of the Rules tab (spec §7.2): Tab next row, A correct, W wrong, C comment, H select text, Enter save, Esc cancel.
 *  Inside a text field only Enter and Esc count. */
export function keyAction(e: { key: string; shiftKey?: boolean; metaKey?: boolean; ctrlKey?: boolean; altKey?: boolean },
  inField: boolean): KeyAction {
  if (e.key === "Enter" && !e.shiftKey) return "save";
  if (e.key === "Escape") return "cancel";
  if (inField || e.metaKey || e.ctrlKey || e.altKey) return null;
  if (e.key === "Tab") return e.shiftKey ? "prev" : "next";
  const k = e.key.toLowerCase();
  return ({ a: "correct", w: "wrong", c: "comment", h: "select", 1: "correct", 2: "wrong", 3: "comment" } as Record<string, KeyAction>)[k] ?? null;
}

/** The Rules tab's keys (1, 2, 3, A, W, C, Enter) act on its selected row only when nothing covers the list: with an
 * AI run's report or the AI runs drawer open (`.run-watch`), a key pressed there must never mark the row behind it. */
export const rowKeysBlocked = (doc: Document = document) => !!doc.querySelector(".run-watch");

export const isField = (t: EventTarget | null) => {
  const el = t as HTMLElement | null;
  return !!el && (el.tagName === "INPUT" || el.tagName === "TEXTAREA" || el.tagName === "SELECT" || el.isContentEditable);
};

// --- page tabs ---------------------------------------------------------------------------------------------------
export interface TabRef { stem: string; url: string; title: string }

/** Tabs of the page pane: the row's page, the other pages its course is on, then the last few pages viewed. */
export function paneTabs(current: TabRef | null, others: TabRef[], recent: TabRef[], max = 8): TabRef[] {
  const out: TabRef[] = [];
  const seen = new Set<string>();
  for (const t of [...(current ? [current] : []), ...others, ...recent]) {
    if (seen.has(t.stem)) continue;
    seen.add(t.stem);
    out.push(t);
    if (out.length >= max) break;
  }
  return out;
}

/** Remember a viewed page; newest first, at most `keep`. */
export function pushRecent(recent: TabRef[], t: TabRef, keep = 3): TabRef[] {
  return [t, ...recent.filter((x) => x.stem !== t.stem)].slice(0, keep);
}

// --- DOM -------------------------------------------------------------------------------------------------------
/** Scroll a list so `el` is visible, without scrolling the document (scrollIntoView would move the top bar). */
export function scrollWithin(box: HTMLElement, el: HTMLElement, center: boolean): void {
  const b = box.getBoundingClientRect();
  const r = el.getBoundingClientRect();
  const top = r.top - b.top + box.scrollTop;
  if (center) box.scrollTop = top - (box.clientHeight - r.height) / 2;
  else if (r.top < b.top) box.scrollTop = top - 8;
  else if (r.bottom > b.bottom) box.scrollTop = top + r.height - box.clientHeight + 8;
}

