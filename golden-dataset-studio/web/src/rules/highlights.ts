// What the Rules tab outlines on the page: a property's value (or where the rule looked), a list's items, the saved
// answer, pinned comments; a locator's course boxes and marks; the reviewer's selected pieces. And which one to scroll to.
import type { EventBrief, Overlay, RuleDetail } from "../api/types";
import type { CapturedSelection, Highlight } from "../pagepane";
import type { RowX } from "./api";
import type { ObjectAdd, ObjectFix } from "./claims";
import type { Draft, Piece } from "./logic";

export interface HighlightInput {
  row: RowX | null; rows: RowX[]; detail: RuleDetail | null; active: string | null; ov: Overlay | null; captures: Piece[];
  draft: Draft | null; missing: EventBrief[]; listRule: boolean; objAdd: ObjectAdd | null; objFix: ObjectFix | null; onPage: boolean;
}

export function pageHighlights(x: HighlightInput): { highlights: Highlight[]; focusId: string | null } {
  const { row, detail } = x;
  if (!row || !detail) return { highlights: [], focusId: null };
  const found = detail.kind === "property" ? propertyMarks(x, row) : x.ov ? blockMarks(x, row, detail, x.ov) : { hs: [], fid: null };
  const missed = detail.kind === "locator" ? missedCourseMarks(x) : [];
  return { highlights: [...found.hs, ...missed, ...captureMarks(x)], focusId: x.captures.length ? "capture-0" : found.fid };
}

type Marks = { hs: Highlight[]; fid: string | null };

function propertyMarks(x: HighlightInput, row: RowX): Marks {
  const here = x.active === row.page_stem;
  const value = here && !!row.css_path && row.status !== "absent";
  const looked = row.status === "absent" && !!row.css_path && here;  // where the rule looked (§6)
  const hs: Highlight[] = [
    ...(value ? [{ id: "value", kind: "value" as const, cssPath: row.css_path!, charStart: row.char_start, charEnd: row.char_end, text: row.value, badge: 1 }] : []),
    // a list's items, each where it is on the page; the items the rule missed, where they were selected
    ...(x.listRule && here ? listMarks(x, row) : []),
    ...(looked ? [{ id: "looked", kind: "looked" as const, cssPath: row.css_path! }] : []),
    ...(here ? savedAnswerMarks(x, row) : []),
    ...(here ? pinnedCommentMarks(x, row) : []),
  ];
  return { hs, fid: looked ? "looked" : value ? "value" : null };
}

function listMarks(x: HighlightInput, row: RowX): Highlight[] {
  return [
    ...(row.items ?? []).flatMap(itemMarks),
    ...Object.entries(x.objFix?.fields ?? {}).map(([f, c]) => expectedAt(`fix-${f}`, c)),
    ...Object.entries(x.objAdd?.fields ?? {}).map(([f, c]) => expectedAt(`obj-${f}`, c)),
    ...(x.objAdd?.pending ? [expectedAt("obj-pending", x.objAdd.pending)] : []),
    ...(row.missing_items ?? []).flatMap((m, i) => (m.expected?.css_path ? [expectedAt(`missing-item-${i}`, m.expected as CapturedSelection)] : [])),
  ];
}

/** An item where it is on the page; an object, each of its fields where it is (sme-fixes §5). */
function itemMarks(it: NonNullable<RowX["items"]>[number]): Highlight[] {
  if (it.fields) {
    return Object.entries(it.fields).filter(([, f]) => f.css_path).map(([f, c]) => ({ id: `item-${it.value_index}-${f}`, kind: "value" as const,
      cssPath: c.css_path!, charStart: c.char_start, charEnd: c.char_end, text: c.text }));
  }
  return it.css_path ? [{ id: `item-${it.value_index}`, kind: "value", cssPath: it.css_path, charStart: it.char_start, charEnd: it.char_end, text: it.value }] : [];
}

/** The saved answer: pieces in it outlined green, pieces marked not in it red dashed. */
function savedAnswerMarks(x: HighlightInput, row: RowX): Highlight[] {
  const exp = row.verdict?.expected;
  if (!exp?.css_path || !(row.state === "wrong" || row.state === "still-wrong") || x.draft) return [];
  return (exp.segments ?? [exp]).map((s, i) => ({ id: `expected-${i}`, kind: "polarity" in s && s.polarity === "out" ? "excluded" as const : "expected" as const,
    cssPath: s.css_path!, charStart: s.char_start, charEnd: s.char_end, text: s.text, badge: i === 0 ? 2 : undefined }));
}

/** Comments pinned to text: a numbered bubble at the text, in the order the row lists them. */
function pinnedCommentMarks(x: HighlightInput, row: RowX): Highlight[] {
  const pinned = [...row.comments.map((c) => c.anchor), ...(x.draft?.anchor ? [x.draft.anchor] : [])];
  return pinned.filter((a): a is NonNullable<typeof a> => !!a?.css_path).map((a, i) => ({ id: `note-${i}`, kind: "note" as const,
    cssPath: a.css_path, charStart: a.char_start, charEnd: a.char_end, text: a.text, badge: i + 1 }));
}

/** Course boxes: a border each, green / red once ✓ / ✗; only the current course is filled (none on a page row). */
function blockMarks(x: HighlightInput, row: RowX, detail: RuleDetail, ov: Overlay): Marks {
  const stateOf = new Map(x.rows.filter((r) => r.page_stem === x.active).map((r) => [r.occurrence_key, r.state]));
  const boxes: Highlight[] = ov.blocks.map((b) => {
    const s = stateOf.get(b.occurrence_key);
    return { id: b.occurrence_key, kind: "block", cssPath: b.css_path, badge: b.n,
             state: s === "correct" ? "ok" : s === "wrong" || s === "still-wrong" ? "bad" : null };
  });
  const marks: Highlight[] = detail.kind === "locator"
    ? ov.marks.map((m, i) => ({ id: `mark${i}`, kind: "mark", cssPath: m.css_path, charStart: m.char_start, charEnd: m.char_end })) : [];
  const fid = x.onPage ? null : detail.kind === "locator" && x.active === row.page_stem ? row.occurrence_key : ov.blocks[0]?.occurrence_key ?? null;
  return { hs: [...boxes, ...marks], fid };
}

function missedCourseMarks(x: HighlightInput): Highlight[] {
  return x.missing.flatMap((m) => {
    const e = m.expected;
    return e?.css_path && m.page_stem === x.active ? [{ id: `missing-${m.annotation_id}`, kind: "expected" as const, cssPath: e.css_path, text: e.text }] : [];
  });
}

function captureMarks(x: HighlightInput): Highlight[] {
  return x.captures.map((c, i) => ({ id: `capture-${i}`, kind: c.polarity === "out" ? "excluded" : "expected", cssPath: c.css_path,
    charStart: c.char_start, charEnd: c.char_end, text: c.text, removable: !!x.draft }));
}

function expectedAt(id: string, c: Pick<CapturedSelection, "css_path" | "char_start" | "char_end" | "text">): Highlight {
  return { id, kind: "expected", cssPath: c.css_path, charStart: c.char_start, charEnd: c.char_end, text: c.text };
}
