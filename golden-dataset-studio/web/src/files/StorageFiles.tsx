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
interface Listing { root: string; catalog: string; crawl: string; files: FileItem[];
                    portal: { browser: string; container_url?: string; container: string; prefix: string } | null }
interface Head { path: string; uri: string; size: number; about: string; portal: string | null }
type Content = Head & (
  | { kind: "json" | "text"; text: string; truncated: boolean }
  | { kind: "jsonl"; total: number; matched: number; offset: number; rows: { line: number; event: unknown }[] }
  | { kind: "table"; total: number; matched: number; offset: number; columns: string[]; rows: unknown[][] });

/** A short note after some folders, to read the layout at a glance. */
const FOLDER_NOTE: Record<string, string> = {
  rules: "one folder per rule, one file per version", rulesets: "one file per ruleset version",
  extractions: "one folder per run of a ruleset", golden: "one folder per publication", assets: "fetched once, by hash",
};

export interface TreeNode { name: string; path: string; file?: FileItem; children: TreeNode[]; files: number }

/** The listed files as a tree of their folders (root-relative paths); folders first, then files, by name. */
export function buildTree(files: FileItem[]): TreeNode {
  const root: TreeNode = { name: "", path: "", children: [], files: 0 };
  for (const f of files) {
    const parts = f.path.split("/");
    let node = root;
    parts.forEach((part, i) => {
      node.files++;
      const path = parts.slice(0, i + 1).join("/");
      let child = node.children.find((c) => c.name === part && !c.file === (i < parts.length - 1));
      if (!child) {
        child = { name: part, path, children: [], files: 0, ...(i === parts.length - 1 ? { file: f } : {}) };
        node.children.push(child);
      }
      node = child;
    });
  }
  const sort = (n: TreeNode) => {
    n.children.sort((a, b) => (a.file ? 1 : 0) - (b.file ? 1 : 0) || a.name.localeCompare(b.name));
    n.children.forEach(sort);
  };
  sort(root);
  return root;
}
const LIMIT = 100;
const base = (c: string) => `/api/catalogs/${encodeURIComponent(c)}/files`;
async function get<T>(url: string): Promise<T> {
  const r = await fetch(url);
  if (!r.ok) throw new Error((await r.json().catch(() => null))?.detail ?? r.statusText);
  return r.json() as Promise<T>;
}
const kb = (n: number) => (n < 1024 ? `${n} B` : n < 1024 * 1024 ? `${fmt(Math.round(n / 1024))} KB` : `${(n / 1048576).toFixed(1)} MB`);
const cell = (v: unknown) => (v == null ? "null" : typeof v === "object" ? JSON.stringify(v) : String(v));

/** The path as shown in the list: relative to the catalog (or crawl) folder. */
export function shortPath(path: string, catalog: string, crawl: string): string {
  return path.replace(`${catalog}/${crawl}/golden-dataset-studio/`, "")
    .replace(`${catalog}/golden-dataset-studio/`, "").replace(`${catalog}/${crawl}/`, "");
}

export function StorageFiles({ catalog, onClose }: { catalog: string; onClose: () => void }) {
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
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);
  const tree = useMemo(() => buildTree(list?.files ?? []), [list]);
  const [closed, setClosed] = useState<Set<string>>(() => new Set());
  const toggle = (p: string) => setClosed((c) => { const n = new Set(c); if (n.has(p)) n.delete(p); else n.add(p); return n; });
  const rootName = list ? (list.root.split("/").filter(Boolean).pop() ?? list.root) : "";

  return (
    <div className="gfp-bg" onClick={onClose}>
      <div className="gfp sf" onClick={(e) => e.stopPropagation()} role="dialog" aria-label="Storage files">
        <div className="gfp-head">
          <div className="sf-title"><b>Storage files</b> <span className="muted">· what the Studio keeps for this catalog, read-only</span>
            {list && <div className="sf-root"><span className="mono" title={list.root}>{list.root}</span>
              {list.portal && <> · <a href={list.portal.browser} target="_blank" rel="noopener noreferrer"
                title={`The storage account's Storage browser (sign in to Azure); then Blob containers → ${list.portal.container} → ${list.portal.prefix}/`}>
                Storage browser ↗</a>
                {list.portal.container_url && <> · <a href={list.portal.container_url} target="_blank" rel="noopener noreferrer"
                  title={`The ${list.portal.container} container in the Azure portal; the files are under ${list.portal.prefix}/`}>
                  container {list.portal.container} ↗</a></>}</>}</div>}</div>
          <button className="btn" onClick={onClose} title="Close (Esc)">Close</button>
        </div>
        <div className="sf-main">
          <nav className="sf-list" aria-label="Files">
            {error && <div className="muted" style={{ padding: 12 }}>{error}</div>}
            {!list && !error && <div className="muted" style={{ padding: 12 }}>Listing…</div>}
            {list && (
              <div className="sf-tree" role="tree">
                <div className="sf-row sf-rootrow" title={list.root}><Ico name="folder-open" /><span className="mono">{rootName}/</span></div>
                <Branch nodes={tree.children} depth={1} closed={closed} toggle={toggle} selected={path} onPick={setPath} />
              </div>
            )}
          </nav>
          <section className="sf-view">{path ? <Preview key={path} catalog={catalog} path={path} /> : null}</section>
        </div>
      </div>
    </div>
  );
}

function Branch({ nodes, depth, closed, toggle, selected, onPick }: {
  nodes: TreeNode[]; depth: number; closed: Set<string>; toggle: (p: string) => void; selected: string | null;
  onPick: (p: string) => void;
}) {
  return (
    <ul className="sf-branch" role="group">
      {nodes.map((n) => {
        if (n.file) {
          return (
            <li key={n.path} role="treeitem" aria-selected={n.path === selected}>
              <button className={"sf-row sf-file" + (n.path === selected ? " on" : "")} title={`${n.path}\n${n.file.about}`}
                onClick={() => onPick(n.path)}>
                <Ico name="file" /><span className="mono sf-name">{n.name}</span><span className="sf-size">{kb(n.file.size)}</span>
              </button>
            </li>
          );
        }
        // the selected file's folders always stay open
        const open = !closed.has(n.path) || (!!selected && selected.startsWith(n.path + "/"));
        return (
          <li key={n.path} role="treeitem" aria-expanded={open}>
            <button className="sf-row sf-dir" onClick={() => toggle(n.path)} title={n.path + "/"}>
              <span className="sf-chev">{open ? "▾" : "▸"}</span><Ico name={open ? "folder-open" : "folder"} />
              <span className="mono sf-name">{n.name}/</span>
              {FOLDER_NOTE[n.name] && <span className="sf-note">{FOLDER_NOTE[n.name]}</span>}
              <span className="sf-size">{n.files}</span>
            </button>
            {open && <Branch nodes={n.children} depth={depth + 1} closed={closed} toggle={toggle} selected={selected} onPick={onPick} />}
          </li>
        );
      })}
    </ul>
  );
}

function Preview({ catalog, path }: { catalog: string; path: string }) {
  const [q, setQ] = useState("");
  const [query, setQuery] = useState("");
  const [offset, setOffset] = useState(0);
  const [newest, setNewest] = useState(true);
  const [c, setC] = useState<Content | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => { const t = setTimeout(() => { setQuery(q); setOffset(0); }, 250); return () => clearTimeout(t); }, [q]);
  useEffect(() => {
    let live = true;
    const s = new URLSearchParams({ path, offset: String(offset), limit: String(LIMIT), newest: String(newest) });
    if (query) s.set("q", query);
    get<Content>(`${base(catalog)}/content?${s}`).then((r) => { if (live) { setC(r); setError(null); } },
                                                       (e) => live && setError(String(e.message ?? e)));
    return () => { live = false; };
  }, [catalog, path, offset, query, newest]);
  const paged = c && (c.kind === "jsonl" || c.kind === "table");
  return (
    <>
      <div className="gfp-name mono">{c?.uri ?? path}{c && <span className="muted"> · {kb(c.size)}</span>}
        {c?.portal && <> · <a className="sf-portal" href={c.portal} target="_blank" rel="noopener noreferrer"
          title="This blob in the Azure portal: properties, versions, download (sign in to Azure)">Open in Azure portal ↗</a></>}</div>
      {c?.about && <div className="sf-about">{c.about}</div>}
      {paged && (
        <div className="gfp-bar">
          <input className="gfp-filter" placeholder={c.kind === "jsonl" ? "Filter events: an author, a course code, a rule…" : "Filter rows: any column"}
            value={q} onChange={(e) => setQ(e.target.value)} />
          {c.kind === "jsonl" && <label className="sf-newest"><input type="checkbox" checked={newest}
            onChange={(e) => { setNewest(e.target.checked); setOffset(0); }} /> newest first</label>}
          <span className="muted">{c.matched === 0 ? `no ${c.kind === "jsonl" ? "events" : "rows"}`
            : `${fmt(c.offset + 1)}–${fmt(Math.min(c.offset + LIMIT, c.matched))} of ${fmt(c.matched)}`}
            {query && ` (filtered from ${fmt(c.total)})`}</span>
          <button className="btn" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - LIMIT))}>Previous</button>
          <button className="btn" disabled={offset + LIMIT >= c.matched} onClick={() => setOffset(offset + LIMIT)}>Next</button>
        </div>
      )}
      {error && <div className="gfp-body"><span className="muted">{error}</span></div>}
      {!c && !error && <div className="gfp-body"><span className="muted">Loading…</span></div>}
      {c && (c.kind === "json" || c.kind === "text") && (
        <div className="gfp-body">
          {c.truncated && <div className="gfp-note">Showing the first 400 KB.</div>}
          <pre className="gfp-code">{c.kind === "json" ? colorizeJson(c.text) : c.text}</pre>
        </div>
      )}
      {c && c.kind === "jsonl" && (
        <div className="gfp-body sf-events">
          {c.rows.map((r) => (
            <div key={r.line} className="sf-event">
              <span className="sf-line mono">{r.line}</span>
              <pre className="gfp-code">{colorizeJson(JSON.stringify(r.event, null, 1).replace(/\n\s*/g, " "))}</pre>
            </div>
          ))}
        </div>
      )}
      {c && c.kind === "table" && (
        <div className="gfp-body table">
          <div className="gfp-scroll">
            <table className="gfp-table">
              <thead><tr>{c.columns.map((h) => <th key={h}>{h}</th>)}</tr></thead>
              <tbody>{c.rows.map((row, i) => <tr key={i}>{row.map((v, j) => <td key={j} title={cell(v)}>{cell(v)}</td>)}</tr>)}</tbody>
            </table>
          </div>
        </div>
      )}
    </>
  );
}
