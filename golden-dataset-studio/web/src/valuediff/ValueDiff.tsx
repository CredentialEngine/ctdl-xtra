// The value diff Evals and Compare share (Evals spec §4.2, §6.4, §6.5): two values GitHub-style, Split (default) or
// Unified, the note box under it (Save note · "… is wrong…", which opens the ✗ flow: select the right text on the
// page), the structured "Marked wrong" box once a wrong verdict is on the row, and the saved page with both values.
import { useEffect, useMemo, useState, useSyncExternalStore, type ReactNode } from "react";
import type { ComparedWith, EventBrief } from "../api/types";
import { PagePane, type CapturedSelection, type Highlight } from "../pagepane";
import { Ico } from "../shell/icons";
import { Expansion } from "../rules/parts";
import type { Draft } from "../rules/logic";
import { fmtDayTime, sameText, sides, type ShownPart } from "./diff";
import "./valuediff.css";

export type DiffMode = "split" | "unified";
const MODE_KEY = "studio.diff.mode";

// Split or Unified for every diff at once: one switch near the top of a tab (DiffModeSwitch) sets it, every diff reads
// it (useDiffMode), and this browser remembers it (Split until someone picks Unified).
const readMode = (): DiffMode => {
  try { return localStorage.getItem(MODE_KEY) === "unified" ? "unified" : "split"; } catch { return "split"; }
};
let current: DiffMode | null = null;
const listeners = new Set<() => void>();
const subscribe = (f: () => void) => { listeners.add(f); return () => { listeners.delete(f); }; };
const snapshot = () => (current ??= readMode());

export function setDiffMode(m: DiffMode): void {
  current = m;
  try { localStorage.setItem(MODE_KEY, m); } catch { /* private window */ }
  listeners.forEach((f) => f());
}

/** The layout every diff uses. */
export function useDiffMode(): DiffMode {
  return useSyncExternalStore(subscribe, snapshot, snapshot);
}

/** The one Split | Unified switch of a tab: it changes every diff on it. */
export function DiffModeSwitch() {
  const mode = useDiffMode();
  return (
    <span className="vd-modew" title="How every diff on this tab is shown">
      <span className="faint">Diffs</span>
      <span className="seg vd-mode" role="group" aria-label="Diff layout">
        <button className={mode === "split" ? "on" : ""} onClick={() => setDiffMode("split")}>Split</button>
        <button className={mode === "unified" ? "on" : ""} onClick={() => setDiffMode("unified")}>Unified</button>
      </span>
    </span>
  );
}

function Parts({ parts, mark }: { parts: ShownPart[]; mark: "del" | "add" }) {
  return <>{parts.map((p, i) => p.op === mark ? <mark key={i}>{p.text}</mark>
    : p.op === "gap" ? <span key={i} className="vd-gap">{p.text}</span> : <span key={i}>{p.text}</span>)}</>;
}

/** Two values: `a` (left / −) and `b` (right / +). `bEmpty` says why `b` is missing ("nothing extracted"). */
export function ValueDiff({ a, b, aLabel, bLabel, mode, compact = false, bEmpty = "no value" }: {
  a: string | null; b: string | null; aLabel: ReactNode; bLabel: ReactNode; mode: DiffMode; compact?: boolean; bEmpty?: string;
}) {
  const same = a !== null && b !== null && sameText(a, b);
  const { left, right } = useMemo(() => sides(a, b, compact), [a, b, compact]);
  const A = a === null ? <span className="vd-none">no value</span> : <Parts parts={left} mark="del" />;
  const B = b === null ? <span className="vd-none">{bEmpty}</span> : <Parts parts={right} mark="add" />;
  if (mode === "unified") {
    return (
      <div className={`vd unified${compact ? " compact" : ""}`} data-testid="value-diff">
        <div className="vd-hdr"><span>{aLabel}</span><span className="faint">→</span><span>{bLabel}</span></div>
        {same ? <div className="vd-ln"><span className="s" /><span className="t">{A}</span></div> : <>
          <div className="vd-ln del"><span className="s">−</span><span className="t">{A}</span></div>
          <div className="vd-ln add"><span className="s">+</span><span className="t">{B}</span></div>
        </>}
      </div>
    );
  }
  return (
    <div className={`vd split${compact ? " compact" : ""}${same ? " same" : ""}`} data-testid="value-diff">
      <div className="vd-side del"><div className="vd-lab">{aLabel}</div><div className="t">{A}</div></div>
      <div className="vd-side add"><div className="vd-lab">{bLabel}</div><div className="t">{B}</div></div>
    </div>
  );
}

/** What a diff's note or verdict was compared with, as a chip label ("extract output 28 Oct", "ruleset v1"). */
export function comparedChip(c: ComparedWith | null | undefined, outputDay?: (score: string) => string | null): string | null {
  if (!c) return null;
  if (c.kind === "ruleset") return `ruleset v${c.ruleset}`;
  const day = outputDay?.(c.score);
  return day ? `extract output ${day}` : "xtra's extract output";
}

/** The note box under a diff. `collapsed` (Compare): "Note…" until clicked. The second action opens the ✗ flow. */
export function NoteActions({ wrongLabel, onSave, onWrong, collapsed = false, disabled = false }: {
  wrongLabel: string; onSave: (note: string) => Promise<boolean>; onWrong: () => void; collapsed?: boolean; disabled?: boolean;
}) {
  const [open, setOpen] = useState(!collapsed);
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const save = async () => {
    if (!note.trim()) return;
    setBusy(true);
    const ok = await onSave(note.trim());
    setBusy(false);
    if (ok) { setNote(""); if (collapsed) setOpen(false); }
  };
  if (!open) {
    return (
      <div className="vd-acts">
        <button className="btn sm" disabled={disabled} onClick={() => setOpen(true)}>Note…</button>
        <button className="btn sm" disabled={disabled} onClick={onWrong}>{wrongLabel}</button>
      </div>
    );
  }
  return (
    <div className="vd-note">
      <textarea placeholder="Note on this difference" value={note} disabled={disabled} autoFocus={collapsed}
        onChange={(e) => setNote(e.target.value)}
        onKeyDown={(e) => { if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) { e.preventDefault(); void save(); } }} />
      <div className="vd-acts">
        <button className="btn sm primary" disabled={disabled || busy || !note.trim()} onClick={() => void save()}>Save note</button>
        {collapsed
          ? <button className="btn sm" onClick={() => { setOpen(false); setNote(""); }}>Cancel</button>
          : <button className="btn sm" disabled={disabled} onClick={onWrong}>{wrongLabel}</button>}
      </div>
    </div>
  );
}

/** The ✗ flow, as on the Rules tab: the pieces selected on the page, a note, Save · wrong. */
export function WrongFlow({ draft, onChange, onSave, onCancel }: {
  draft: Draft; onChange: (d: Draft) => void; onSave: () => void; onCancel: () => void;
}) {
  return <div className="vd-wrong"><Expansion draft={draft} fieldRule onChange={onChange} onSave={onSave} onCancel={onCancel} /></div>;
}

/** The box a wrong verdict on the row shows (Evals spec §6.4, decision 41). */
export function MarkedWrong({ verdict, what, column, compared }: {
  verdict: EventBrief; what: string; column: string; compared: string | null;
}) {
  return (
    <div className="vd-marked" data-testid="marked-wrong">
      <div className="h"><Ico name="needs work" /><b>Marked wrong</b><span className="muted">· {what}</span>
        <span className="when">{verdict.author} · {fmtDayTime(verdict.at)}</span></div>
      <table><tbody>
        {verdict.expected?.text && <tr><th>Right text</th><td>{verdict.expected.text}</td></tr>}
        {verdict.note && <tr><th>Note</th><td>{verdict.note}</td></tr>}
        {compared && <tr><th>Compared with</th><td><span className="vd-xchip">{compared}</span></td></tr>}
      </tbody></table>
      <div className="f"><Ico name="needs work" /><span><span className="mono">{column}</span> rule: known wrong values, until a new rule version fixes it</span></div>
    </div>
  );
}

/** Notes already on the row (any comment), newest last, with what each was compared with. */
export function RowNotes({ comments, label }: { comments: EventBrief[]; label: (e: EventBrief) => string | null }) {
  const notes = comments.filter((c) => c.note);
  if (!notes.length) return null;
  return (
    <ul className="vd-notes">
      {notes.map((c) => {
        const l = label(c);
        return <li key={c.annotation_id}><Ico name="bubble" /><span><b>{c.author}</b> “{c.note}”
          <span className="faint"> · {fmtDayTime(c.at)}{l ? ` · compared with ${l}` : ""}</span></span></li>;
      })}
    </ul>
  );
}

/** The saved page: the left value (green) at its recorded location, the right value (pink) wherever its text is
 * found, and while the ✗ flow is open, the pieces selected (they can be removed with ×). */
export function ValuePage({ catalog, stem, url, title, golden, other, captures, capturing, onCapture, onRemove, labels, ruleset }: {
  catalog: string; stem: string; url: string; title: string;
  golden: { cssPath: string | null; charStart: number | null; charEnd: number | null; text: string | null } | null;
  other: string | null; captures: CapturedSelection[]; capturing: boolean;
  onCapture: (c: CapturedSelection) => void; onRemove: (i: number) => void;
  labels: { golden: string; other: string }; ruleset?: number | null;
}) {
  const highlights = useMemo<Highlight[]>(() => {
    const h: Highlight[] = [];
    if (captures.length) {
      captures.forEach((c, i) => h.push({ id: `capture-${i}`, kind: "expected", cssPath: c.css_path, charStart: c.char_start,
        charEnd: c.char_end, text: c.text, removable: true }));
      return h;
    }
    if (golden?.cssPath) h.push({ id: "golden", kind: "expected", cssPath: golden.cssPath, charStart: golden.charStart,
      charEnd: golden.charEnd, text: golden.text });
    if (other) {
      h.push({ id: "other", kind: "mark", cssPath: "body", text: other });
      if (other.length > 90) h.push({ id: "other-start", kind: "mark", cssPath: "body", text: other.slice(0, 80) });
    }
    return h;
  }, [golden, other, captures]);
  const [focus, setFocus] = useState<string | null>(null);
  useEffect(() => { setFocus(captures.length ? "capture-0" : golden?.cssPath ? "golden" : other ? "other" : null); },
    [stem, golden, other, captures.length]);
  return (
    <div className="vd-page">
      <PagePane catalog={catalog} tabs={[{ stem, url, title }]} activeStem={stem} onActivate={() => {}}
        highlights={highlights} focusId={focus} ruleset={ruleset}
        captureSelection={capturing} onSelection={onCapture} onRemove={(id) => onRemove(Number(id.split("-")[1]))}
        banner={capturing ? <span>Select the right text on the page. Drag across more text to add a piece.</span> : undefined}
        legend={<span className="vd-legend"><span><i className="sw g" />{labels.golden}</span>
          {other && <span><i className="sw x" />{labels.other}</span>}</span>} />
    </div>
  );
}
