// One row of the Rules tab, as a card: the course code, the value box (or a list's items), the course title, the
// row's links, the strata chips, the history line and the ✓ ✕ comment controls. The Rules tab lists them; an AI run's
// report shows the rows it talks about with the same card (one-rule-runs spec §1.4), so the reader knows which row is
// meant. In the report the card is not selectable and takes no keyboard focus (no `index`).
import type { ReactNode } from "react";
import type { RuleKind } from "../api/types";
import { StrataTags } from "../shell/Sample";
import { ReviewLine } from "./AnnotatedBy";
import type { RowX } from "./api";
import { statusWords } from "./claims";
import { isSettled, type Draft, type HistItem } from "./logic";
import { Controls, HistoryLine, Value } from "./parts";

export type Pick3 = "correct" | "wrong" | "comment";

export function RowCard({ row: r, kind, label, on, draft = null, perPage = false, items, links, index, onClick, onPick,
  linked = null, stacked = false, lead, history, expansion, below, review = true, tour, confirm, marked, commentOnly,
  okTitle, wrongTitle, talkTitle }: {
  row: RowX; kind: RuleKind;
  /** the value box's legend on an open card ("Description", "Found") */
  label: string | null;
  /** open: the whole value with its legend (the selected row; every card in a report) */
  on: boolean;
  draft?: Draft | null; perPage?: boolean;
  /** a list property's items (ListItems, ProfileItems): shown instead of the value box */
  items?: ReactNode;
  /** the row's link buttons (.xbtn: Open in Records →, Open in Rules →) */
  links?: ReactNode;
  /** its place in the Rules tab's list; without one the card can't be selected or focused (a report) */
  index?: number; onClick?: () => void;
  onPick: (v: Pick3) => void;
  linked?: string | null;
  /** a report: history items one per line, `lead` items first, `history` instead of the row's own */
  stacked?: boolean; lead?: HistItem[]; history?: HistItem[];
  /** under the history line: the ✕ / comment expansion */
  expansion?: ReactNode;
  /** under the links: the page passages a report shows (left out of a value) */
  below?: ReactNode;
  /** the "human-reviewed" line (the Rules tab); a report leaves it to the byline */
  review?: boolean;
  tour?: boolean; confirm?: boolean; marked?: boolean; commentOnly?: boolean; okTitle?: string; wrongTitle?: string;
  talkTitle?: string;
}) {
  const val = statusWords(r.status, r.value);
  const settled = isSettled(r.state);
  const selectable = index !== undefined;
  const cls = `row${on ? " on" : ""}${r.verdict && r.state !== "fixed" ? ` v-${r.verdict.verdict}` : ""}`
    + `${settled && !(on && draft) ? " done" : ""}${kind === "page" ? " page-row" : ""}${perPage ? " in-page" : ""}`;
  const linkRow = links ? <div className="row-links">{links}</div> : null;
  return (
    <div className={cls} data-row-index={selectable ? index : undefined} tabIndex={selectable ? -1 : undefined}
      onClick={onClick} data-testid={selectable ? undefined : "row-card"} data-course={r.course_key ?? undefined}>
      {kind !== "page" && <div className="code">{r.course_key ?? "—"}</div>}
      <div className="body">
        {kind === "page"
          ? <><div className="val">{r.page_title ?? r.page_stem}</div><div className="pg">{r.url.replace(/^https?:\/\//, "")}</div></>
          : items ? <>{items}<div className="pg">{r.context}</div>{linkRow}</>
          : <><div className={`valbox${on ? " on" : ""}${r.status === "found" ? "" : " empty"}${r.status === "absent" ? " claim" : ""}`}>
              {on && <span className="valbox-k">{label}</span>}
              {on
                // an open row: the whole value, its paragraphs kept (as the Records tab shows a property)
                ? <div className={`val full${r.status === "found" ? "" : " empty"}`} data-testid="row-full-value">{val}</div>
                : <div className={`val${r.status === "found" ? "" : " empty"}`}><Value text={val} /></div>}
              </div>
              <div className="pg">{r.context}</div>
              {linkRow}</>}
        {below}
        {review && <ReviewLine r={r} />}
        <StrataTags tags={r.tags} />
        <HistoryLine state={r.state} verdict={r.verdict} reattached={r.reattached} comments={r.comments} page_questions={r.page_questions}
          linked={linked} stacked={stacked} lead={lead} items={history} />
        {expansion}
      </div>
      <Controls state={r.state} verdict={r.verdict} comments={r.comments} draft={draft} onPick={onPick} tour={tour}
        confirm={confirm} marked={marked} commentOnly={commentOnly} okTitle={okTitle} wrongTitle={wrongTitle} talkTitle={talkTitle} stacked={stacked} />
    </div>
  );
}
