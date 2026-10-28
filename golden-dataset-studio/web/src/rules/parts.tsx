// Row pieces shared by the Rules and Records tabs: the three verdict controls, the inline expansion, the history line.
import { useEffect, useRef } from "react";
import type { EventBrief, RowStateName } from "../api/types";
import { Ico } from "../shell/icons";
import { clip, controlOn, historyItems, type Draft } from "./logic";

export function Controls({ state, verdict, comments, draft, onPick, tour, confirm, marked }: {
  state: RowStateName | null; verdict: EventBrief | null; comments: EventBrief[]; draft: Draft | null;
  onPick: (v: "correct" | "wrong" | "comment") => void; tour?: boolean;
  /** an engineer-checked value an expert sees: ✓ becomes Confirm (an ordinary ✓ by the expert, Evals spec §6.7) */
  confirm?: boolean;
  /** human-reviewed or engineer-checked: the row's review line names who, so no byline here */
  marked?: boolean;
}) {
  const on = draft ? (draft.mode === "wrong" ? "wrong" : null) : controlOn(state);
  const talk = state === "question" ? "inst" : comments.length || draft?.mode === "comment" ? "on" : "";
  const settled = state && state !== "fixed" && state !== "changed-since-correct";
  const by = marked ? null : settled ? verdict?.author : comments[comments.length - 1]?.author;
  const click = (v: "correct" | "wrong" | "comment") => (e: React.MouseEvent) => { e.stopPropagation(); onPick(v); };
  return (
    <div className="ctl3" data-tour={tour ? "row-controls" : undefined}>
      <div className="btns">
        {confirm
          ? <button className="cb confirm" title="Confirm the engineer's check (1): the value becomes human-reviewed" onClick={click("correct")}>
              <Ico name="correct" />Confirm</button>
          : <button className={`cb ok${on === "correct" ? " on" : ""}`} title="Correct (1)" aria-label="Correct" onClick={click("correct")}><Ico name="correct" /></button>}
        <button className={`cb no${on === "wrong" ? " on" : ""}`} title="Wrong (2): select the right text on the page" aria-label="Wrong" onClick={click("wrong")}><Ico name="wrong" /></button>
        <button className={`cb talk ${talk}`} title={state === "question" ? "Question for the institution" : "Comment (3)"} aria-label="Comment"
          data-tour={tour ? "comment-button" : undefined} onClick={click("comment")}><Ico name="bubble" /></button>
      </div>
      {by && <div className="byline">{by}{state === "question" ? " · question for the institution" : ""}</div>}
    </div>
  );
}

export function Expansion({ draft, fieldRule, emptyValue, onChange, onSave, onCancel }: {
  draft: Draft; fieldRule: boolean; emptyValue?: boolean; onChange: (d: Draft) => void; onSave: () => void; onCancel: () => void;
}) {
  const note = useRef<HTMLInputElement>(null);
  useEffect(() => { if (draft.mode === "comment") note.current?.focus(); }, [draft.mode]);
  const stop = (e: React.SyntheticEvent) => e.stopPropagation();
  if (draft.mode === "comment") {
    return (
      <div className="expand comment" onClick={stop}>
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
  const pick = fieldRule ? "Select the right text on the page →" : "Optional: select text on the page that shows why →";
  return (
    <div className="expand wrong" onClick={stop}>
      {draft.captures.length
        ? <>{draft.captures.map((c, i) => (
              <div className="sel-piece" key={`${c.css_path}|${c.char_start}`}>
                <blockquote className="sel-quote" data-testid="capture">{clip(c.text)}</blockquote>
                <button className="sel-x" title="Remove this piece" aria-label={`Remove piece ${i + 1}`}
                  onClick={() => onChange({ ...draft, captures: draft.captures.filter((_, j) => j !== i) })}>×</button>
              </div>))}
            <div className="faint sel-again">{draft.captures.length > 1
              ? `${draft.captures.length} pieces, joined in page order. `
              : fieldRule ? "The right value, outlined on the page. " : "Outlined on the page. "}
              Drag across more text to add a piece; × removes one.</div></>
        : <div className="pick"><Ico name="highlight" /><span>{pick}</span>
            {fieldRule && emptyValue && <span className="faint">(the rule found nothing here; select the value the page shows)</span>}</div>}
      <input ref={note} className="note" placeholder="Note for whoever fixes the rule (optional)" value={draft.note}
        onChange={(e) => onChange({ ...draft, note: e.target.value })} />
      <div className="ex-btns">
        <button className="btn primary save" onClick={onSave}>Save · wrong <kbd className="kb-inv">Enter</kbd></button>
        <button className="btn cancel" onClick={onCancel}>Cancel</button>
      </div>
    </div>
  );
}

export function HistoryLine(props: Parameters<typeof historyItems>[0]) {
  const items = historyItems(props);
  if (!items.length) return null;
  return (
    <div className="hist">
      {items.map((h, i) => (
        <span key={i} className={`h-${h.cls}${h.cls === "good" ? " good" : h.cls === "bad" ? " bad" : h.cls === "expert" ? " expert-t" : ""}`}>
          {i > 0 && <span className="h-sep"> · </span>}
          {h.cls === "expert" && <Ico name="inst" />}
          {h.cls === "comment" && <Ico name="bubble" className="ib" />}
          {h.author && <b>{h.author}: </b>}{h.text}
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
