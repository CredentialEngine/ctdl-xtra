// "Annotated by" (Evals spec §6.7, §6.8), shared by the Rules and Records tabs and kept in the URL (?by=…&v=…):
// a searchable dropdown of people grouped by role, each with the field values they annotated, plus "Not annotated
// yet" and "Any engineer · waiting for an expert"; the verdict switch beside it (Rules tab); the line a row shows when
// an expert confirmed its value (human-reviewed) or only an engineer did (engineer-checked); the experts' note.
import { useEffect, useRef, useState } from "react";
import type { ReviewMarks } from "../api/types";
import { Ico } from "../shell/icons";
import { fmt } from "../shell/ui";
import type { Annotators } from "./api";
import { BY_NOBODY, BY_WAITING, byLabel, shortWhen } from "./logic";

const VERDICTS: { id: string | null; name: string }[] = [
  { id: null, name: "Any" }, { id: "correct", name: "✓ correct" }, { id: "wrong", name: "✕ wrong" }, { id: "note", name: "note" }];

export function AnnotatedBy({ people, by, me, onPick, bare }: {
  people: Annotators | null; by: string | null; me: string; onPick: (by: string | null) => void;
  /** Without its "Annotated by" label: the label sits beside it (the Rules tab's filter rows). */
  bare?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState("");
  const box = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const away = (e: MouseEvent) => { if (!box.current?.contains(e.target as Node)) setOpen(false); };
    document.addEventListener("mousedown", away);
    return () => document.removeEventListener("mousedown", away);
  }, [open]);
  const pick = (v: string | null) => { onPick(v); setOpen(false); setQ(""); };
  const ql = q.trim().toLowerCase();
  const shown = (name: string) => !ql || name.toLowerCase().includes(ql);
  const all = people?.people ?? [];
  const values = (n: number) => <span className="ab-n">{n ? `${fmt(n)} value${n === 1 ? "" : "s"}` : "none yet"}</span>;
  const item = (id: string | null, name: string, extra?: React.ReactNode) => shown(name) && (
    <button key={id ?? ""} role="option" aria-selected={by === id} className={"ab-item" + (by === id ? " on" : "")}
      onClick={() => pick(id)}><span>{name}{id === me && <span className="faint"> (you)</span>}</span>{extra}</button>);
  const group = (role: "sme" | "engineer") => all.filter((p) => p.role === role).map((p) => item(p.name, p.name, values(p.values)));
  return (
    <div className="ab" ref={box} data-testid="annotated-by">
      <button className={"ab-btn" + (open ? " open" : "") + (by ? " set" : "")} aria-haspopup="listbox" aria-expanded={open}
        onClick={() => setOpen(!open)}>{!bare && <><span className="ab-k">Annotated by</span> </>}<b>{byLabel(by)}</b><Ico name="chevron" className="ab-car" /></button>
      {open && (
        <div className="ab-pop" role="listbox">
          <input className="ab-q" placeholder="Search people" value={q} autoFocus onChange={(e) => setQ(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Escape") setOpen(false); }} />
          {item(null, "Anyone")}
          {item(BY_NOBODY, "Not annotated yet")}
          <div className="ab-h">Subject matter experts · human-reviewed</div>
          {group("sme")}
          <div className="ab-h">Engineers · waiting for an expert</div>
          {item(BY_WAITING, "Any engineer · waiting for an expert", people && values(people.waiting))}
          {group("engineer")}
        </div>
      )}
    </div>
  );
}

export function VerdictSwitch({ verdict, onPick }: { verdict: string | null; onPick: (v: string | null) => void }) {
  return (
    <div className="seg ab-v" role="group" aria-label="Verdict">
      {VERDICTS.map((v) => <button key={v.name} className={verdict === v.id ? "on" : ""} onClick={() => onPick(v.id)}>{v.name}</button>)}
    </div>
  );
}

/** Under a value: "✓ human-reviewed · published  Jared Diener confirmed Eric Riddoch's check · just now", or
 * "✓ engineer-checked  Eric Riddoch [engineer] · 21 Oct · waiting for an expert". Nothing for other values. */
export function ReviewLine({ r }: { r: ReviewMarks }) {
  if (r.human_reviewed && r.human) {
    const confirmed = r.checked && r.checked.at <= r.human.at ? r.checked : null;
    return (
      <div className="rv-line" data-testid="review-line">
        <span className="rv-chip human">✓ human-reviewed · published</span>
        <b>{r.human.author}</b>{confirmed && <span className="muted">confirmed {confirmed.author}'s check</span>}
        <span className="muted">· {shortWhen(r.human.at)}</span>
      </div>
    );
  }
  if (r.engineer_checked && r.checked) {
    return (
      <div className="rv-line" data-testid="review-line">
        <span className="rv-chip eng">✓ engineer-checked</span>
        <b>{r.checked.author}</b><span className="rv-role">engineer</span>
        <span className="muted">· {shortWhen(r.checked.at)} · waiting for an expert</span>
      </div>
    );
  }
  return null;
}

/** Foot of the rule list, for experts: the values an engineer checked, and a button that lists them. */
export function WaitingNote({ n, on, onToggle }: { n: number; on: boolean; onToggle: () => void }) {
  if (!n) return null;
  return (
    <div className="ab-note" data-testid="waiting-note">
      <p><b>{fmt(n)} value{n === 1 ? "" : "s"} an engineer checked</b> {n === 1 ? "is" : "are"} waiting for an expert.
        They aren't human-reviewed until you confirm them.</p>
      <button className="btn" onClick={onToggle}>{on ? "Clear filter" : "Show them"}</button>
    </div>
  );
}

const KIND_NAME: Record<string, string> = { correct: "✓ correct", wrong: "✕ wrong", note: "note" };

/** Records tab, filtered to a person: their verdict on a value and when, where no review line says it. */
export function PersonLine({ name, a }: { name: string; a: { kinds: string[]; at: string } }) {
  return (
    <div className="rv-line" data-testid="person-line">
      <b>{name}</b><span className="muted">{a.kinds.map((k) => ` · ${KIND_NAME[k] ?? k}`).join("")} · {shortWhen(a.at)}</span>
    </div>
  );
}
