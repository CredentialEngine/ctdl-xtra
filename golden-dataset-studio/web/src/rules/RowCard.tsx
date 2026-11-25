// One row of the Rules tab, as a card: the record key (its card on hover says where it came from; no tags under the
// rows, approved item 13), the value box (or a list's items), the record's title,
// the row's links, the history line and the ✓ ✕ comment controls. The Rules tab lists them; an AI run's
// report shows the rows it talks about with the same card (one-rule-runs spec §1.4), so the reader knows which row is
// meant. In the report the card is not selectable and takes no keyboard focus (no `index`).
import type { ReactNode } from "react";
import type { RuleKind } from "../api/types";
import { ReviewLine } from "./AnnotatedBy";
import type { RowX } from "./api";
import { statusWords } from "./claims";
import { isSettled, type Draft, type HistItem } from "./logic";
import { KeyCode } from "./KeyCode";
import { Controls, HistoryLine, Value } from "./parts";

export type Pick3 = "correct" | "wrong" | "comment";

export function RowCard(props: RowCardProps) {
  const p = withDefaults(props);
  const r = p.row;
  const selectable = p.index !== undefined;
  return (
    <div className={rowClass(p)} data-row-index={selectable ? p.index : undefined} tabIndex={selectable ? -1 : undefined}
      onClick={p.onClick} data-testid={selectable ? undefined : "row-card"} data-course={r.record_external_identifier ?? undefined}>
      {p.kind !== "page" && <KeyCode id={r.record_external_identifier} occ={r.occurrence_key} generated={r.key_generated} />}
      <CardBody p={p} />
      <RowControls p={p} />
    </div>
  );
}

interface RowCardProps {
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
}

type CardProps = ReturnType<typeof withDefaults>;

function withDefaults({ draft = null, perPage = false, linked = null, stacked = false, review = true, ...rest }: RowCardProps) {
  return { ...rest, draft, perPage, linked, stacked, review };
}

function rowClass({ row: r, on, draft, kind, perPage }: CardProps): string {
  const settled = isSettled(r.state);
  return `row${on ? " on" : ""}${r.verdict && r.state !== "fixed" ? ` v-${r.verdict.verdict}` : ""}`
    + `${settled && !(on && draft) ? " done" : ""}${kind === "page" ? " page-row" : ""}${perPage ? " in-page" : ""}`;
}

function CardBody({ p }: { p: CardProps }) {
  return (
    <div className="body">
      <RowBody p={p} />
      {p.below}
      {p.review && <ReviewLine r={p.row} />}
      <RowHistory p={p} />
      {p.expansion}
    </div>
  );
}

/** A page row shows its title and address; a list its items; any other row its value box. */
function RowBody({ p }: { p: CardProps }) {
  const r = p.row;
  const linkRow = p.links ? <div className="row-links">{p.links}</div> : null;
  if (p.kind === "page") return <><div className="val">{r.page_title ?? r.page_stem}</div><div className="pg">{r.url.replace(/^https?:\/\//, "")}</div></>;
  if (p.items) return <>{p.items}<div className="pg">{r.context}</div>{linkRow}</>;
  return <><ValueBox row={r} on={p.on} label={p.label} /><div className="pg">{r.context}</div>{linkRow}</>;
}

function ValueBox({ row: r, on, label }: { row: RowX; on: boolean; label: string | null }) {
  const val = statusWords(r.status, r.value);
  return (
    <div className={`valbox${on ? " on" : ""}${r.status === "found" ? "" : " empty"}${r.status === "absent" ? " claim" : ""}`}>
      {on && <span className="valbox-k">{label}</span>}
      {on
        // an open row: the whole value, its paragraphs kept (as the Records tab shows a property)
        ? <div className={`val full${r.status === "found" ? "" : " empty"}`} data-testid="row-full-value">{val}</div>
        : <div className={`val${r.status === "found" ? "" : " empty"}`}><Value text={val} /></div>}
    </div>
  );
}

function RowHistory({ p }: { p: CardProps }) {
  const r = p.row;
  return <HistoryLine state={r.state} verdict={r.verdict} reattached={r.reattached} comments={r.comments} page_questions={r.page_questions}
    linked={p.linked} stacked={p.stacked} lead={p.lead} items={p.history} />;
}

function RowControls({ p }: { p: CardProps }) {
  const r = p.row;
  return <Controls state={r.state} verdict={r.verdict} comments={r.comments} draft={p.draft} onPick={p.onPick} tour={p.tour}
    confirm={p.confirm} marked={p.marked} commentOnly={p.commentOnly} okTitle={p.okTitle} wrongTitle={p.wrongTitle} talkTitle={p.talkTitle} stacked={p.stacked} />;
}
