// Samples of what a golden dataset version wrote, file by file: a page's <stem>.json in each tree (and at the latest
// location), its <stem>.html, publication.json, lineage.parquet and golden.parquet. Opened from the file names in the
// Golden datasets tab's tree. Read-only.
import { useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import { api } from "../api/client";
import type { GoldenFileText, GoldenLineage } from "../api/types";
import { colorize } from "../pagepane/SourceView";
import { fmt } from "../shell/ui";

export type GoldenFile = "rule-matched.json" | "human-reviewed.json" | "page.json" | "page.html" | "publication.json"
  | "lineage.parquet" | "golden.parquet";
/** The tree a page file is read from ("latest": the latest location). */
const TREE: Partial<Record<GoldenFile, string>> = { "rule-matched.json": "rule-matched", "human-reviewed.json": "human-reviewed",
                                                    "page.json": "latest", "page.html": "latest" };
/** What each file is, beside its name. */
const FILE_NOTE: Partial<Record<GoldenFile, string>> = {
  "rule-matched.json": "every value with a CTDL term",
  "human-reviewed.json": "only the values a subject matter expert reviewed (approval: human)",
  "page.json": "the latest version's rule-matched file, where readers look today",
  "page.html": "the page as crawled, only at the latest location",
  "lineage.parquet": "stays in the Studio; never copied to the golden container",
  "golden.parquet": "every value of this version as published, for Evals",
};
const JSON_TOKEN = /("(?:[^"\\]|\\.)*")(\s*:)?|(-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)|\b(true|false|null)\b/g;
const LIMIT = 100;

interface FilePreviewProps { catalog: string; version: string; latest: boolean; file: GoldenFile; initialStem?: string; onClose: () => void }
type Pages = ReturnType<typeof usePageStems>;
type TableName = "lineage" | "golden";
type TableFilter = ReturnType<typeof useDebouncedFilter>;
interface FileText { f: GoldenFileText | null; error?: string }

export function FilePreview({ catalog, version, latest, file, initialStem, onClose }: FilePreviewProps) {
  const { which, setWhich, pages, name, openPage } = usePreviewedFile(catalog, version, file, initialStem);
  useEscape(onClose);
  return (
    <div className="gfp-bg" onClick={onClose}>
      <div className="gfp" onClick={(e) => e.stopPropagation()} role="dialog" aria-label={`Sample of ${name}`}>
        <PreviewHead which={which} latest={latest} onPick={setWhich} onClose={onClose} />
        {pages.tree && <PageBar pages={pages} />}
        <div className="gfp-name mono">{name}{FILE_NOTE[which] && <span className="muted">{` · ${FILE_NOTE[which]}`}</span>}</div>
        <FileBody catalog={catalog} version={version} which={which} pages={pages} onPage={openPage} />
      </div>
    </div>
  );
}

/** Colour a JSON text: keys, strings, numbers and literals. The text is never interpreted as HTML. */
export function colorizeJson(text: string): ReactNode[] {
  const out: ReactNode[] = [];
  let last = 0;
  let key = 0;
  for (const m of text.matchAll(JSON_TOKEN)) {
    const at = m.index ?? 0;
    if (at > last) out.push(text.slice(last, at));
    out.push(...jsonToken(m, key++));
    last = at + m[0].length;
  }
  if (last < text.length) out.push(text.slice(last));
  return out;
}

/** The file shown, its page, and its name; a page picked in a table opens its silver <page>.json. */
function usePreviewedFile(catalog: string, version: string, file: GoldenFile, initialStem: string | undefined) {
  const [which, setWhich] = useState<GoldenFile>(file);
  const pages = usePageStems(catalog, version, TREE[which], initialStem);
  const openPage = (stem: string) => { pages.setStem(stem); setWhich("rule-matched.json"); };
  return { which, setWhich, pages, openPage, name: fileName(which, pages.tree, pages.stem) };
}

/** The pages of the file's tree, the one shown, and the text typed in the Page box. */
function usePageStems(catalog: string, version: string, tree: string | undefined, initialStem: string | undefined) {
  const [stems, setStems] = useState<Record<string, string[]>>({});
  const list = tree ? stems[tree] : undefined;
  const [stem, setStem] = useState(initialStem ?? "");
  const [typed, setTyped] = useState(stem);
  useEffect(() => setTyped(stem), [stem]);
  useEffect(() => {
    if (!tree || stems[tree]) return;
    api.goldenStems(catalog, version, tree).then((s) => setStems((m) => ({ ...m, [tree]: s })), () => setStems((m) => ({ ...m, [tree]: [] })));
  }, [catalog, version, tree, stems]);
  useEffect(() => { if (list && list.length && !list.includes(stem)) setStem(list[0]); }, [list, stem]);
  const at = list ? list.indexOf(stem) : -1;
  const step = (d: number) => { if (list?.length) setStem(list[(at + d + list.length) % list.length]); };
  return { tree, list, stem, setStem, typed, setTyped, at, step, ready: !!tree && !!list && list.includes(stem) };
}

function useEscape(onClose: () => void) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);
}

function fileName(which: GoldenFile, tree: string | undefined, stem: string): string {
  if (!tree) return which;
  return `${tree === "latest" ? "" : `${tree}/…/`}${stem || "<page>"}/${stem || "<page>"}.${which === "page.html" ? "html" : "json"}`;
}

function PreviewHead({ which, latest, onPick, onClose }: { which: GoldenFile; latest: boolean; onPick: (f: GoldenFile) => void; onClose: () => void }) {
  return (
    <div className="gfp-head">
      <div className="gfp-tabs">{fileTabs(latest).map(([f, label]) => (
        <button key={f} className={`gfp-tab mono ${f === which ? "on" : ""}`} onClick={() => onPick(f)}>{label}</button>))}
      </div>
      <button className="btn" onClick={onClose} title="Close (Esc)">Close</button>
    </div>
  );
}

function PageBar({ pages: { list, at, typed, setTyped, setStem, step } }: { pages: Pages }) {
  const type = (value: string) => { setTyped(value); if (list?.includes(value)) setStem(value); };
  return (
    <div className="gfp-bar">
      <span className="muted">Page</span>
      <input className="gfp-filter mono" list="gfp-stems" value={typed} onChange={(e) => type(e.target.value)} />
      <datalist id="gfp-stems">{(list ?? []).map((s) => <option key={s} value={s} />)}</datalist>
      <span className="muted">{list ? (at >= 0 ? `${fmt(at + 1)} of ${fmt(list.length)} pages` : `${fmt(list.length)} pages`) : "Loading…"}</span>
      <button className="btn" onClick={() => step(-1)}>Previous</button>
      <button className="btn" onClick={() => step(1)}>Next</button>
    </div>
  );
}

function FileBody({ catalog, version, which, pages: { tree, list, stem, ready }, onPage }: {
  catalog: string; version: string; which: GoldenFile; pages: Pages; onPage: (stem: string) => void }) {
  return <>
    {tree && list && !list.length && <div className="gfp-body"><span className="muted">No pages in this tree.</span></div>}
    {ready && which !== "page.html" && <TextFile load={() => api.goldenPageJson(catalog, version, stem, tree!)} deps={[catalog, version, stem, tree]} />}
    {ready && which === "page.html" && <TextFile html load={() => api.goldenPageHtml(catalog, version, stem)} deps={[catalog, version, stem]} />}
    {which === "publication.json" && <TextFile load={() => api.goldenPublicationJson(catalog, version)} deps={[catalog, version]} />}
    {(which === "lineage.parquet" || which === "golden.parquet") &&
      <TableFile key={which} catalog={catalog} version={version} table={which === "lineage.parquet" ? "lineage" : "golden"} onPage={onPage} />}
  </>;
}

function jsonToken(m: RegExpMatchArray, key: number): ReactNode[] {
  if (m[1]) return m[2] ? [<span key={key} className="k">{m[1]}</span>, m[2]] : [<span key={key} className="s">{m[1]}</span>];
  if (m[3]) return [<span key={key} className="n">{m[3]}</span>];
  return [<span key={key} className="l">{m[4]}</span>];
}

function fileTabs(latest: boolean): [GoldenFile, string][] {
  return [["rule-matched.json", "silver/<page>.json"], ["human-reviewed.json", "golden/<page>.json"],
    ...(latest ? [["page.json", "latest <page>.json"], ["page.html", "<page>.html"]] as [GoldenFile, string][] : []),
    ["publication.json", "publication.json"], ["lineage.parquet", "lineage.parquet"], ["golden.parquet", "golden.parquet"]];
}

function TextFile({ load, html, deps }: { load: () => Promise<GoldenFileText>; html?: boolean; deps: unknown[] }) {
  const r = useFileText(load, deps);
  const body = useMemo(() => (r?.f ? highlighted(r.f.text, html) : null), [r, html]);
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

function TableFile({ catalog, version, table, onPage }: { catalog: string; version: string; table: TableName; onPage: (stem: string) => void }) {
  const filter = useDebouncedFilter();
  const { d, error } = useTablePage(catalog, version, table, filter.query, filter.offset);
  if (error) return <div className="gfp-body"><span className="muted">{error}</span></div>;
  if (!d) return <div className="gfp-body"><span className="muted">Loading…</span></div>;
  return (
    <div className="gfp-body table">
      <TableBar d={d} filter={filter} />
      <div className="gfp-scroll">
        <TableRows d={d} onPage={onPage} />
      </div>
    </div>
  );
}

function useFileText(load: () => Promise<GoldenFileText>, deps: unknown[]): FileText | null {
  const [r, setR] = useState<FileText | null>(null);
  useEffect(() => {
    let live = true;
    setR(null);
    load().then((f) => live && setR({ f }), (e) => live && setR({ f: null, error: String(e) }));
    return () => { live = false; };
  }, deps); // eslint-disable-line react-hooks/exhaustive-deps
  return r;
}

function highlighted(text: string, html: boolean | undefined): ReactNode {
  if (!html) return colorizeJson(text);
  return text.split("\n").map((line, n) => (
    <div key={n} className="ln"><span className="no">{n + 1}</span><span>{colorize(line, `l${n}`)}</span></div>));
}

/** The filter box as typed, and the query it settles on a quarter second later (back to the first page). */
function useDebouncedFilter() {
  const [q, setQ] = useState("");
  const [query, setQuery] = useState("");
  const [offset, setOffset] = useState(0);
  useEffect(() => { const t = setTimeout(() => { setQuery(q); setOffset(0); }, 250); return () => clearTimeout(t); }, [q]);
  return { q, setQ, query, offset, setOffset };
}

function useTablePage(catalog: string, version: string, table: TableName, query: string, offset: number) {
  const [d, setD] = useState<GoldenLineage | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    let live = true;
    setD(null);
    api.goldenTable(catalog, version, table, { q: query || undefined, offset, limit: LIMIT })
      .then((r) => live && setD(r), (e) => live && setError(String(e)));
    return () => { live = false; };
  }, [catalog, version, table, query, offset]);
  return { d, error };
}

function TableBar({ d, filter: { q, setQ, query, offset, setOffset } }: { d: GoldenLineage; filter: TableFilter }) {
  return (
    <div className="gfp-bar">
      <input className="gfp-filter" placeholder="Filter rows: a golden_record_id, page, property, rule…" value={q}
             onChange={(e) => setQ(e.target.value)} autoFocus />
      <span className="muted">
        {d.matched === 0 ? "no rows" : `rows ${fmt(d.offset + 1)}–${fmt(Math.min(d.offset + LIMIT, d.matched))} of ${fmt(d.matched)}`}
        {query && ` (filtered from ${fmt(d.total)})`}</span>
      <button className="btn" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - LIMIT))}>Previous</button>
      <button className="btn" disabled={offset + LIMIT >= d.matched} onClick={() => setOffset(offset + LIMIT)}>Next</button>
    </div>
  );
}

function TableRows({ d, onPage }: { d: GoldenLineage; onPage: (stem: string) => void }) {
  const stemCol = Math.max(d.columns.indexOf("page_stem"), d.columns.indexOf("stem"));
  return (
    <table className="gfp-table">
      <thead><tr>{d.columns.map((c) => <th key={c}>{c}</th>)}</tr></thead>
      <tbody>{d.rows.map((row, i) => (
        <tr key={i}>{row.map((v, j) => <TableCell key={j} value={v} isStem={j === stemCol} onPage={onPage} />)}</tr>))}
      </tbody>
    </table>
  );
}

function TableCell({ value, isStem, onPage }: { value: unknown; isStem: boolean; onPage: (stem: string) => void }) {
  return <td title={cell(value)}>{isStem
    ? <button className="gfp-link" onClick={() => onPage(String(value))} title={`Open ${value}.json`}>{cell(value)}</button>
    : cell(value)}</td>;
}

function kb(n?: number): string {
  return n == null ? "" : n < 1024 ? `${n} B` : `${fmt(Math.round(n / 1024))} KB`;
}

function cell(v: unknown): string {
  return Array.isArray(v) ? v.join(", ") : v == null ? "null" : String(v);
}
