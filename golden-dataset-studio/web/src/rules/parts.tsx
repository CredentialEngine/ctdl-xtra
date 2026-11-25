// Row pieces shared by the Rules and Records tabs: the three verdict controls, the inline expansion, the history line.
import { useEffect, useRef, type RefObject } from "react";
import type { EventBrief, RowStateName } from "../api/types";
import { Ico } from "../shell/icons";
import { ago, clip, controlOn, fullTime, historyItems, monthDay, type Draft, type HistItem } from "./logic";
import { WhyWrong } from "./WhyWrong";

export function Controls(p: ControlsProps) {
  const by = bylineAuthor(p);
  return (
    <div className="ctl3" data-tour={p.tour ? "row-controls" : undefined}>
      <div className="btns">
        {p.commentOnly ? null : <CorrectButton p={p} />}
        {!p.commentOnly && <button className={`cb no${litControl(p) === "wrong" ? " on" : ""}`} title={p.wrongTitle ?? "Wrong (2): select the right text on the page"} aria-label="Wrong" onClick={picking(p, "wrong")}><Ico name="wrong" /></button>}
        <TalkButton p={p} />
      </div>
      {by && <div className="byline">{by}{p.state === "question" ? (p.stacked ? ", question for the institution" : " · question for the institution") : ""}</div>}
    </div>
  );
}

export function Expansion(p: ExpansionProps) {
  const note = useFocusedNote(p.draft);
  if (p.draft.mode === "comment") return <CommentExpansion draft={p.draft} note={note} onChange={p.onChange} onSave={p.onSave} onCancel={p.onCancel} />;
  return <WrongExpansion {...p} note={note} />;
}

function WrongExpansion({ draft, propertyRule, emptyValue, onChange, onSave, onCancel, note }: ExpansionProps & { note: RefObject<HTMLInputElement> }) {
  return (
    <div className="expand wrong" onClick={stopEvent}>
      {draft.captures.length
        ? <CapturedPieces draft={draft} propertyRule={propertyRule} onChange={onChange} />
        : <PickPrompt propertyRule={propertyRule} emptyValue={emptyValue} />}
      {propertyRule && <WhyWrong reasons={draft.reasons ?? []} onChange={(reasons) => onChange({ ...draft, reasons })} />}
      {draft.anchor && <PinnedAnchor draft={draft} anchor={draft.anchor} onChange={onChange} />}
      <NoteInput note={note} draft={draft} onChange={onChange}
        placeholder={draft.anchor ? "Your comment on that text" : "Note for whoever fixes the rule (optional)"} />
      <SaveButtons label="Save · wrong" onSave={onSave} onCancel={onCancel} />
    </div>
  );
}

/** The history line under a row. `stacked` (an AI run's report): one item per line, no " · " between them; `lead`:
 * items shown first (the report's "In v9: …"). */
export function HistoryLine({ linked, stacked, lead, items: given, ...props }: HistoryLineProps) {
  const items = [...(lead ?? []), ...(given ?? historyItems(props))];
  const ref = useRef<HTMLDivElement>(null);
  useScrollToLinked(ref, linked);
  if (!items.length) return null;
  return (
    <div className={`hist${stacked ? " stacked" : ""}`} ref={ref}>
      {items.map((h, i) => <HistoryItem key={i} h={h} first={i === 0} linked={linked} stacked={stacked} />)}
    </div>
  );
}

/** A time as people say it ("12 minutes ago"), the full date and time zone in its tooltip ("Nov 5, 2026, 6:28 PM MST"). */
export function When({ at, now }: { at: string; now?: number }) {
  return <time dateTime={at} title={fullTime(at)}>{ago(at, now)}</time>;
}

/** A value on two lines with line breaks shown as ↵ (screen 04). */
export function Value({ text }: { text: string }) {
  const parts = text.split(/\s*\n\s*/).filter((p, i, a) => p || i < a.length - 1);
  return <>{parts.map((p, i) => <span key={i}>{i > 0 && <span className="nl">↵</span>}{p}</span>)}</>;
}

type Pick3 = "correct" | "wrong" | "comment";

interface ControlsProps {
  state: RowStateName | null; verdict: EventBrief | null; comments: EventBrief[]; draft: Draft | null;
  onPick: (v: Pick3) => void; tour?: boolean;
  /** an engineer-checked value an expert sees: ✓ becomes Confirm (an ordinary ✓ by the expert, Evals spec §6.7) */
  confirm?: boolean;
  /** human-reviewed or engineer-checked: the row's review line names who, so no byline here */
  marked?: boolean;
  /** a list property's row: its items have their own ✓ and ✕, so the row has only the comment button */
  commentOnly?: boolean;
  /** the ✓ and ✕ tooltips when they do something else (an AI run's report: ✓ saves an inferred value, ✕ opens a new tab) */
  okTitle?: string; wrongTitle?: string; talkTitle?: string;
  /** an AI run's report: no " · " in the byline */
  stacked?: boolean;
}

interface ExpansionProps {
  draft: Draft; propertyRule: boolean; emptyValue?: boolean; onChange: (d: Draft) => void; onSave: () => void; onCancel: () => void;
}

type HistoryLineProps = Parameters<typeof historyItems>[0] & {
  linked?: string | null; stacked?: boolean; lead?: HistItem[];
  /** the items to show instead of the row's (a report row's history, reportHistory) */ items?: HistItem[];
};

/** Which control is lit: a draft's ✕ while one is open, else the row's state. */
function litControl({ draft, state }: ControlsProps) {
  return draft ? (draft.mode === "wrong" ? "wrong" : null) : controlOn(state);
}

/** Who the byline names: the verdict's author once settled, else the last commenter; nobody when the review line does. */
function bylineAuthor({ marked, state, verdict, comments }: ControlsProps) {
  const settled = state && state !== "fixed" && state !== "changed-since-correct";
  return marked ? null : settled ? verdict?.author : comments[comments.length - 1]?.author;
}

function CorrectButton({ p }: { p: ControlsProps }) {
  if (p.confirm) {
    return <button className="cb confirm" title="Confirm the engineer's check (1): the value becomes human-reviewed" onClick={picking(p, "correct")}>
      <Ico name="correct" />Confirm</button>;
  }
  return <button className={`cb ok${litControl(p) === "correct" ? " on" : ""}`} title={p.okTitle ?? "Correct (1)"} aria-label="Correct" onClick={picking(p, "correct")}><Ico name="correct" /></button>;
}

function TalkButton({ p }: { p: ControlsProps }) {
  const talk = p.state === "question" ? "inst" : p.comments.length || p.draft?.mode === "comment" ? "on" : "";
  return (
    <button className={`cb talk ${talk}`} title={p.state === "question" ? "Question for the institution" : p.talkTitle ?? "Comment (3)"} aria-label="Comment"
      data-tour={p.tour ? "comment-button" : undefined} onClick={picking(p, "comment")}><Ico name="bubble" /></button>
  );
}

const picking = (p: ControlsProps, v: Pick3) => (e: React.MouseEvent) => { e.stopPropagation(); p.onPick(v); };

function useFocusedNote(draft: Draft): RefObject<HTMLInputElement> {
  const note = useRef<HTMLInputElement>(null);
  useEffect(() => { if (draft.mode === "comment" || draft.anchor) note.current?.focus(); }, [draft.mode, draft.anchor]);
  return note;
}

function CommentExpansion({ draft, note, onChange, onSave, onCancel }: {
  draft: Draft; note: RefObject<HTMLInputElement>; onChange: (d: Draft) => void; onSave: () => void; onCancel: () => void;
}) {
  return (
    <div className="expand comment" onClick={stopEvent}>
      {draft.anchor && <blockquote className="sel-quote sel-anchor" data-testid="anchor">{clip(draft.anchor.text, 160)}</blockquote>}
      <NoteInput note={note} draft={draft} onChange={onChange} placeholder="Comment for whoever fixes the rule" />
      <label className="chk-expert">
        <input type="checkbox" checked={draft.question} onChange={(e) => onChange({ ...draft, question: e.target.checked })} />
        <Ico name="inst" /><span><b>Question for the institution</b> · only the college can answer this (send it to them)</span>
      </label>
      <SaveButtons label="Save comment" onSave={onSave} onCancel={onCancel} />
    </div>
  );
}

function NoteInput({ note, draft, placeholder, onChange }: {
  note: RefObject<HTMLInputElement>; draft: Draft; placeholder: string; onChange: (d: Draft) => void;
}) {
  return <input ref={note} className="note" placeholder={placeholder} value={draft.note} onChange={(e) => onChange({ ...draft, note: e.target.value })} />;
}

function CapturedPieces({ draft, propertyRule, onChange }: { draft: Draft; propertyRule: boolean; onChange: (d: Draft) => void }) {
  const remove = (i: number) => onChange({ ...draft, captures: draft.captures.filter((_, j) => j !== i) });
  return (<>
    {draft.captures.map((c, i) => <CapturedPiece key={`${c.css_path}|${c.char_start}`} piece={c} n={i + 1} onRemove={() => remove(i)} />)}
    <div className="faint sel-again">{draft.captures.length > 1
      ? `${draft.captures.length} pieces, joined in page order. `
      : propertyRule ? "The right value, outlined on the page. " : "Outlined on the page. "}
      Drag across more text to add a piece; × removes one.</div>
  </>);
}

function CapturedPiece({ piece, n, onRemove }: { piece: Draft["captures"][number]; n: number; onRemove: () => void }) {
  return (
    <div className="sel-piece">
      {piece.polarity === "out" && <span className="sel-pol" title="Marked not part of the right answer">✕ not in answer</span>}
      <blockquote className={`sel-quote${piece.polarity === "out" ? " out" : ""}`} data-testid="capture">{clip(piece.text)}</blockquote>
      <button className="sel-x" title="Remove this piece" aria-label={`Remove piece ${n}`} onClick={onRemove}>×</button>
    </div>
  );
}

function PickPrompt({ propertyRule, emptyValue }: { propertyRule: boolean; emptyValue?: boolean }) {
  const pick = propertyRule ? "Select the right text on the page →" : "Optional: select text on the page that shows why →";
  return (
    <div className="pick"><Ico name="highlight" /><span>{pick}</span>
      {propertyRule && emptyValue && <span className="faint">(the rule found nothing here; select the value the page shows)</span>}</div>
  );
}

function PinnedAnchor({ draft, anchor, onChange }: { draft: Draft; anchor: NonNullable<Draft["anchor"]>; onChange: (d: Draft) => void }) {
  return (
    <div className="sel-piece sel-pin">
      <span className="sel-pol pin" title="Your comment is pinned to this text on the page"><Ico name="bubble" /> comment on</span>
      <blockquote className="sel-quote sel-anchor" data-testid="anchor">{clip(anchor.text, 160)}</blockquote>
      <button className="sel-x" title="Unpin: the comment becomes a note on the row" aria-label="Unpin the comment"
        onClick={() => onChange({ ...draft, anchor: null })}>×</button>
    </div>
  );
}

function SaveButtons({ label, onSave, onCancel }: { label: string; onSave: () => void; onCancel: () => void }) {
  return (
    <div className="ex-btns">
      <button className="btn primary save" onClick={onSave}>{label} <kbd className="kb-inv">Enter</kbd></button>
      <button className="btn cancel" onClick={onCancel}>Cancel</button>
    </div>
  );
}

const stopEvent = (e: React.SyntheticEvent) => e.stopPropagation();

/** A link to one annotation (?note=): bring it into view. */
function useScrollToLinked(ref: RefObject<HTMLDivElement>, linked: string | null | undefined): void {
  useEffect(() => {
    if (linked) ref.current?.querySelector(".is-linked")?.scrollIntoView?.({ block: "nearest" });
  }, [ref, linked]);
}

function HistoryItem({ h, first, linked, stacked }: { h: HistItem; first: boolean; linked?: string | null; stacked?: boolean }) {
  const isLinked = !!h.id && h.id === linked;
  return (
    <span data-annotation={h.id} title={isLinked ? "The annotation the link points at" : undefined} className={historyClass(h, isLinked)}>
      {!first && !stacked && <span className="h-sep"> · </span>}
      {h.cls === "expert" && <Ico name="inst" />}
      {h.cls === "comment" && (h.n ? <span className="h-n" title="Pinned to text on the page: the bubble with this number">{h.n}</span>
        : <Ico name="bubble" className="ib" />)}
      <HistoryAuthor h={h} />{h.text}
      {h.when && <>{" "}<When at={h.when} />{h.after}</>}
      {h.compared && (stacked ? <span className="h-compared"> ({h.compared})</span> : <span className="h-compared"> · {h.compared}</span>)}
    </span>
  );
}

function historyClass(h: HistItem, isLinked: boolean): string {
  return `h-${h.cls}${h.cls === "good" ? " good" : h.cls === "bad" ? " bad" : h.cls === "expert" ? " expert-t" : ""}${isLinked ? " is-linked" : ""}`;
}

/** "Jared Diener: ", or Claude's "(v10, AI run Nov 6): " with the run linked. */
function HistoryAuthor({ h }: { h: HistItem }) {
  if (!h.run) return <>{h.author && <b>{h.author}: </b>}</>;
  return <><b>{h.author}</b> <span className="faint">({h.run.version != null ? `v${h.run.version}, ` : ""}<a href={runHref(h.run.id)}
    onClick={(e) => e.stopPropagation()} title="The AI run's report">AI run {monthDay(h.run.at)}</a>)</span><b>: </b></>;
}

/** A link to an AI run's report from where the reader is (App opens `?run=`). */
const runHref = (id: string) => `#${(location.hash.replace(/^#/, "") || "/").split("?")[0]}?run=${encodeURIComponent(id)}`;
