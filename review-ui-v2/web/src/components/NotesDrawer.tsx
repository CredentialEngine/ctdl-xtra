import { useState } from "react";
import type { Flag, Note } from "../types";

interface Props {
  notes: Note[];
  flags: Flag[];
  onSave: (text: string, id?: string) => void;
  onClose: () => void;
}

/** Field notes are keyed by an internal id; show "GEOG222 · Credit Value" instead. */
export function describeTarget(note: Note): string {
  if (note.scope !== "field" || !note.target) return note.target ?? "";
  const parts = note.target.split("::");
  return parts[0] === "label" ? `label · ${parts[2]}` : `${parts[0]} · ${parts[1]}`;
}

export default function NotesDrawer({ notes, flags, onSave, onClose }: Props) {
  const [text, setText] = useState("");
  const general = notes.filter((n) => n.scope === "general");
  const scoped = notes.filter((n) => n.scope !== "general");

  return (
    <aside className="drawer" aria-label="Notes">
      <div className="drawer-head">
        <strong>Notes for Claude</strong>
        <button onClick={onClose}>Close</button>
      </div>
      <p className="hint">
        General notes about the session or the catalog. Notes on a specific value, rule or
        property are written on the cards and listed below.
      </p>
      <textarea placeholder="Add a general note…" value={text} onChange={(e) => setText(e.target.value)} />
      <button
        className="primary"
        disabled={!text.trim()}
        onClick={() => {
          onSave(text.trim());
          setText("");
        }}
      >
        Add note
      </button>
      <h4>General ({general.length})</h4>
      {general.map((n) => (
        <div className="note" key={n.id}>
          {n.text} <em>({n.author})</em>
          <button className="link" onClick={() => onSave("", n.id)}>remove</button>
        </div>
      ))}
      <h4>⚑ Flagged for review ({flags.length})</h4>
      {flags.map((f) => (
        <div className="note flagged-note" key={f.target}>
          <span className="note-scope">{f.scope}</span>{" "}
          <code>{f.scope === "page" ? f.stem : `${f.record_id ?? "label"} · ${f.canonical_label ?? ""}`}</code>
          <div>{f.note || "(no note)"} <em>({f.author})</em></div>
        </div>
      ))}
      <h4>On specific values, rules and properties ({scoped.length})</h4>
      {scoped.map((n) => (
        <div className="note" key={n.id}>
          <span className="note-scope">{n.scope}</span> <code>{describeTarget(n)}</code>
          <div>{n.text} <em>({n.author})</em></div>
        </div>
      ))}
    </aside>
  );
}
