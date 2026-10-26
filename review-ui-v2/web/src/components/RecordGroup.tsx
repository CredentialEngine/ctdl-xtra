import { useState } from "react";
import type { Actions } from "../actions";
import { fieldNotes } from "../review";
import type { Decision, Flag, Note, RecordView, TemplateProperty } from "../types";
import ItemCard from "./ItemCard";

interface Props {
  stem: string;
  record: RecordView;
  pageUrl: string;
  decisions: Record<string, Decision>;
  flags: Record<string, Flag>;
  notes: Note[];
  properties: TemplateProperty[];
  reasons: string[];
  selectedKey: string | null;
  onSelect: (key: string, path: string | null) => void;
  actions: Actions;
}

export default function RecordGroup(p: Props) {
  const [open, setOpen] = useState(true);
  const [adding, setAdding] = useState(false);
  const [prop, setProp] = useState("");
  const [value, setValue] = useState("");
  const [note, setNote] = useState("");
  // Flagged values are questions for an expert, so "accept remaining" leaves them alone.
  const pending = p.record.fields.filter((f) => !p.decisions[f.field_id] && !p.flags[f.field_id]);
  const added = Object.values(p.decisions).filter(
    (d) => d.status === "missing" && d.record_id === p.record.record_id && d.source_url === p.pageUrl,
  );

  const submitAdd = () => {
    if (!prop || !value.trim()) return;
    p.actions.addMissing(p.record.record_id, prop, p.pageUrl, value.trim(), note.trim() || undefined);
    setAdding(false);
    setProp("");
    setValue("");
    setNote("");
  };

  return (
    <section className="record">
      <header className="record-head">
        <button className="link big" onClick={() => setOpen(!open)} aria-expanded={open}>
          {open ? "▾" : "▸"} {p.record.record_id}
        </button>
        <span className="muted">
          {p.record.fields.length} values · seen on {p.record.source_urls.length} page
          {p.record.source_urls.length === 1 ? "" : "s"}
        </span>
        {pending.length > 0 && (
          <button
            className="act accept small"
            onClick={() =>
              pending.forEach((f) =>
                p.actions.decide(
                  {
                    kind: "field",
                    key: f.field_id,
                    canonical_label: f.canonical_label,
                    source_url: f.source_url,
                    record_id: p.record.record_id,
                    rule_id: f.rule_id,
                    value: f.value,
                  },
                  "accepted",
                ),
              )
            }
          >
            ✓ Accept remaining ({pending.length})
          </button>
        )}
      </header>

      {open && (
        <>
          {p.record.conflicts.map((c) => (
            <div className="conflict" key={c.canonical_label}>
              <strong>{c.canonical_label}</strong> differs between pages:{" "}
              {c.values.map((v) => (
                <span key={v.value}>
                  <q>{v.value}</q> ({v.source_urls.length}){" "}
                </span>
              ))}
            </div>
          ))}
          {p.record.fields.map((f) => (
            <ItemCard
              key={f.field_id}
              title={f.canonical_label}
              term={f.ctdl_property}
              value={f.value}
              emptyText="— not found on the page —"
              ruleId={f.rule_id}
              derived={f.rule_type === "constant" || f.rule_type === "source_url"}
              decision={p.decisions[f.field_id]}
              flag={p.flags[f.field_id]}
              onFlag={(on, note) =>
                p.actions.flag(
                  {
                    scope: "field",
                    key: f.field_id,
                    stem: p.stem,
                    source_url: f.source_url,
                    canonical_label: f.canonical_label,
                    record_id: p.record.record_id,
                  },
                  on,
                  note,
                )
              }
              notes={fieldNotes(p.notes, f.field_id)}
              reasons={p.reasons}
              askExpected
              canRuleNote={!!f.rule_id}
              selected={p.selectedKey === f.field_id}
              onSelect={() => p.onSelect(f.field_id, f.location?.css_path ?? null)}
              onAccept={() =>
                p.actions.decide(refOf(p.record.record_id, f), "accepted")
              }
              onReject={(extra) => p.actions.decide(refOf(p.record.record_id, f), "rejected", extra)}
              onClear={() => p.actions.decide(refOf(p.record.record_id, f), "pending")}
              onNote={(scope, text, id) =>
                p.actions.note(
                  scope,
                  scope === "field" ? f.field_id : scope === "rule" ? f.rule_id! : f.canonical_label,
                  text,
                  id,
                )
              }
            />
          ))}
          {added.map((d) => (
            <div className="card added" key={d.key}>
              <div className="card-head">
                <span className="card-title">{d.canonical_label}</span>
                <span className="chip derived">added by reviewer</span>
              </div>
              <div className="value">{d.expected_value}</div>
              <div className="actions">
                <button className="act subtle" onClick={() => p.actions.decide(refOfDecision(d), "pending")}>
                  remove
                </button>
              </div>
            </div>
          ))}
          {adding ? (
            <div className="form add">
              <select value={prop} onChange={(e) => setProp(e.target.value)}>
                <option value="">Choose a property the rules missed…</option>
                {p.properties.map((t) => (
                  <option key={t.name} value={t.name}>
                    {t.name}
                    {t.term ? ` (${t.term})` : ""}
                  </option>
                ))}
              </select>
              <input placeholder="Expected value" value={value} onChange={(e) => setValue(e.target.value)} />
              <textarea placeholder="Where is it on the page? (optional note)" value={note} onChange={(e) => setNote(e.target.value)} />
              <div className="form-actions">
                <button className="primary" disabled={!prop || !value.trim()} onClick={submitAdd}>
                  Add missing value
                </button>
                <button onClick={() => setAdding(false)}>Cancel</button>
              </div>
            </div>
          ) : (
            <button className="add-btn" onClick={() => setAdding(true)}>+ Add missing property</button>
          )}
        </>
      )}
    </section>
  );
}

function refOf(recordId: string, f: RecordView["fields"][number]) {
  return {
    kind: "field" as const,
    key: f.field_id,
    canonical_label: f.canonical_label,
    source_url: f.source_url,
    record_id: recordId,
    rule_id: f.rule_id,
    value: f.value,
  };
}

function refOfDecision(d: Decision) {
  return {
    kind: "field" as const,
    key: d.key,
    canonical_label: d.canonical_label,
    source_url: d.source_url,
    record_id: d.record_id,
    value: null,
  };
}
