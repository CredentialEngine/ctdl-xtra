import { useEffect, useRef, useState, type KeyboardEvent, type ReactNode } from "react";
import { cardState } from "../review";
import type { Decision, Flag, Note, NoteScope } from "../types";

export interface DecideExtra {
  reasons: string[];
  expected?: string;
  note?: string;
}

interface Props {
  title: string;
  term?: string | null;
  value: string | null;
  emptyText?: string;
  ruleId?: string | null;
  derived?: boolean;
  decision?: Decision;
  flag?: Flag;
  notes: Note[];
  reasons: string[];
  askExpected: boolean;
  canRuleNote: boolean;
  badges?: ReactNode;
  selected: boolean;
  onSelect: () => void;
  onAccept: () => void;
  onReject: (extra: DecideExtra) => void;
  onClear: () => void;
  onNote: (scope: NoteScope, text: string, id?: string) => void;
  onFlag: (on: boolean, note?: string) => void;
}

const pretty = (reason: string) => reason.replace(/_/g, " ");

export default function ItemCard(props: Props) {
  const { decision, notes } = props;
  const [mode, setMode] = useState<"idle" | "reject" | "comment" | "flag">("idle");
  const [expanded, setExpanded] = useState(false);
  const [chosen, setChosen] = useState<string[]>([]);
  const [expected, setExpected] = useState("");
  const [text, setText] = useState("");
  const [scope, setScope] = useState<NoteScope>("field");
  const firstInput = useRef<HTMLInputElement | HTMLTextAreaElement>(null);
  const state = cardState(decision);

  useEffect(() => {
    if (mode !== "idle") firstInput.current?.focus();
  }, [mode]);

  const close = () => {
    setMode("idle");
    setChosen([]);
    setExpected("");
    setText("");
    setScope("field");
  };

  const openFlag = () => {
    setText(props.flag?.note ?? "");
    setMode("flag");
  };

  const onKeyDown = (e: KeyboardEvent) => {
    const tag = (e.target as HTMLElement).tagName;
    if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") {
      if (e.key === "Escape") close();
      return;
    }
    const key = e.key.toLowerCase();
    if (!["a", "r", "e", "c", "f"].includes(key) || e.metaKey || e.ctrlKey || e.altKey) return;
    e.preventDefault(); // otherwise the letter is typed into the form that opens
    if (key === "a") props.onAccept();
    else if (key === "r" || key === "e") setMode("reject");
    else if (key === "f") openFlag();
    else setMode("comment");
  };

  const submitReject = () => {
    props.onReject({ reasons: chosen, expected: expected.trim() || undefined, note: text.trim() || undefined });
    close();
  };

  const submitFlag = () => {
    props.onFlag(true, text.trim() || undefined);
    close();
  };

  const removeFlag = () => {
    props.onFlag(false);
    close();
  };

  const submitNote = () => {
    if (text.trim()) props.onNote(scope, text.trim());
    close();
  };

  const long = (props.value ?? "").length > 160;

  return (
    <div
      className={`card ${state} ${props.flag ? "flagged" : ""} ${props.selected ? "selected" : ""}`}
      tabIndex={0}
      onKeyDown={onKeyDown}
      onFocus={props.onSelect}
      onClick={props.onSelect}
    >
      <div className="card-head">
        <span className="card-title">{props.title}</span>
        {props.term && <code className="term">{props.term}</code>}
      </div>

      <div
        className={`value ${props.value == null ? "empty" : ""} ${long && !expanded ? "clamped" : ""}`}
        onClick={() => long && setExpanded(!expanded)}
        title={long ? "click to expand" : undefined}
      >
        {props.value ?? props.emptyText ?? "not found"}
      </div>

      <div className="meta">
        {props.ruleId ? <code className="chip">{props.ruleId}</code> : <span className="chip none">no rule</span>}
        {props.derived && <span className="chip derived">derived</span>}
        {props.badges}
        {props.flag && (
          <span className="chip flag">
            ⚑ flagged · {props.flag.author}
            {props.flag.carried_from ? " · carried over" : ""}
          </span>
        )}
        {decision && (
          <span className={`chip status ${state}`}>
            {decision.status === "accepted" ? "accepted" : "rejected"} · {decision.author}
            {decision.carried_from ? " · carried over" : ""}
          </span>
        )}
      </div>

      {props.flag?.note && <div className="flag-note">⚑ {props.flag.note}</div>}

      {decision?.status !== "accepted" && decision && (
        <div className="decision-detail">
          {decision.reasons.length > 0 && <span>{decision.reasons.map(pretty).join(", ")}</span>}
          {decision.expected_value && <span>expected: <q>{decision.expected_value}</q></span>}
        </div>
      )}

      {notes.map((n) => (
        <div className="note" key={n.id}>
          <span className="note-scope">{n.scope}</span> {n.text} <em>({n.author})</em>
          <button className="link" tabIndex={-1} onClick={() => props.onNote(n.scope, "", n.id)}>remove</button>
        </div>
      ))}

      <div className="actions">
        <button tabIndex={-1} className="act accept" title="Accept (A)" onClick={props.onAccept}>✓ Accept</button>
        <button tabIndex={-1} className="act reject" title="Reject (R)" onClick={() => setMode("reject")}>✕ Reject</button>
        <button tabIndex={-1} className="act" title="Comment (C)" onClick={() => setMode("comment")}>💬 Note</button>
        <button
          tabIndex={-1}
          className={`act flag-btn ${props.flag ? "on" : ""}`}
          title="Flag for review (F)"
          onClick={openFlag}
        >
          ⚑ {props.flag ? "Flagged" : "Flag"}
        </button>
        {decision && (
          <button tabIndex={-1} className="act subtle" onClick={props.onClear}>undo</button>
        )}
      </div>

      {mode === "reject" && (
        <div className="form" onClick={(e) => e.stopPropagation()}>
          <div className="chips">
            {props.reasons.map((r) => (
              <button
                key={r}
                tabIndex={-1}
                className={`chip pick ${chosen.includes(r) ? "on" : ""}`}
                onClick={() => setChosen(chosen.includes(r) ? chosen.filter((x) => x !== r) : [...chosen, r])}
              >
                {pretty(r)}
              </button>
            ))}
          </div>
          {props.askExpected && (
            <input
              ref={firstInput as React.RefObject<HTMLInputElement>}
              placeholder="What should the value be? (leave empty if it should be absent)"
              value={expected}
              onChange={(e) => setExpected(e.target.value)}
            />
          )}
          <textarea
            ref={props.askExpected ? undefined : (firstInput as React.RefObject<HTMLTextAreaElement>)}
            placeholder="Why is this wrong? (optional note)"
            value={text}
            onChange={(e) => setText(e.target.value)}
          />
          <div className="form-actions">
            <button className="primary" onClick={submitReject}>Save rejection</button>
            <button onClick={close}>Cancel</button>
          </div>
        </div>
      )}

      {mode === "flag" && (
        <div className="form" onClick={(e) => e.stopPropagation()}>
          <p className="hint">
            Mark this for a subject matter expert. It stays undecided until you accept or
            reject it.
          </p>
          <textarea
            ref={firstInput as React.RefObject<HTMLTextAreaElement>}
            placeholder="What are you unsure about? (optional)"
            value={text}
            onChange={(e) => setText(e.target.value)}
          />
          <div className="form-actions">
            <button className="primary flag-save" onClick={submitFlag}>
              ⚑ {props.flag ? "Update flag" : "Flag for review"}
            </button>
            {props.flag && <button onClick={removeFlag}>Remove flag</button>}
            <button onClick={close}>Cancel</button>
          </div>
        </div>
      )}

      {mode === "comment" && (
        <div className="form" onClick={(e) => e.stopPropagation()}>
          <select value={scope} onChange={(e) => setScope(e.target.value as NoteScope)}>
            <option value="field">This value, on this page</option>
            {props.canRuleNote && <option value="rule">The rule that found it (all pages)</option>}
            <option value="property">This property in general (all pages)</option>
          </select>
          <textarea
            ref={firstInput as React.RefObject<HTMLTextAreaElement>}
            placeholder="Note"
            value={text}
            onChange={(e) => setText(e.target.value)}
          />
          <div className="form-actions">
            <button className="primary" onClick={submitNote}>Save note</button>
            <button onClick={close}>Cancel</button>
          </div>
        </div>
      )}
    </div>
  );
}
