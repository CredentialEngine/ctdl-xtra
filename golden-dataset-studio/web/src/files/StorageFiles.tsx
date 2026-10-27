// Storage files (routes_files.py): a debugging view of what the Studio keeps for a catalog on its storage root, to
// see how it works under the hood. Opened from the bottom bar, out of the way. Left: the files, grouped (root
// manifest, rules, rulesets, the annotation log, the crawl, extractions, golden publications), each with what it is.
// Right: the selected file: JSON pretty-printed, the log as events (newest first), Parquet as a table; both filterable.
import { useEffect, useMemo, useState } from "react";
import { colorizeJson } from "../golden/FilePreview";
import { fmt } from "../shell/ui";
import "../golden/golden.css";
import "./files.css";

interface FileItem { path: string; size: number; group: string; about: string; portal?: string }
interface Listing { root: string; catalog: string; crawl: string; files: FileItem[];
                    portal: { browser: string; container: string; prefix: string } | null }
interface Head { path: string; uri: string; size: number; about: string; portal: string | null }
type Content = Head & (
  | { kind: "json" | "text"; text: string; truncated: boolean }
  | { kind: "jsonl"; total: number; matched: number; offset: number; rows: { line: number; event: unknown }[] }
  | { kind: "table"; total: number; matched: number; offset: number; columns: string[]; rows: unknown[][] });

const GROUPS = ["Root", "Rules", "Rulesets", "Annotations", "Crawl", "Extractions", "Golden publications"];
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
  const groups = useMemo(() => GROUPS.map((g) => [g, (list?.files ?? []).filter((f) => f.group === g)] as const)
    .filter(([, fs]) => fs.length), [list]);

  return (
    <div className="gfp-bg" onClick={onClose}>
      <div className="gfp sf" onClick={(e) => e.stopPropagation()} role="dialog" aria-label="Storage files">
        <div className="gfp-head">
          <div className="sf-title"><b>Storage files</b> <span className="muted">· what the Studio keeps for this catalog, read-only</span>
            {list && <div className="sf-root"><span className="mono" title={list.root}>{list.root}</span>
              {list.portal && <> · <a href={list.portal.browser} target="_blank" rel="noopener noreferrer"
                title={`The storage account's Storage browser: container ${list.portal.container}, folder ${list.portal.prefix}/ (sign in to Azure)`}>
                Azure portal ↗</a></>}</div>}</div>
          <button className="btn" onClick={onClose} title="Close (Esc)">Close</button>
        </div>
        <div className="sf-main">
          <nav className="sf-list" aria-label="Files">
            {error && <div className="muted" style={{ padding: 12 }}>{error}</div>}
            {!list && !error && <div className="muted" style={{ padding: 12 }}>Listing…</div>}
            {list && groups.map(([g, fs]) => (
              <div key={g} className="sf-group">
                <div className="sf-gh">{g}</div>
                {fs.map((f) => (
                  <button key={f.path} className={"sf-item" + (f.path === path ? " on" : "")} title={`${f.path}\n${f.about}`}
                    onClick={() => setPath(f.path)}>
                    <span className="mono sf-name">{shortPath(f.path, list.catalog, list.crawl)}</span>
                    <span className="sf-size">{kb(f.size)}</span>
                  </button>
                ))}
              </div>
            ))}
          </nav>
          <section className="sf-view">{path ? <Preview key={path} catalog={catalog} path={path} /> : null}</section>
        </div>
      </div>
    </div>
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
