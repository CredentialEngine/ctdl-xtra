// The line above the page pane: a legend while something is being selected on the page (an answer, a missing item, an
// object's field, a missed course or page) or for a locator's boxes; otherwise a banner saying what the page shows.
import type { ReactNode } from "react";
import type { RuleDetail } from "../api/types";
import { Ico } from "../shell/icons";
import { CLASS_NAME } from "../shell/router";
import { classOfRule } from "../shell/klass";
import type { RowX } from "./api";
import { statusHint } from "./claims";
import type { RulesTabState } from "./useRulesTab";

export function paneNotes(t: RulesTabState): { legend: ReactNode; banner: ReactNode } {
  if (!t.detail || !t.row) return { legend: null, banner: null };
  const what = rowWhat(t.detail, t.row, t.kind);
  const legend = workLegend(t, what) ?? kindLegend(t);
  if (legend !== undefined) return { legend, banner: null };
  return { legend: null, banner: rowBanner(t, t.row, what) };
}

/** "Description on ART 101", "Course ART 101", or the rule's title. */
function rowWhat(detail: RuleDetail, row: RowX, kind: RulesTabState["kind"]): ReactNode {
  const key = row.record_external_identifier ?? "";
  if (kind === "property") return <><b>{detail.property_label ?? detail.title}</b>{key ? ` on ${key}` : ""}</>;
  if (kind === "locator") return <><b>{CLASS_NAME[classOfRule(detail.rule_id) ?? "course"]}</b>{key ? ` ${key}` : ""}</>;
  return <b>{detail.title}</b>;
}

function workLegend(t: RulesTabState, what: ReactNode): ReactNode | undefined {
  return (t.listRule ? listLegend(t, what) : undefined) ?? answerLegend(t, what) ?? missedLegend(t);
}

/** A list's row: correcting an object, adding one, or adding a missing item. */
function listLegend({ objFix, objAdd, itemAdd, noun }: RulesTabState, what: ReactNode): ReactNode | undefined {
  if (objFix) return <><Ico name="highlight" /><span><b>Select the right text</b> on the page for the selected {noun} of {what}, then pick its field;
    Enter saves the correction.</span></>;
  if (objAdd) return <><Ico name="highlight" /><span><b>{objAdd.pending ? "Which field is it?" : "Select a piece of the missing one"}</b> on the page for {what}
    {objAdd.pending ? ": pick its field under the row." : ", then label it."}</span></>;
  if (!itemAdd) return undefined;
  return itemAdd.capture
    ? <><Ico name="highlight" /><span><b>Your missing item is outlined.</b> Save it under the row, or Esc to cancel.</span></>
    : <><Ico name="highlight" /><span><b>Select the missing item</b> on the page for {what}: drag across it.</span></>;
}

/** After ✗: where to select the answer, and what the pieces selected so far are. */
function answerLegend({ draft, kind, onRowPage }: RulesTabState, what: ReactNode): ReactNode | undefined {
  if (draft?.mode !== "wrong") return undefined;
  if (kind === "property" && !onRowPage) {
    return <><Ico name="highlight" /><span className="ctx-text"><b>Select the right text</b> for {what} on tab 1, the page this value is from.</span></>;
  }
  const n = draft.captures.length;
  return <><Ico name="highlight" /><span className="ctx-text"><b>{n ? `Your answer is outlined${n > 1 ? ` (${n} pieces)` : ""}` : "Select the right text"}</b> on the page for {what}:
    {n ? " drag across more text to add a piece, × to remove one, Enter to save." : " drag across it (more drags add more pieces). Zoom in (+) to select precisely."}</span></>;
}

function missedLegend({ missed, kind }: RulesTabState): ReactNode | undefined {
  if (missed && kind === "locator") return <>{LOCATOR_LEGEND}<span className="adding">Adding a missed course…</span></>;
  if (missed && kind === "page") return <><Ico name="highlight" /><span><b>Add a missed page</b> · find the page below; it opens here so you can check it.</span></>;
  return undefined;
}

function kindLegend(t: RulesTabState): ReactNode | undefined {
  return t.kind === "locator" ? <>{LOCATOR_LEGEND}<AddMissedButton label="Add a course this rule missed" onClick={t.startMissed} /></> : undefined;
}

function rowBanner(t: RulesTabState, row: RowX, what: ReactNode): ReactNode {
  if (t.kind === "page") {
    return <><span className="gds-num">1</span><span className="grow">{what} — the courses found on this page are outlined.</span>
      <AddMissedButton label="Add a page this rule missed" onClick={t.startMissed} /></>;
  }
  if (t.active !== row.page_stem) return <span className="grow">{what} — another page this course is on. The value is highlighted on tab 1.</span>;
  return <><span className="gds-num">1</span><span className="grow">{what} — {foundWords(t, row)}
    {" "}<span className="answer-hint" data-testid="answer-hint">{answerHint(t, row)}</span></span></>;
}

function foundWords({ listRule }: RulesTabState, row: RowX): string {
  if (listRule) return row.items?.length ? "each item found is highlighted." : "this rule found nothing on this page.";
  return row.status === "found" && row.css_path ? "the value found is highlighted." : statusHint(row.status);
}

function answerHint({ listRule, profile, noun }: RulesTabState, row: RowX): string {
  if (listRule) return profile ? `Wrong part? Click the ${noun}, then select the right text. Missing one? Add it below.`
    : "Wrong item? Use its ✕. Missing one? Add it below.";
  if (row.status === "none") return "Select the value the page shows to mark it.";
  return row.css_path ? "Wrong? Drag across the right text to mark it." : "If the page shows it, drag across it to mark it.";
}

function AddMissedButton({ label, onClick }: { label: string; onClick: () => void }) {
  return <button className="missed-btn" data-tour="add-missed" onClick={onClick}><Ico name="missing" />{label}</button>;
}

const LOCATOR_LEGEND = (
  <span className="legend grow" data-tour="locator-legend">
    <span className="sw-found">1</span>outlined = found by this rule <span className="sep">·</span>{" "}
    <span className="sw-unc">ABC 101</span>marked = looks like a course but wasn't found
  </span>
);
