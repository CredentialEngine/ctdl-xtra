import { useState } from "react";
import type { Actions } from "../actions";
import { fieldNotes } from "../review";
import type { Decision, Flag, LabelView, Note } from "../types";
import ItemCard from "./ItemCard";

interface Props {
  stem: string;
  pageUrl: string;
  labels: LabelView[];
  vocabulary: string[];
  decisions: Record<string, Decision>;
  flags: Record<string, Flag>;
  notes: Note[];
  reasons: string[];
  selectedKey: string | null;
  onSelect: (key: string) => void;
  actions: Actions;
}

export default function LabelSection(p: Props) {
  const [adding, setAdding] = useState(false);
  const [choice, setChoice] = useState("");
  const [note, setNote] = useState("");
  const added = Object.values(p.decisions).filter(
    (d) => d.kind === "label" && d.status === "missing" && d.source_url === p.pageUrl,
  );

  return (
    <section className="record labels">
      <header className="record-head">
        <strong>Labels</strong>
        <span className="muted">which CTDL classes this page describes</span>
      </header>
      {p.labels.length === 0 && added.length === 0 && (
        <div className="card empty-card">No label applies to this page. Reject nothing if that is right.</div>
      )}
      {p.labels.map((l) => {
        const ref = {
          kind: "label" as const,
          key: l.key,
          canonical_label: l.label,
          source_url: p.pageUrl,
          rule_id: l.rule_id,
          value: l.label,
        };
        return (
          <ItemCard
            key={l.key}
            title={l.label}
            value={`This page is a ${l.label}`}
            ruleId={l.rule_id}
            decision={p.decisions[l.key]}
            flag={p.flags[l.key]}
            onFlag={(on, note) =>
              p.actions.flag(
                {
                  scope: "label",
                  key: l.key,
                  stem: p.stem,
                  source_url: p.pageUrl,
                  canonical_label: l.label,
                },
                on,
                note,
              )
            }
            notes={fieldNotes(p.notes, l.key)}
            reasons={p.reasons}
            askExpected={false}
            canRuleNote
            selected={p.selectedKey === l.key}
            onSelect={() => p.onSelect(l.key)}
            onAccept={() => p.actions.decide(ref, "accepted")}
            onReject={(extra) => p.actions.decide(ref, "rejected", extra)}
            onClear={() => p.actions.decide(ref, "pending")}
            onNote={(scope, text, id) =>
              p.actions.note(scope, scope === "field" ? l.key : scope === "rule" ? l.rule_id : l.label, text, id)
            }
          />
        );
      })}
      {added.map((d) => (
        <div className="card added" key={d.key}>
          <div className="card-head">
            <span className="card-title">{d.expected_value}</span>
            <span className="chip derived">added by reviewer</span>
          </div>
          <div className="actions">
            <button
              className="act subtle"
              onClick={() =>
                p.actions.decide(
                  { kind: "label", key: d.key, canonical_label: d.canonical_label, source_url: d.source_url, value: null },
                  "pending",
                )
              }
            >
              remove
            </button>
          </div>
        </div>
      ))}
      {adding ? (
        <div className="form add">
          <select value={choice} onChange={(e) => setChoice(e.target.value)}>
            <option value="">Choose the missing label…</option>
            {p.vocabulary.map((v) => (
              <option key={v}>{v}</option>
            ))}
          </select>
          <textarea placeholder="Why does it apply? (optional note)" value={note} onChange={(e) => setNote(e.target.value)} />
          <div className="form-actions">
            <button
              className="primary"
              disabled={!choice}
              onClick={() => {
                p.actions.addLabel(p.pageUrl, choice, note.trim() || undefined);
                setAdding(false);
                setChoice("");
                setNote("");
              }}
            >
              Add label
            </button>
            <button onClick={() => setAdding(false)}>Cancel</button>
          </div>
        </div>
      ) : (
        <button className="add-btn" onClick={() => setAdding(true)}>+ Add missing label</button>
      )}
    </section>
  );
}
