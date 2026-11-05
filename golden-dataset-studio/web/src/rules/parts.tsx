// Row pieces shared by the Rules and Records tabs: the three verdict controls, the inline expansion, the history line.
import { useEffect, useRef } from "react";
import type { EventBrief, RowStateName } from "../api/types";
import { Ico } from "../shell/icons";
import { clip, controlOn, historyItems, type Draft } from "./logic";
import { WhyWrong } from "./WhyWrong";

export function Controls({ state, verdict, comments, draft, onPick, tour, confirm, marked, commentOnly }: {
  state: RowStateName | null; verdict: EventBrief | null; comments: EventBrief[]; draft: Draft | null;
  onPick: (v: "correct" | "wrong" | "comment") => void; tour?: boolean;
  /** an engineer-checked value an expert sees: ✓ becomes Confirm (an ordinary ✓ by the expert, Evals spec §6.7) */
  confirm?: boolean;
  /** human-reviewed or engineer-checked: the row's review line names who, so no byline here */
  marked?: boolean;
  /** a list property's row: its items have their own ✓ and ✕, so the row has only the comment button */
  commentOnly?: boolean;
}) {
  const on = draft ? (draft.mode === "wrong" ? "wrong" : null) : controlOn(state);
  const talk = state === "question" ? "inst" : comments.length || draft?.mode === "comment" ? "on" : "";
  const settled = state && state !== "fixed" && state !== "changed-since-correct";
  const by = marked ? null : settled ? verdict?.author : comments[comments.length - 1]?.author;
  const click = (v: "correct" | "wrong" | "comment") => (e: React.MouseEvent) => { e.stopPropagation(); onPick(v); };
  return (
    <div className="ctl3" data-tour={tour ? "row-controls" : undefined}>
      <div className="btns">
        {commentOnly ? null : confirm
          ? <button className="cb confirm" title="Confirm the engineer's check (1): the value becomes human-reviewed" onClick={click("correct")}>
              <Ico name="correct" />Confirm</button>
          : <button className={`cb ok${on === "correct" ? " on" : ""}`} title="Correct (1)" aria-label="Correct" onClick={click("correct")}><Ico name="correct" /></button>}
        {!commentOnly && <button className={`cb no${on === "wrong" ? " on" : ""}`} title="Wrong (2): select the right text on the page" aria-label="Wrong" onClick={click("wrong")}><Ico name="wrong" /></button>}
        <button className={`cb talk ${talk}`} title={state === "question" ? "Question for the institution" : "Comment (3)"} aria-label="Comment"
          data-tour={tour ? "comment-button" : undefined} onClick={click("comment")}><Ico name="bubble" /></button>
      </div>
      {by && <div className="byline">{by}{state === "question" ? " · question for the institution" : ""}</div>}
    </div>
  );
}

export function Expansion({ draft, propertyRule, emptyValue, onChange, onSave, onCancel }: {
  draft: Draft; propertyRule: boolean; emptyValue?: boolean; onChange: (d: Draft) => void; onSave: () => void; onCancel: () => void;
}) {
  const note = useRef<HTMLInputElement>(null);
  useEffect(() => { if (draft.mode === "comment" || draft.anchor) note.current?.focus(); }, [draft.mode, draft.anchor]);
  const stop = (e: React.SyntheticEvent) => e.stopPropagation();
  if (draft.mode === "comment") {
    return (
      <div className="expand comment" onClick={stop}>
        {draft.anchor && <blockquote className="sel-quote sel-anchor" data-testid="anchor">{clip(draft.anchor.text, 160)}</blockquote>}
        <input ref={note} className="note" placeholder="Comment for whoever fixes the rule" value={draft.note}
          onChange={(e) => onChange({ ...draft, note: e.target.value })} />
        <label className="chk-expert">
          <input type="checkbox" checked={draft.question} onChange={(e) => onChange({ ...draft, question: e.target.checked })} />
          <Ico name="inst" /><span><b>Question for the institution</b> · only the college can answer this (send it to them)</span>
        </label>
        <div className="ex-btns">
          <button className="btn primary save" onClick={onSave}>Save comment <kbd className="kb-inv">Enter</kbd></button>
          <button className="btn cancel" onClick={onCancel}>Cancel</button>
        </div>
      </div>
    );
  }
  const pick = propertyRule ? "Select the right text on the page →" : "Optional: select text on the page that shows why →";
  return (
    <div className="expand wrong" onClick={stop}>
      {draft.captures.length
        ? <>{draft.captures.map((c, i) => (
              <div className="sel-piece" key={`${c.css_path}|${c.char_start}`}>
                {c.polarity === "out" && <span className="sel-pol" title="Marked not part of the right answer">✕ not in answer</span>}
                <blockquote className={`sel-quote${c.polarity === "out" ? " out" : ""}`} data-testid="capture">{clip(c.text)}</blockquote>
                <button className="sel-x" title="Remove this piece" aria-label={`Remove piece ${i + 1}`}
                  onClick={() => onChange({ ...draft, captures: draft.captures.filter((_, j) => j !== i) })}>×</button>
              </div>))}
            <div className="faint sel-again">{draft.captures.length > 1
              ? `${draft.captures.length} pieces, joined in page order. `
              : propertyRule ? "The right value, outlined on the page. " : "Outlined on the page. "}
              Drag across more text to add a piece; × removes one.</div></>
        : <div className="pick"><Ico name="highlight" /><span>{pick}</span>
            {propertyRule && emptyValue && <span className="faint">(the rule found nothing here; select the value the page shows)</span>}</div>}
      {propertyRule && <WhyWrong reasons={draft.reasons ?? []} onChange={(reasons) => onChange({ ...draft, reasons })} />}
      {draft.anchor && (
        <div className="sel-piece sel-pin">
          <span className="sel-pol pin" title="Your comment is pinned to this text on the page"><Ico name="bubble" /> comment on</span>
          <blockquote className="sel-quote sel-anchor" data-testid="anchor">{clip(draft.anchor.text, 160)}</blockquote>
          <button className="sel-x" title="Unpin: the comment becomes a note on the row" aria-label="Unpin the comment"
            onClick={() => onChange({ ...draft, anchor: null })}>×</button>
        </div>)}
      <input ref={note} className="note" placeholder={draft.anchor ? "Your comment on that text" : "Note for whoever fixes the rule (optional)"} value={draft.note}
        onChange={(e) => onChange({ ...draft, note: e.target.value })} />
      <div className="ex-btns">
        <button className="btn primary save" onClick={onSave}>Save · wrong <kbd className="kb-inv">Enter</kbd></button>
        <button className="btn cancel" onClick={onCancel}>Cancel</button>
      </div>
    </div>
  );
}

export function HistoryLine({ linked, ...props }: Parameters<typeof historyItems>[0] & { linked?: string | null }) {
  const items = historyItems(props);
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {  // a link to one annotation (?note=): bring it into view
    if (linked) ref.current?.querySelector(".is-linked")?.scrollIntoView?.({ block: "nearest" });
  }, [linked]);
  if (!items.length) return null;
  return (
    <div className="hist" ref={ref}>
      {items.map((h, i) => (
        <span key={i} data-annotation={h.id} title={h.id && h.id === linked ? "The annotation the link points at" : undefined}
          className={`h-${h.cls}${h.cls === "good" ? " good" : h.cls === "bad" ? " bad" : h.cls === "expert" ? " expert-t" : ""}${h.id && h.id === linked ? " is-linked" : ""}`}>
          {i > 0 && <span className="h-sep"> · </span>}
          {h.cls === "expert" && <Ico name="inst" />}
          {h.cls === "comment" && (h.n ? <span className="h-n" title="Pinned to text on the page: the bubble with this number">{h.n}</span>
            : <Ico name="bubble" className="ib" />)}
          {h.author && <b>{h.author}: </b>}{h.text}
          {h.compared && <span className="h-compared"> · {h.compared}</span>}
        </span>
      ))}
    </div>
  );
}

/** A value on two lines with line breaks shown as ↵ (screen 04). */
export function Value({ text }: { text: string }) {
  const parts = text.split(/\s*\n\s*/).filter((p, i, a) => p || i < a.length - 1);
  return <>{parts.map((p, i) => <span key={i}>{i > 0 && <span className="nl">↵</span>}{p}</span>)}</>;
}
