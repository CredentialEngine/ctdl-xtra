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

/** Two values: `a` (left / −) and `b` (right / +). `bEmpty` says why `b` is missing ("nothing extracted"). */
export function ValueDiff({ a, b, aLabel, bLabel, mode, compact = false, bEmpty = "no value" }: {
  a: string | null; b: string | null; aLabel: ReactNode; bLabel: ReactNode; mode: DiffMode; compact?: boolean; bEmpty?: string;
}) {
  const { left, right } = useMemo(() => sides(a, b, compact), [a, b, compact]);
  const view: DiffView = { aLabel, bLabel, compact, same: a !== null && b !== null && sameText(a, b),
    before: a === null ? <span className="vd-none">no value</span> : <Parts parts={left} mark="del" />,
    after: b === null ? <span className="vd-none">{bEmpty}</span> : <Parts parts={right} mark="add" /> };
  return mode === "unified" ? <UnifiedDiff {...view} /> : <SplitDiff {...view} />;
}

interface DiffView { before: ReactNode; after: ReactNode; aLabel: ReactNode; bLabel: ReactNode; compact: boolean; same: boolean }

function UnifiedDiff({ before, after, aLabel, bLabel, compact, same }: DiffView) {
  return (
    <div className={`vd unified${compact ? " compact" : ""}`} data-testid="value-diff">
      <div className="vd-hdr"><span>{aLabel}</span><span className="faint">→</span><span>{bLabel}</span></div>
      {same ? <div className="vd-ln"><span className="s" /><span className="t">{before}</span></div> : <>
        <div className="vd-ln del"><span className="s">−</span><span className="t">{before}</span></div>
        <div className="vd-ln add"><span className="s">+</span><span className="t">{after}</span></div>
      </>}
    </div>
  );
}

function SplitDiff({ before, after, aLabel, bLabel, compact, same }: DiffView) {
  return (
    <div className={`vd split${compact ? " compact" : ""}${same ? " same" : ""}`} data-testid="value-diff">
      <div className="vd-side del"><div className="vd-lab">{aLabel}</div><div className="t">{before}</div></div>
      <div className="vd-side add"><div className="vd-lab">{bLabel}</div><div className="t">{after}</div></div>
    </div>
  );
}

function Parts({ parts, mark }: { parts: ShownPart[]; mark: "del" | "add" }) {
  return <>{parts.map((p, i) => p.op === mark ? <mark key={i}>{p.text}</mark>
    : p.op === "gap" ? <span key={i} className="vd-gap">{p.text}</span> : <span key={i}>{p.text}</span>)}</>;
}

/** What a diff's note or verdict was compared with, as a chip label ("extract output 28 Oct", "ruleset v1"). */
export function comparedChip(c: ComparedWith | null | undefined, outputDay?: (score: string) => string | null): string | null {
  if (!c) return null;
  if (c.kind === "ruleset") return `ruleset v${c.ruleset}`;
  const day = outputDay?.(c.score);
  return day ? `extract output ${day}` : "xtra's extract output";
}

/** The note box under a diff. `collapsed` (Compare): "Note…" until clicked. The second action opens the ✗ flow. */
export function NoteActions(props: NoteActionsProps) {
  const box = useNoteBox(props.onSave, !!props.collapsed);
  if (!box.open) {
    return (
      <div className="vd-acts">
        <button className="btn sm" disabled={props.disabled} onClick={() => box.setOpen(true)}>Note…</button>
        <button className="btn sm" disabled={props.disabled} onClick={props.onWrong}>{props.wrongLabel}</button>
      </div>
    );
  }
  return <NoteBox box={box} {...props} />;
}

interface NoteActionsProps {
  wrongLabel: string; onSave: (note: string) => Promise<boolean>; onWrong: () => void; collapsed?: boolean; disabled?: boolean;
}

function useNoteBox(onSave: (note: string) => Promise<boolean>, collapsed: boolean) {
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
  return { open, setOpen, note, setNote, busy, save };
}

function NoteBox({ box, wrongLabel, onWrong, collapsed = false, disabled = false }: NoteActionsProps & { box: ReturnType<typeof useNoteBox> }) {
  return (
    <div className="vd-note">
      <textarea placeholder="Note on this difference" value={box.note} disabled={disabled} autoFocus={collapsed}
        onChange={(e) => box.setNote(e.target.value)}
        onKeyDown={(e) => { if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) { e.preventDefault(); void box.save(); } }} />
      <div className="vd-acts">
        <button className="btn sm primary" disabled={disabled || box.busy || !box.note.trim()} onClick={() => void box.save()}>Save note</button>
        {collapsed
          ? <button className="btn sm" onClick={() => { box.setOpen(false); box.setNote(""); }}>Cancel</button>
          : <button className="btn sm" disabled={disabled} onClick={onWrong}>{wrongLabel}</button>}
      </div>
    </div>
  );
}

/** The ✗ flow, as on the Rules tab: the pieces selected on the page, a note, Save · wrong. */
export function WrongFlow({ draft, onChange, onSave, onCancel }: {
  draft: Draft; onChange: (d: Draft) => void; onSave: () => void; onCancel: () => void;
}) {
  return <div className="vd-wrong"><Expansion draft={draft} propertyRule onChange={onChange} onSave={onSave} onCancel={onCancel} /></div>;
}

/** The box a wrong verdict on the row shows (Evals spec §6.4, decision 41). */
export function MarkedWrong({ verdict, what, column, compared }: {
  verdict: EventBrief; what: string; column: string; compared: string | null;
}) {
  return (
    <div className="vd-marked" data-testid="marked-wrong">
      <div className="h"><Ico name="needs work" /><b>Marked wrong</b><span className="muted">· {what}</span>
        <span className="when">{verdict.author} · {fmtDayTime(verdict.at)}</span></div>
      <WrongDetails verdict={verdict} compared={compared} />
      <div className="f"><Ico name="needs work" /><span><span className="mono">{column}</span> rule: known wrong values, until a new rule version fixes it</span></div>
    </div>
  );
}

function WrongDetails({ verdict, compared }: { verdict: EventBrief; compared: string | null }) {
  return (
    <table><tbody>
      {verdict.expected?.text && <tr><th>Right text</th><td>{verdict.expected.text}</td></tr>}
      {verdict.note && <tr><th>Note</th><td>{verdict.note}</td></tr>}
      {compared && <tr><th>Compared with</th><td><span className="vd-xchip">{compared}</span></td></tr>}
    </tbody></table>
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
export function ValuePage({ catalog, stem, url, title, golden, other, captures, capturing, onCapture, onRemove, labels, ruleset }: ValuePageProps) {
  const highlights = useMemo(() => pageHighlights(golden, other, captures), [golden, other, captures]);
  const focus = useFirstHighlight(stem, golden, other, captures.length);
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

interface ValuePageProps {
  catalog: string; stem: string; url: string; title: string; golden: GoldenSpot | null;
  other: string | null; captures: CapturedSelection[]; capturing: boolean;
  onCapture: (c: CapturedSelection) => void; onRemove: (i: number) => void;
  labels: { golden: string; other: string }; ruleset?: number | null;
}
type GoldenSpot = { cssPath: string | null; charStart: number | null; charEnd: number | null; text: string | null };

/** While the ✗ flow has pieces, only them; else the left value at its location and the right value by its text. */
function pageHighlights(golden: GoldenSpot | null, other: string | null, captures: CapturedSelection[]): Highlight[] {
  if (captures.length) return captures.map((c, i) => ({ id: `capture-${i}`, kind: "expected", cssPath: c.css_path, charStart: c.char_start,
    charEnd: c.char_end, text: c.text, removable: true }));
  return [...goldenHighlight(golden), ...otherHighlights(other)];
}

function useFirstHighlight(stem: string, golden: GoldenSpot | null, other: string | null, captureCount: number): string | null {
  const [focus, setFocus] = useState<string | null>(null);
  useEffect(() => { setFocus(captureCount ? "capture-0" : golden?.cssPath ? "golden" : other ? "other" : null); },
    [stem, golden, other, captureCount]);
  return focus;
}

function goldenHighlight(golden: GoldenSpot | null): Highlight[] {
  if (!golden?.cssPath) return [];
  return [{ id: "golden", kind: "expected", cssPath: golden.cssPath, charStart: golden.charStart, charEnd: golden.charEnd, text: golden.text }];
}

function otherHighlights(other: string | null): Highlight[] {
  if (!other) return [];
  const start: Highlight[] = other.length > 90 ? [{ id: "other-start", kind: "mark", cssPath: "body", text: other.slice(0, 80) }] : [];
  return [{ id: "other", kind: "mark", cssPath: "body", text: other }, ...start];
}
