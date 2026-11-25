// A finding's editor (learning-programs Phase 6; mockup w4-evals-finding-panel), a drawer on the right: its code and
// title, whose error, the units it covers (live per catalog, else the running notes' counts), cause, fix and
// assessment, its state, and its thread. The same drawer holds a group's thread alone (`thread` without a finding).
// Anyone edits; a person says Fixed (a finding never closes by itself, wave 4 §4.3).
import { SkelCards } from "../shell/Skeleton";
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

interface FindingPanelProps {
  cls: ClassSlug; col: string;
  /** the finding to edit; null for a new one (covering `link`) */
  finding: FindingX | null;
  link?: FindingLink | null;
  /** a group's thread alone */
  thread?: { target: ThreadTarget; title: string } | null;
  catalogName: (short: string) => string;
  onClose: () => void; onSaved: () => void;
}
interface ThreadProps { cls: ClassSlug; col: string; target: ThreadTarget; onPosted?: () => void }
type FindingDraft = ReturnType<typeof draftOf>;
type Editor = ReturnType<typeof useFindingDraft>;
interface FindingSave {
  cls: ClassSlug; col: string; me: string; d: FindingDraft; isNew: boolean; link?: FindingLink | null; finding: FindingX | null;
  onSaved: () => void; onClose: () => void;
}
const FIELDS = ["code", "title", "whose", "kind", "cause", "fix", "assessment", "state"] as const;

export function FindingPanel(props: FindingPanelProps) {
  const { finding, thread, onClose } = props;
  useEscape(onClose);
  return (
    <aside className="fd-panel" role="dialog" aria-modal="false" aria-label={thread ? thread.title : finding ? `${finding.code} ${finding.title}` : "New finding"}
      data-testid="finding-panel">
      <button className="ac-x fd-x" aria-label="Close" onClick={onClose}>×</button>
      {thread ? <GroupThread {...props} thread={thread} /> : <FindingEditor {...props} />}
    </aside>
  );
}

/** A thread: its comments, oldest first, and a reply box (Enter posts). */
export function Thread({ cls, col, target, onPosted }: ThreadProps) {
  const me = useReviewer();
  const [items, setItems] = useThreadComments(cls, col, threadKey(target));
  const [note, setNote] = useState("");
  const post = () => postReply({ cls, col, target }, me, note, (c) => { setItems((x) => [...(x ?? []), c]); setNote(""); onPosted?.(); });
  return (
    <div className="fd-thread" data-testid="thread">
      <Comments items={items} />
      <input className="fd-reply" placeholder="Reply…" value={note} aria-label="Reply" onChange={(e) => setNote(e.target.value)}
        onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); void post(); } }} />
    </div>
  );
}

function useEscape(onClose: () => void) {
  useEffect(() => {
    const esc = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", esc);
    return () => window.removeEventListener("keydown", esc);
  }, [onClose]);
}

function GroupThread({ cls, col, thread, onSaved }: FindingPanelProps & { thread: { target: ThreadTarget; title: string } }) {
  return <>
    <h2 className="fd-h">{thread.title}</h2>
    <p className="muted fd-sub">Discussion on <span className="mono">{termOfColumn(col)}</span>, {CLASS_NAME[cls]}.</p>
    <Thread cls={cls} col={col} target={thread.target} onPosted={onSaved} />
  </>;
}

function FindingEditor(props: FindingPanelProps) {
  const editor = useFindingDraft(props);
  return (
    <>
      <FindingTitle editor={editor} finding={props.finding} />
      <FindingSub cls={props.cls} col={props.col} finding={props.finding} />
      <WhoseSwitch editor={editor} />
      <UnitsBox isNew={editor.isNew} link={props.link} finding={props.finding} catalogName={props.catalogName} />
      <FindingTexts editor={editor} />
      {props.finding && <StateSwitch editor={editor} />}
      {editor.dirty && <SaveFinding editor={editor} />}
      {props.finding && <FindingDiscussion {...props} finding={props.finding} />}
    </>
  );
}

function useThreadComments(cls: ClassSlug, col: string, key: string) {
  const [items, setItems] = useState<ThreadComment[] | null>(null);
  useEffect(() => { let live = true; api.propertyThread(cls, col, key).then((x) => live && setItems(x), () => live && setItems([])); return () => { live = false; }; }, [cls, col, key]);
  return [items, setItems] as const;
}

function threadKey(target: ThreadTarget): string {
  return target.kind === "finding" ? findingThread(target.id)
    : `group:${target.catalog}|${target.outcome}|${target.field ?? ""}|${target.by}|${target.key}`;
}

async function postReply({ cls, col, target }: Omit<ThreadProps, "onPosted">, me: string, note: string, onPosted: (c: ThreadComment) => void) {
  if (!note.trim()) return;
  try { onPosted(await api.addPropertyComment(cls, col, { author: me, note, target })); }
  catch (e) { toast(`Not saved: ${e instanceof Error ? e.message : String(e)}`); }
}

function Comments({ items }: { items: ThreadComment[] | null }) {
  if (items === null) return <SkelCards n={2} label="Loading comments" />;
  if (items.length === 0) return <p className="faint">No comments yet.</p>;
  return <>{items.map((c) => (
    <div key={c.annotation_id} className="fd-cm"><div><b>{c.author}</b> <span className="faint">{day(c.at)}</span></div>
      <p>{c.note}</p></div>))}</>;
}

function useFindingDraft({ cls, col, finding, link, onClose, onSaved }: FindingPanelProps) {
  const me = useReviewer();
  const [d, setD] = useState(() => draftOf(finding, link));
  const [busy, setBusy] = useState(false);
  const isNew = !finding;
  const save = async () => {
    setBusy(true);
    await storeFinding({ cls, col, me, d, isNew, link, finding, onSaved, onClose });
    setBusy(false);
  };
  const set = (k: keyof FindingDraft) => (v: string | null) => setD((x) => ({ ...x, [k]: v }));
  return { d, set, busy, save, isNew, dirty: isNew || isChanged(d, finding!) };
}

function FindingTitle({ editor: { isNew, d, set }, finding }: { editor: Editor; finding: FindingX | null }) {
  if (!isNew) return <h2 className="fd-h"><span className="mono fd-c">{finding!.code}</span>{finding!.title}</h2>;
  return <div className="fd-new"><input className="fd-code mono" placeholder="Code" aria-label="Code" value={d.code} onChange={(e) => set("code")(e.target.value)} autoFocus />
    <input className="fd-title" placeholder="What goes wrong, in a sentence" aria-label="Title" value={d.title} onChange={(e) => set("title")(e.target.value)} /></div>;
}

function FindingSub({ cls, col, finding }: { cls: ClassSlug; col: string; finding: FindingX | null }) {
  return <p className="muted fd-sub">Finding on <span className="mono">{termOfColumn(col)}</span>, {CLASS_NAME[cls]}.
    {finding ? <> Opened by {first(finding.created.by)}, {day(finding.created.at)}. {finding.state === "open" ? "Open." : "Fixed."}</> : null}</p>;
}

function WhoseSwitch({ editor: { d, set } }: { editor: Editor }) {
  return <>
    <h3 className="fd-l">Whose error</h3>
    <span className="seg xs fd-seg" role="group" aria-label="Whose error">
      {WHOSE.map((w) => <button key={w} className={d.whose === w ? "on" : ""} onClick={() => set("whose")(d.whose === w ? null : w)}>{w}</button>)}
    </span>
  </>;
}

function UnitsBox({ isNew, link, finding, catalogName }: {
  isNew: boolean; link?: FindingLink | null; finding: FindingX | null; catalogName: (short: string) => string }) {
  return <>
    <h3 className="fd-l">Units it covers</h3>
    <div className="fd-box fd-units">
      {isNew ? (link ? <p>{catalogName(link.catalog)}, <i>{link.outcome}, {link.key}</i></p> : <p className="faint">No group yet.</p>)
        : finding!.live ? <LiveUnits live={finding!.live} catalogName={catalogName} /> : <NotedUnits finding={finding!} />}
    </div>
  </>;
}

function FindingTexts({ editor: { d, set, isNew } }: { editor: Editor }) {
  return <>{(["cause", "fix", "assessment"] as const).map((k) => (
    <div key={k}><h3 className="fd-l">{k}</h3>
      <Field label={k} value={d[k] ?? ""} editing={isNew} onChange={set(k)} /></div>))}</>;
}

function StateSwitch({ editor: { d, set } }: { editor: Editor }) {
  return <><h3 className="fd-l">State</h3>
    <span className="seg xs fd-seg" role="group" aria-label="State">
      <button className={d.state === "open" ? "on" : ""} onClick={() => set("state")("open")}>open</button>
      <button className={d.state === "fixed" ? "on" : ""} onClick={() => set("state")("fixed")}
        title="Say it's fixed: a finding never closes by itself">fixed</button>
    </span></>;
}

function SaveFinding({ editor: { d, busy, save, isNew } }: { editor: Editor }) {
  return <div className="fd-save"><button className="btn primary" disabled={busy || !d.code.trim() || !d.title.trim()} onClick={save}>
    {isNew ? "Save finding" : "Save changes"}</button></div>;
}

function FindingDiscussion({ cls, col, finding, onSaved }: FindingPanelProps & { finding: FindingX }) {
  return <><h3 className="fd-l">Discussion</h3>
    <Thread cls={cls} col={col} target={{ kind: "finding", id: finding.id }} onPosted={onSaved} /></>;
}

function draftOf(finding: FindingX | null, link: FindingLink | null | undefined) {
  return {
    code: finding?.code ?? "", title: finding?.title ?? "", whose: finding?.whose ?? null, kind: finding?.kind ?? (link?.outcome === "missing" ? "missing" : "mismatch"),
    cause: finding?.cause ?? "", fix: finding?.fix ?? "", assessment: finding?.assessment ?? "", state: finding?.state ?? "open",
  };
}

async function storeFinding({ cls, col, me, d, isNew, link, finding, onSaved, onClose }: FindingSave) {
  try {
    await api.saveFinding(cls, col, { author: me, ...d, whose: d.whose || null,
      ...(isNew && link ? { links: [link] } : {}) } as never, finding?.id);
    toast(isNew ? `${d.code} saved` : `${d.code} updated`);
    onSaved();
    if (isNew) onClose();
  } catch (e) { toast(`Not saved: ${e instanceof Error ? e.message : String(e)}`); }
}

function isChanged(d: FindingDraft, finding: FindingX): boolean {
  return FIELDS.some((k) => (d[k] ?? "") !== ((finding as unknown as Record<string, string | null>)[k] ?? ""));
}

function LiveUnits({ live, catalogName }: { live: NonNullable<FindingX["live"]>; catalogName: (short: string) => string }) {
  return <table><thead><tr><th /><th className="r">golden</th><th className="r">silver</th></tr></thead>
    <tbody>{live.rows.map((r, i) => (
      <tr key={i}><td>{catalogName(r.catalog)}, <i>{r.outcome}, {r.key}</i></td><td className="r">{fmt(r.golden)}</td><td className="r">{fmt(r.silver)}</td></tr>))}
    </tbody></table>;
}

function NotedUnits({ finding }: { finding: FindingX }) {
  const counts = countsOf(finding);
  return <table><thead><tr><th /><th className="r">golden</th><th className="r">silver</th></tr></thead>
    <tbody>{COUNTED.filter((o) => counts[o]).map((o) => (
      <tr key={o}><td><i>{o}</i></td><td className="r">{fmt(counts[o]![0])}</td><td className="r">{fmt(counts[o]![1])}</td></tr>))}
    </tbody>
    <tfoot><tr><td colSpan={3} className="faint">{finding.catalogs}. From the running notes; counted live once linked to a group in Evals.</td></tr></tfoot></table>;
}

/** A text field shown as written (Markdown: links, lists, tables), a click away from its editor, which grows with its
 * text. */
function Field({ label, value, editing, onChange }: { label: string; value: string; editing: boolean; onChange: (v: string) => void }) {
  const [edit, setEdit] = useState(editing);
  const ref = useGrowingTextarea(edit, value);
  if (!edit) return <FieldView label={label} value={value} onEdit={() => setEdit(true)} />;
  return <textarea ref={ref} className="fd-box fd-ta" aria-label={label} value={value} autoFocus={!editing}
    onChange={(e) => onChange(e.target.value)} />;
}

function useGrowingTextarea(edit: boolean, value: string) {
  const ref = useRef<HTMLTextAreaElement>(null);
  useEffect(() => {
    const el = ref.current;
    if (el) { el.style.height = "auto"; el.style.height = `${el.scrollHeight + 2}px`; }
  }, [edit, value]);
  return ref;
}

function FieldView({ label, value, onEdit }: { label: string; value: string; onEdit: () => void }) {
  return <div className={`fd-box fd-read${value ? "" : " empty"}`} role="button" tabIndex={0} aria-label={`Edit ${label}`}
    title="Click to edit" onClick={onEdit} onKeyDown={(e) => { if (e.key === "Enter") onEdit(); }}>
    {value ? <Markdown text={value} /> : <span className="faint">Not written yet.</span>}</div>;
}

function day(iso: string): string {
  return new Date(iso).toLocaleDateString("en-GB", { day: "numeric", month: "short" });
}

function first(name: string): string {
  return name.split(" ")[0];
}
