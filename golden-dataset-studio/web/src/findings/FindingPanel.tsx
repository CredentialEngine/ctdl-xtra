// A finding's editor (learning-programs Phase 6; mockup w4-evals-finding-panel), a drawer on the right: its code and
// title, whose error, the units it covers (live per catalog, else the running notes' counts), cause, fix and
// assessment, its state, and its thread. The same drawer holds a group's thread alone (`thread` without a finding).
// Anyone edits; a person says Fixed (a finding never closes by itself, wave 4 §4.3).
import { useEffect, useRef, useState } from "react";
import { Markdown } from "../prompt/markdown";
import "../prompt/prompt.css";
import { api } from "../api/client";
import type { FindingLink, FindingX, ThreadComment, ThreadTarget } from "../api/types";
import { useReviewer } from "../shell/reviewer";
import { CLASS_NAME, type ClassSlug } from "../shell/router";
import { fmt, toast } from "../shell/ui";
import { COUNTED, countsOf, findingThread, termOfColumn, WHOSE } from "./logic";
import "./findings.css";

const day = (iso: string) => new Date(iso).toLocaleDateString("en-GB", { day: "numeric", month: "short" });
const first = (name: string) => name.split(" ")[0];

/** A text field shown as written (Markdown: links, lists, tables), a click away from its editor, which grows with its
 * text. */
function Field({ label, value, editing, onChange }: { label: string; value: string; editing: boolean; onChange: (v: string) => void }) {
  const [edit, setEdit] = useState(editing);
  const ref = useRef<HTMLTextAreaElement>(null);
  useEffect(() => {
    const el = ref.current;
    if (el) { el.style.height = "auto"; el.style.height = `${el.scrollHeight + 2}px`; }
  }, [edit, value]);
  if (!edit) {
    return <div className={`fd-box fd-read${value ? "" : " empty"}`} role="button" tabIndex={0} aria-label={`Edit ${label}`}
      title="Click to edit" onClick={() => setEdit(true)} onKeyDown={(e) => { if (e.key === "Enter") setEdit(true); }}>
      {value ? <Markdown text={value} /> : <span className="faint">Not written yet.</span>}</div>;
  }
  return <textarea ref={ref} className="fd-box fd-ta" aria-label={label} value={value} autoFocus={!editing}
    onChange={(e) => onChange(e.target.value)} />;
}

/** A thread: its comments, oldest first, and a reply box (Enter posts). */
export function Thread({ cls, col, target, onPosted }: { cls: ClassSlug; col: string; target: ThreadTarget; onPosted?: () => void }) {
  const me = useReviewer();
  const key = target.kind === "finding" ? findingThread(target.id)
    : `group:${target.catalog}|${target.outcome}|${target.field ?? ""}|${target.by}|${target.key}`;
  const [items, setItems] = useState<ThreadComment[] | null>(null);
  const [note, setNote] = useState("");
  useEffect(() => { let live = true; api.propertyThread(cls, col, key).then((x) => live && setItems(x), () => live && setItems([])); return () => { live = false; }; }, [cls, col, key]);
  const post = async () => {
    if (!note.trim()) return;
    try {
      const c = await api.addPropertyComment(cls, col, { author: me, note, target });
      setItems((x) => [...(x ?? []), c]); setNote(""); onPosted?.();
    } catch (e) { toast(`Not saved: ${e instanceof Error ? e.message : String(e)}`); }
  };
  return (
    <div className="fd-thread" data-testid="thread">
      {items === null ? <p className="faint">Loading…</p> : items.length === 0 ? <p className="faint">No comments yet.</p>
        : items.map((c) => (
          <div key={c.annotation_id} className="fd-cm"><div><b>{c.author}</b> <span className="faint">{day(c.at)}</span></div>
            <p>{c.note}</p></div>))}
      <input className="fd-reply" placeholder="Reply…" value={note} aria-label="Reply" onChange={(e) => setNote(e.target.value)}
        onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); void post(); } }} />
    </div>
  );
}

export function FindingPanel({ cls, col, finding, link, thread, catalogName, onClose, onSaved }: {
  cls: ClassSlug; col: string;
  /** the finding to edit; null for a new one (covering `link`) */
  finding: FindingX | null;
  link?: FindingLink | null;
  /** a group's thread alone */
  thread?: { target: ThreadTarget; title: string } | null;
  catalogName: (short: string) => string;
  onClose: () => void; onSaved: () => void;
}) {
  const me = useReviewer();
  const [d, setD] = useState(() => ({
    code: finding?.code ?? "", title: finding?.title ?? "", whose: finding?.whose ?? null, kind: finding?.kind ?? (link?.outcome === "missing" ? "missing" : "mismatch"),
    cause: finding?.cause ?? "", fix: finding?.fix ?? "", assessment: finding?.assessment ?? "", state: finding?.state ?? "open",
  }));
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    const esc = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", esc);
    return () => window.removeEventListener("keydown", esc);
  }, [onClose]);
  const isNew = !finding && !thread;
  const dirty = isNew || !!finding && (["code", "title", "whose", "kind", "cause", "fix", "assessment", "state"] as const)
    .some((k) => (d[k] ?? "") !== ((finding as unknown as Record<string, string | null>)[k] ?? ""));
  const save = async () => {
    setBusy(true);
    try {
      await api.saveFinding(cls, col, { author: me, ...d, whose: d.whose || null,
        ...(isNew && link ? { links: [link] } : {}) } as never, finding?.id);
      toast(isNew ? `${d.code} saved` : `${d.code} updated`);
      onSaved();
      if (isNew) onClose();
    } catch (e) { toast(`Not saved: ${e instanceof Error ? e.message : String(e)}`); }
    setBusy(false);
  };
  const set = (k: keyof typeof d) => (v: string | null) => setD((x) => ({ ...x, [k]: v }));
  const counts = finding ? countsOf(finding) : null;

  return (
    <aside className="fd-panel" role="dialog" aria-modal="false" aria-label={thread ? thread.title : finding ? `${finding.code} ${finding.title}` : "New finding"}
      data-testid="finding-panel">
      <button className="ac-x fd-x" aria-label="Close" onClick={onClose}>×</button>
      {thread ? <>
        <h2 className="fd-h">{thread.title}</h2>
        <p className="muted fd-sub">Discussion on <span className="mono">{termOfColumn(col)}</span>, {CLASS_NAME[cls]}.</p>
        <Thread cls={cls} col={col} target={thread.target} onPosted={onSaved} />
      </> : <>
        {isNew
          ? <div className="fd-new"><input className="fd-code mono" placeholder="Code" aria-label="Code" value={d.code} onChange={(e) => set("code")(e.target.value)} autoFocus />
              <input className="fd-title" placeholder="What goes wrong, in a sentence" aria-label="Title" value={d.title} onChange={(e) => set("title")(e.target.value)} /></div>
          : <h2 className="fd-h"><span className="mono fd-c">{finding!.code}</span>{finding!.title}</h2>}
        <p className="muted fd-sub">Finding on <span className="mono">{termOfColumn(col)}</span>, {CLASS_NAME[cls]}.
          {finding ? <> Opened by {first(finding.created.by)}, {day(finding.created.at)}. {finding.state === "open" ? "Open." : "Fixed."}</> : null}</p>

        <h3 className="fd-l">Whose error</h3>
        <span className="seg xs fd-seg" role="group" aria-label="Whose error">
          {WHOSE.map((w) => <button key={w} className={d.whose === w ? "on" : ""} onClick={() => set("whose")(d.whose === w ? null : w)}>{w}</button>)}
        </span>

        <h3 className="fd-l">Units it covers</h3>
        <div className="fd-box fd-units">
          {isNew ? (link ? <p>{catalogName(link.catalog)}, <i>{link.outcome}, {link.key}</i></p> : <p className="faint">No group yet.</p>)
            : finding!.live ? (
              <table><thead><tr><th /><th className="r">golden</th><th className="r">silver</th></tr></thead>
                <tbody>{finding!.live.rows.map((r, i) => (
                  <tr key={i}><td>{catalogName(r.catalog)}, <i>{r.outcome}, {r.key}</i></td><td className="r">{fmt(r.golden)}</td><td className="r">{fmt(r.silver)}</td></tr>))}
                </tbody></table>)
            : (
              <table><thead><tr><th /><th className="r">golden</th><th className="r">silver</th></tr></thead>
                <tbody>{COUNTED.filter((o) => counts![o]).map((o) => (
                  <tr key={o}><td><i>{o}</i></td><td className="r">{fmt(counts![o]![0])}</td><td className="r">{fmt(counts![o]![1])}</td></tr>))}
                </tbody>
                <tfoot><tr><td colSpan={3} className="faint">{finding!.catalogs}. From the running notes; counted live once linked to a group in Evals.</td></tr></tfoot></table>)}
        </div>

        {(["cause", "fix", "assessment"] as const).map((k) => (
          <div key={k}><h3 className="fd-l">{k}</h3>
            <Field label={k} value={d[k] ?? ""} editing={isNew} onChange={set(k)} /></div>))}

        {finding && <><h3 className="fd-l">State</h3>
          <span className="seg xs fd-seg" role="group" aria-label="State">
            <button className={d.state === "open" ? "on" : ""} onClick={() => set("state")("open")}>open</button>
            <button className={d.state === "fixed" ? "on" : ""} onClick={() => set("state")("fixed")}
              title="Say it's fixed: a finding never closes by itself">fixed</button>
          </span></>}

        {dirty && <div className="fd-save"><button className="btn primary" disabled={busy || !d.code.trim() || !d.title.trim()} onClick={save}>
          {isNew ? "Save finding" : "Save changes"}</button></div>}

        {finding && <><h3 className="fd-l">Discussion</h3>
          <Thread cls={cls} col={col} target={{ kind: "finding", id: finding.id }} onPosted={onSaved} /></>}
      </>}
    </aside>
  );
}
