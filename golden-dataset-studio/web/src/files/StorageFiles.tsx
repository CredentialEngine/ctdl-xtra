// Storage files (routes_files.py): a debugging view of what the Studio keeps for a catalog on its storage root, to
// see how it works under the hood. Opened from the bottom bar, out of the way. Left: the files as a tree of the
// storage layout (the root's manifest, then the catalog's rules, rulesets and annotation log, then its crawl with
// extractions and golden publications), folders collapsible, each file with what it is on hover.
// Right: the selected file: JSON pretty-printed, the log as events (newest first), Parquet as a table; both filterable.
import { useEffect, useMemo, useState } from "react";
import { colorizeJson } from "../golden/FilePreview";
import { fmt, Ico } from "../shell/ui";
import "../golden/golden.css";
import "./files.css";

interface FileItem { path: string; size: number; group: string; about: string; portal?: string }
interface Portal { browser: string; container_url?: string; container: string; prefix: string }
interface Listing { root: string; catalog: string; crawl: string; files: FileItem[]; portal: Portal | null }
interface Head { path: string; uri: string; size: number; about: string; portal: string | null }
type TextContent = Head & { kind: "json" | "text"; text: string; truncated: boolean };
type EventsContent = Head & { kind: "jsonl"; total: number; matched: number; offset: number; rows: { line: number; event: unknown }[] };
type TableContent = Head & { kind: "table"; total: number; matched: number; offset: number; columns: string[]; rows: unknown[][] };
type Content = TextContent | EventsContent | TableContent;
type PreviewFilter = ReturnType<typeof usePreviewFilter>;

export interface TreeNode { name: string; path: string; file?: FileItem; children: TreeNode[]; files: number }
interface BranchProps {
  nodes: TreeNode[]; depth: number; closed: Set<string>; toggle: (p: string) => void; selected: string | null;
  onPick: (p: string) => void;
}

/** A short note after some folders, to read the layout at a glance. */
const FOLDER_NOTE: Record<string, string> = {
  rules: "one folder per rule, one file per version", rulesets: "one file per ruleset version",
  extractions: "one folder per run of a ruleset", golden: "one folder per publication", assets: "fetched once, by hash",
};
const LIMIT = 100;

export function StorageFiles({ catalog, onClose }: { catalog: string; onClose: () => void }) {
  const { list, error, path, setPath } = useListing(catalog);
  useEscape(onClose);
  return (
    <div className="gfp-bg" onClick={onClose}>
      <div className="gfp sf" onClick={(e) => e.stopPropagation()} role="dialog" aria-label="Storage files">
        <StorageHead list={list} onClose={onClose} />
        <div className="sf-main">
          <FileList list={list} error={error} selected={path} onPick={setPath} />
          <section className="sf-view">{path ? <Preview key={path} catalog={catalog} path={path} /> : null}</section>
        </div>
      </div>
    </div>
  );
}

/** The listed files as a tree of their folders (root-relative paths); folders first, then files, by name. */
export function buildTree(files: FileItem[]): TreeNode {
  const root: TreeNode = { name: "", path: "", children: [], files: 0 };
  for (const f of files) addFile(root, f);
  sortTree(root);
  return root;
}

/** The path as shown in the list: relative to the catalog (or crawl) folder. */
export function shortPath(path: string, catalog: string, crawl: string): string {
  return path.replace(`${catalog}/${crawl}/golden-dataset-studio/`, "")
    .replace(`${catalog}/golden-dataset-studio/`, "").replace(`${catalog}/${crawl}/`, "");
}

/** The listing, and the file picked in it: the annotation log first. */
function useListing(catalog: string) {
  const [list, setList] = useState<Listing | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [path, setPath] = useState<string | null>(null);
  useEffect(() => {
    let live = true;
    get<Listing>(base(catalog)).then((l) => {
      if (!live) return;
      setList(l);
      setPath((p) => p ?? l.files.find((f) => f.path.endsWith("/annotations.jsonl"))?.path ?? l.files[0]?.path ?? null);
    }, (e) => live && setError(String(e.message ?? e)));
    return () => { live = false; };
  }, [catalog]);
  return { list, error, path, setPath };
}

function useEscape(onClose: () => void) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);
}

function useFolderTree(list: Listing) {
  const root = useMemo(() => buildTree(list.files), [list]);
  const [closed, setClosed] = useState<Set<string>>(() => new Set());
  const toggle = (p: string) => setClosed((c) => { const n = new Set(c); if (n.has(p)) n.delete(p); else n.add(p); return n; });
  return { root, closed, toggle };
}

function StorageHead({ list, onClose }: { list: Listing | null; onClose: () => void }) {
  return (
    <div className="gfp-head">
      <StorageTitle list={list} />
      <button className="btn" onClick={onClose} title="Close (Esc)">Close</button>
    </div>
  );
}

function StorageTitle({ list }: { list: Listing | null }) {
  return <div className="sf-title"><b>Storage files</b> <span className="muted">· what the Studio keeps for this catalog, read-only</span>
    {list && <div className="sf-root"><span className="mono" title={list.root}>{list.root}</span>
      {list.portal && <PortalLinks portal={list.portal} />}</div>}</div>;
}

function FileList({ list, error, selected, onPick }: {
  list: Listing | null; error: string | null; selected: string | null; onPick: (p: string) => void }) {
  return (
    <nav className="sf-list" aria-label="Files">
      {error && <div className="muted" style={{ padding: 12 }}>{error}</div>}
      {!list && !error && <div className="muted" style={{ padding: 12 }}>Listing…</div>}
      {list && <FolderTreeView list={list} selected={selected} onPick={onPick} />}
    </nav>
  );
}

function FolderTreeView({ list, selected, onPick }: { list: Listing; selected: string | null; onPick: (p: string) => void }) {
  const tree = useFolderTree(list);
  return (
    <div className="sf-tree" role="tree">
      <div className="sf-row sf-rootrow" title={list.root}><Ico name="folder-open" /><span className="mono">{rootName(list)}/</span></div>
      <Branch nodes={tree.root.children} depth={1} closed={tree.closed} toggle={tree.toggle} selected={selected} onPick={onPick} />
    </div>
  );
}

function Preview({ catalog, path }: { catalog: string; path: string }) {
  const filter = usePreviewFilter();
  const { c, error } = useContent(catalog, path, filter);
  return (
    <>
      <PreviewName c={c} path={path} />
      {c?.about && <div className="sf-about">{c.about}</div>}
      {c && (c.kind === "jsonl" || c.kind === "table") && <PagedBar c={c} filter={filter} />}
      {error && <div className="gfp-body"><span className="muted">{error}</span></div>}
      {!c && !error && <div className="gfp-body"><span className="muted">Loading…</span></div>}
      {c && <ContentBody c={c} />}
    </>
  );
}

function addFile(root: TreeNode, f: FileItem) {
  const parts = f.path.split("/");
  let node = root;
  parts.forEach((_, i) => {
    node.files++;
    node = childFor(node, parts, i, f);
  });
}

function sortTree(n: TreeNode) {
  n.children.sort((a, b) => (a.file ? 1 : 0) - (b.file ? 1 : 0) || a.name.localeCompare(b.name));
  n.children.forEach(sortTree);
}

function PortalLinks({ portal }: { portal: Portal }) {
  return <> · <a href={portal.browser} target="_blank" rel="noopener noreferrer"
    title={`The storage account's Storage browser (sign in to Azure); then Blob containers → ${portal.container} → ${portal.prefix}/`}>
    Storage browser ↗</a>
    {portal.container_url && <> · <a href={portal.container_url} target="_blank" rel="noopener noreferrer"
      title={`The ${portal.container} container in the Azure portal; the files are under ${portal.prefix}/`}>
      container {portal.container} ↗</a></>}</>;
}

function Branch(branch: BranchProps) {
  return (
    <ul className="sf-branch" role="group">
      {branch.nodes.map((n) => (n.file
        ? <FileLeaf key={n.path} node={n} file={n.file} selected={branch.selected} onPick={branch.onPick} />
        : <FolderNode key={n.path} node={n} branch={branch} />))}
    </ul>
  );
}

/** The filter box as typed and the query it settles on a quarter second later, the page, and the log's order. */
function usePreviewFilter() {
  const [q, setQ] = useState("");
  const [query, setQuery] = useState("");
  const [offset, setOffset] = useState(0);
  const [newest, setNewest] = useState(true);
  useEffect(() => { const t = setTimeout(() => { setQuery(q); setOffset(0); }, 250); return () => clearTimeout(t); }, [q]);
  return { q, setQ, query, offset, setOffset, newest, setNewest };
}

function useContent(catalog: string, path: string, { offset, query, newest }: PreviewFilter) {
  const [c, setC] = useState<Content | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    let live = true;
    get<Content>(contentUrl(catalog, path, offset, query, newest)).then((r) => { if (live) { setC(r); setError(null); } },
                                                                      (e) => live && setError(String(e.message ?? e)));
    return () => { live = false; };
  }, [catalog, path, offset, query, newest]);
  return { c, error };
}

function PreviewName({ c, path }: { c: Content | null; path: string }) {
  return <div className="gfp-name mono">{c?.uri ?? path}{c && <span className="muted"> · {kb(c.size)}</span>}
    {c?.portal && <> · <a className="sf-portal" href={c.portal} target="_blank" rel="noopener noreferrer"
      title="This blob in the Azure portal: properties, versions, download (sign in to Azure)">Open in Azure portal ↗</a></>}</div>;
}

function PagedBar({ c, filter: { q, setQ, query, offset, setOffset, newest, setNewest } }: { c: EventsContent | TableContent; filter: PreviewFilter }) {
  return (
    <div className="gfp-bar">
      <input className="gfp-filter" placeholder={c.kind === "jsonl" ? "Filter events: an author, a course code, a rule…" : "Filter rows: any column"}
        value={q} onChange={(e) => setQ(e.target.value)} />
      {c.kind === "jsonl" && <label className="sf-newest"><input type="checkbox" checked={newest}
        onChange={(e) => { setNewest(e.target.checked); setOffset(0); }} /> newest first</label>}
      <span className="muted">{pageRange(c)}
        {query && ` (filtered from ${fmt(c.total)})`}</span>
      <button className="btn" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - LIMIT))}>Previous</button>
      <button className="btn" disabled={offset + LIMIT >= c.matched} onClick={() => setOffset(offset + LIMIT)}>Next</button>
    </div>
  );
}

function ContentBody({ c }: { c: Content }) {
  if (c.kind === "jsonl") return <EventsBody c={c} />;
  if (c.kind === "table") return <TableBody c={c} />;
  return <TextBody c={c} />;
}

function childFor(node: TreeNode, parts: string[], i: number, f: FileItem): TreeNode {
  const isFile = i === parts.length - 1;
  const found = node.children.find((c) => c.name === parts[i] && !c.file === !isFile);
  if (found) return found;
  const child: TreeNode = { name: parts[i], path: parts.slice(0, i + 1).join("/"), children: [], files: 0, ...(isFile ? { file: f } : {}) };
  node.children.push(child);
  return child;
}

function FileLeaf({ node, file, selected, onPick }: { node: TreeNode; file: FileItem; selected: string | null; onPick: (p: string) => void }) {
  return (
    <li role="treeitem" aria-selected={node.path === selected}>
      <button className={"sf-row sf-file" + (node.path === selected ? " on" : "")} title={`${node.path}\n${file.about}`}
        onClick={() => onPick(node.path)}>
        <Ico name="file" /><span className="mono sf-name">{node.name}</span><span className="sf-size">{kb(file.size)}</span>
      </button>
    </li>
  );
}

function FolderNode({ node: n, branch }: { node: TreeNode; branch: BranchProps }) {
  // the selected file's folders always stay open
  const open = !branch.closed.has(n.path) || (!!branch.selected && branch.selected.startsWith(n.path + "/"));
  return (
    <li role="treeitem" aria-expanded={open}>
      <button className="sf-row sf-dir" onClick={() => branch.toggle(n.path)} title={n.path + "/"}>
        <Ico name={open ? "chevron" : "chevron-right"} className="sf-chev" /><Ico name={open ? "folder-open" : "folder"} />
        <span className="mono sf-name">{n.name}/</span>
        {FOLDER_NOTE[n.name] && <span className="sf-note">{FOLDER_NOTE[n.name]}</span>}
        <span className="sf-size">{n.files}</span>
      </button>
      {open && <Branch {...branch} nodes={n.children} depth={branch.depth + 1} />}
    </li>
  );
}

function TextBody({ c }: { c: TextContent }) {
  return (
    <div className="gfp-body">
      {c.truncated && <div className="gfp-note">Showing the first 400 KB.</div>}
      <pre className="gfp-code">{c.kind === "json" ? colorizeJson(c.text) : c.text}</pre>
    </div>
  );
}

function EventsBody({ c }: { c: EventsContent }) {
  return (
    <div className="gfp-body sf-events">
      {c.rows.map((r) => (
        <div key={r.line} className="sf-event">
          <span className="sf-line mono">{r.line}</span>
          <pre className="gfp-code">{colorizeJson(JSON.stringify(r.event, null, 1).replace(/\n\s*/g, " "))}</pre>
        </div>
      ))}
    </div>
  );
}

function TableBody({ c }: { c: TableContent }) {
  return (
    <div className="gfp-body table">
      <div className="gfp-scroll">
        <table className="gfp-table">
          <thead><tr>{c.columns.map((h) => <th key={h}>{h}</th>)}</tr></thead>
          <tbody>{c.rows.map((row, i) => <tr key={i}>{row.map((v, j) => <td key={j} title={cell(v)}>{cell(v)}</td>)}</tr>)}</tbody>
        </table>
      </div>
    </div>
  );
}

function contentUrl(catalog: string, path: string, offset: number, query: string, newest: boolean): string {
  const s = new URLSearchParams({ path, offset: String(offset), limit: String(LIMIT), newest: String(newest) });
  if (query) s.set("q", query);
  return `${base(catalog)}/content?${s}`;
}

function pageRange(c: EventsContent | TableContent): string {
  if (c.matched === 0) return `no ${c.kind === "jsonl" ? "events" : "rows"}`;
  return `${fmt(c.offset + 1)}–${fmt(Math.min(c.offset + LIMIT, c.matched))} of ${fmt(c.matched)}`;
}

function rootName(list: Listing): string {
  return list.root.split("/").filter(Boolean).pop() ?? list.root;
}

function base(catalog: string): string {
  return `/api/catalogs/${encodeURIComponent(catalog)}/files`;
}

async function get<T>(url: string): Promise<T> {
  const r = await fetch(url);
  if (!r.ok) throw new Error((await r.json().catch(() => null))?.detail ?? r.statusText);
  return r.json() as Promise<T>;
}

function kb(n: number): string {
  return n < 1024 ? `${n} B` : n < 1024 * 1024 ? `${fmt(Math.round(n / 1024))} KB` : `${(n / 1048576).toFixed(1)} MB`;
}

function cell(v: unknown): string {
  return v == null ? "null" : typeof v === "object" ? JSON.stringify(v) : String(v);
}
