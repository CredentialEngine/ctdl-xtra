// Pure helpers of the Rules and Records tabs (no React, no fetch): wording, verdict events, keyboard, page tabs.
import type { EventBrief, Expected, NewEvent, ReviewMarks, RowStateName, RuleKind, RuleSummary, Verdict } from "../api/types";
import type { CapturedSelection } from "../pagepane";

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

/** Where a field rule looks, under its title: "Description · course pages". */
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

/** Why Approve is greyed out (spec §7.2), or null when it can be approved. */
export function approveBlocked(s: Pick<RuleSummary, "open_wrong" | "open_missing">): string | null {
  const n = s.open_wrong + s.open_missing;
  if (!n) return null;
  return `Can't approve yet: ${n.toLocaleString("en-US")} ${n === 1 ? "course is" : "courses are"} marked wrong or missing. ` +
    "A rule is approved only when none of its courses is. Fix it with “Improve all rules”, or change those verdicts.";
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
}

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
  if (v && (r.state === "wrong" || r.state === "still-wrong" || r.state === "missing") && v.expected?.text) {
    out.push({ cls: "note", text: `expected “${clip(v.expected.text, 90)}”`, compared: v.note ? undefined : vc });
  }
  if (v?.note) {
    if (r.state === "question") out.push({ cls: "expert", text: `Question for the institution: “${v.note}”` });
    else if (r.state !== "fixed") out.push({ cls: "note", author: v.author, text: `“${v.note}”`, compared: vc });
  } else if (r.state === "question") out.push({ cls: "expert", text: "Waiting for the institution's answer" });
  for (const q of r.page_questions ?? []) {
    out.push({ cls: "expert", text: q.note ? `Question for the institution: “${q.note}”` : "Question for the institution (no note yet)" });
  }
  for (const c of r.comments) if (c.note) out.push({ cls: "comment", author: c.author, text: `“${c.note}”`, compared: comparedLine(c) });
  return out;
}

// --- events ------------------------------------------------------------------------------------------------------
export type DraftMode = "wrong" | "comment";
/** Text compared the way the server compares values (review.norm): runs of whitespace are one space. */
export const norm = (v: string | null | undefined): string => (v ?? "").replace(/\s+/g, " ").trim();

/** A draft verdict or comment. `captures`: the right value as the reviewer selected it on the page, one or more
 * pieces (a value can be split across the page: two paragraphs with a heading between them), in page order. */
export interface Draft { mode: DraftMode; captures: CapturedSelection[]; note: string; question: boolean }

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
export function addCapture(cs: CapturedSelection[], c: CapturedSelection): CapturedSelection[] {
  const kept = cs.filter((x) => !overlaps(x, c));
  return [...kept, c].sort((a, b) => (a.doc_start ?? Infinity) - (b.doc_start ?? Infinity));
}

const located = (c: CapturedSelection) => ({ text: c.text, css_path: c.css_path, char_start: c.char_start, char_end: c.char_end,
  quote: { prefix: c.prefix, exact: c.text, suffix: c.suffix } });

/** The `expected` of a wrong verdict: one piece as before; several pieces → their text joined by line breaks in page
 * order (what the rule should extract), located at the first piece, every piece in `segments`. */
export function expectedOf(c: CapturedSelection | CapturedSelection[] | null): Expected | null {
  const cs = c === null ? [] : Array.isArray(c) ? c : [c];
  if (!cs.length) return null;
  const e: Expected = { ...located(cs[0]), located_by: "highlight in the Studio" };
  if (cs.length > 1) {
    e.text = cs.map((x) => x.text.trim()).join("\n");
    e.segments = cs.map(located);
  }
  return e;
}

export type Target = NewEvent["target"];

/** A row's annotation target: a match (field rule), an occurrence (record locator) or a page (page rule). */
export function rowTarget(kind: RuleKind, ruleId: string, row: { occurrence_key: string | null; page_stem: string }): Target {
  if (kind === "field") return { kind: "match", rule_id: ruleId, occurrence_key: row.occurrence_key, page_stem: row.page_stem };
  if (kind === "locator") return { kind: "occurrence", rule_id: ruleId, occurrence_key: row.occurrence_key, page_stem: row.page_stem };
  return { kind: "page", rule_id: ruleId, page_stem: row.page_stem };
}

/** The event a saved draft (or a ✓) becomes. A changed verdict supersedes the previous one (spec §4.3). */
export function verdictEvent(author: string, target: Target, prev: EventBrief | null,
  what: { verdict: "correct" } | { draft: Draft }): NewEvent {
  const supersedes = prev && prev.type === "verdict" ? prev.annotation_id : null;
  if ("verdict" in what) return { type: "verdict", author, target, verdict: "correct", supersedes };
  const d = what.draft;
  const note = d.note.trim() || null;
  if (d.mode === "comment" && !d.question) return { type: "comment", author, target, note };
  const verdict: Verdict = d.mode === "comment" ? "question" : "wrong";
  return { type: "verdict", author, target, verdict, note, supersedes,
           expected: verdict === "wrong" ? expectedOf(d.captures) : null };
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
/** "Anyone" picked on purpose: without a `by` the Rules tab filters to its default annotator instead. */
export const BY_ANYONE = "anyone";
/** The Rules tab's default "Annotated by": the subject matter expert who annotated the most values (Jared, on AVC). */
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

