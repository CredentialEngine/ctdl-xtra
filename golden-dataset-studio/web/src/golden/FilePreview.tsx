// "What will be written", file by file: a page's <stem>.json and <stem>.html, lineage.parquet's rows and
// publication.json, each as the publication would write it. Opened from the file names in the Golden tab's tree.
import { useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import { api } from "../api/client";
import type { GoldenFileText, GoldenLineage } from "../api/types";
import { colorize } from "../pagepane/SourceView";
import { fmt } from "../shell/ui";

export type GoldenFile = "page.json" | "page.html" | "lineage.parquet" | "publication.json";

const JSON_TOKEN = /("(?:[^"\\]|\\.)*")(\s*:)?|(-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)|\b(true|false|null)\b/g;

/** Colour a JSON text: keys, strings, numbers and literals. The text is never interpreted as HTML. */
export function colorizeJson(text: string): ReactNode[] {
  const out: ReactNode[] = [];
  let last = 0;
  let i = 0;
  for (const m of text.matchAll(JSON_TOKEN)) {
    const at = m.index ?? 0;
    if (at > last) out.push(text.slice(last, at));
    if (m[1]) {
      out.push(<span key={i++} className={m[2] ? "k" : "s"}>{m[1]}</span>);
      if (m[2]) out.push(m[2]);
    } else if (m[3]) {
      out.push(<span key={i++} className="n">{m[3]}</span>);
    } else {
      out.push(<span key={i++} className="l">{m[4]}</span>);
    }
    last = at + m[0].length;
  }
  if (last < text.length) out.push(text.slice(last));
  return out;
}

const kb = (n?: number) => (n == null ? "" : n < 1024 ? `${n} B` : `${fmt(Math.round(n / 1024))} KB`);
const cell = (v: unknown) => (Array.isArray(v) ? v.join(", ") : v == null ? "null" : String(v));

function TextFile({ load, html, deps }: { load: () => Promise<GoldenFileText>; html?: boolean; deps: unknown[] }) {
  const [r, setR] = useState<{ f: GoldenFileText | null; error?: string } | null>(null);
  useEffect(() => {
    let live = true;
    setR(null);
    load().then((f) => live && setR({ f }), (e) => live && setR({ f: null, error: String(e) }));
    return () => { live = false; };
  }, deps); // eslint-disable-line react-hooks/exhaustive-deps
  const body = useMemo(() => {
    if (!r?.f) return null;
    if (!html) return colorizeJson(r.f.text);
    return r.f.text.split("\n").map((line, n) => (
      <div key={n} className="ln"><span className="no">{n + 1}</span><span>{colorize(line, `l${n}`)}</span></div>));
  }, [r, html]);
  if (!r) return <div className="gfp-body"><span className="muted">Loading…</span></div>;
  if (!r.f) return <div className="gfp-body"><span className="muted">{r.error}</span></div>;
  return (
    <div className="gfp-body">
      {r.f.truncated && <div className="gfp-note">Showing the first {kb(400_000)} of {kb(r.f.bytes)}. The whole page is written.</div>}
      {r.f.truncated_page_stems && <div className="gfp-note">page_stems is cut to 20 here; the file lists every page.</div>}
      <pre className="gfp-code">{body}</pre>
    </div>
  );
}

function LineageTable({ catalog, properties, onPage }: { catalog: string; properties: string[]; onPage: (stem: string) => void }) {
  const [q, setQ] = useState("");
  const [query, setQuery] = useState("");
  const [offset, setOffset] = useState(0);
  const [d, setD] = useState<GoldenLineage | null>(null);
  const [error, setError] = useState<string | null>(null);
  const limit = 100;
  useEffect(() => { const t = setTimeout(() => { setQuery(q); setOffset(0); }, 250); return () => clearTimeout(t); }, [q]);
  useEffect(() => {
    let live = true;
    api.goldenLineage(catalog, { q: query || undefined, offset, limit, properties: properties.join(",") })
      .then((r) => live && setD(r), (e) => live && setError(String(e)));
    return () => { live = false; };
  }, [catalog, query, offset, properties]);
  if (error) return <div className="gfp-body"><span className="muted">{error}</span></div>;
  if (!d) return <div className="gfp-body"><span className="muted">Loading…</span></div>;
  const stemCol = d.columns.indexOf("page_stem");
  return (
    <div className="gfp-body table">
      <div className="gfp-bar">
        <input className="gfp-filter" placeholder="Filter rows: a golden_record_id, page, property, rule…" value={q}
               onChange={(e) => setQ(e.target.value)} autoFocus />
        <span className="muted">
          {d.matched === 0 ? "no rows" : `rows ${fmt(d.offset + 1)}–${fmt(Math.min(d.offset + limit, d.matched))} of ${fmt(d.matched)}`}
          {query && ` (filtered from ${fmt(d.total)})`}</span>
        <button className="btn" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - limit))}>Previous</button>
        <button className="btn" disabled={offset + limit >= d.matched} onClick={() => setOffset(offset + limit)}>Next</button>
      </div>
      <div className="gfp-scroll">
        <table className="gfp-table">
          <thead><tr>{d.columns.map((c) => <th key={c}>{c}</th>)}</tr></thead>
          <tbody>{d.rows.map((row, i) => (
            <tr key={i}>{row.map((v, j) => (
              <td key={j} title={cell(v)}>{j === stemCol
                ? <button className="gfp-link" onClick={() => onPage(String(v))} title={`Open ${v}.json`}>{cell(v)}</button>
                : cell(v)}</td>))}</tr>))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export function FilePreview({ catalog, file, stems, initialStem, author, properties, onClose }: {
  catalog: string; file: GoldenFile; stems: { stem: string; records: number }[]; initialStem?: string; author: string;
  properties: string[]; onClose: () => void;
}) {
  const [which, setWhich] = useState<GoldenFile>(file);
  const [stem, setStem] = useState(initialStem ?? stems[0]?.stem ?? "");
  const [typed, setTyped] = useState(stem);
  useEffect(() => setTyped(stem), [stem]);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const perPage = which === "page.json" || which === "page.html";
  const at = stems.findIndex((s) => s.stem === stem);
  const step = (d: number) => { const n = stems[(at + d + stems.length) % stems.length]; if (n) setStem(n.stem); };
  const name = perPage ? `${stem}/${stem}.${which === "page.json" ? "json" : "html"}` : which;
  const tabs: [GoldenFile, string][] = [["page.json", "<page>.json"], ["page.html", "<page>.html"],
    ["lineage.parquet", "lineage.parquet"], ["publication.json", "publication.json"]];

  return (
    <div className="gfp-bg" onClick={onClose}>
      <div className="gfp" onClick={(e) => e.stopPropagation()} role="dialog" aria-label={`Preview of ${name}`}>
        <div className="gfp-head">
          <div className="gfp-tabs">{tabs.map(([f, label]) => (
            <button key={f} className={`gfp-tab mono ${f === which ? "on" : ""}`} onClick={() => setWhich(f)}>{label}</button>))}
          </div>
          <button className="btn" onClick={onClose} title="Close (Esc)">Close</button>
        </div>
        {perPage && (
          <div className="gfp-bar">
            <span className="muted">Page</span>
            <input className="gfp-filter mono" list="gfp-stems" value={typed} onChange={(e) => {
              setTyped(e.target.value);
              if (stems.some((s) => s.stem === e.target.value)) setStem(e.target.value);
            }} />
            <datalist id="gfp-stems">{stems.map((s) => <option key={s.stem} value={s.stem}>{s.records} course entries</option>)}</datalist>
            <span className="muted">{at >= 0 ? `${fmt(at + 1)} of ${fmt(stems.length)} · ${stems[at].records} course entries` : ""}</span>
            <button className="btn" onClick={() => step(-1)}>Previous</button>
            <button className="btn" onClick={() => step(1)}>Next</button>
          </div>)}
        <div className="gfp-name mono">{name}{which === "page.json" && <span className="muted"> · {properties.join(", ")} from this
          extraction; other properties as the golden set has them</span>}
          {which === "page.html" && <span className="muted"> · the page as crawled, copied as is</span>}
          {which === "publication.json" && <span className="muted"> · as it would be written now</span>}
          {which === "lineage.parquet" && <span className="muted"> · stays in the Studio; never copied to the golden container</span>}</div>
        {which === "page.json" && <TextFile load={() => api.goldenPageJson(catalog, stem, properties)} deps={[catalog, stem, properties.join()]} />}
        {which === "page.html" && <TextFile html load={() => api.goldenPageHtml(catalog, stem, properties)} deps={[catalog, stem, properties.join()]} />}
        {which === "publication.json" && <TextFile load={() => api.goldenPublicationJson(catalog, author, properties)} deps={[catalog, author, properties.join()]} />}
        {which === "lineage.parquet" && <LineageTable catalog={catalog} properties={properties} onPage={(s) => { setStem(s); setWhich("page.json"); }} />}
      </div>
    </div>
  );
}
