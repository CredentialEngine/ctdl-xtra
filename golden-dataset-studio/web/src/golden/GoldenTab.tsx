// Datasets (Evals spec §6.6, m4b; property-rules spec §4.16): a read-only record of the two datasets. The golden dataset is
// only the values an expert reviewed, by property, as they are now. The silver datasets are one per ruleset version (every
// value an approved rule found, also called the rule-matched dataset): its columns, values and where it's written. Approving
// a rule publishes its silver dataset (Rules tab), so there's no Publish button here. "Where these files are" opens where
// the chosen version is written, each file a link to a sample.
import { useCallback, useEffect, useState } from "react";
import { api } from "../api/client";
import type { CatalogDetail, ClassSummary, GoldenResponse, GoldenTree, GoldenVersion } from "../api/types";
import { inClass } from "../shell/klass";
import { CLASS_NAME, currentClass, replaceParam, type ClassSlug } from "../shell/router";
import type { TabProps } from "../shell/tabProps";
import { fmt, useKeyHints } from "../shell/ui";
import { FilePreview } from "./FilePreview";
import type { GoldenFile } from "./FilePreview";
import "./golden.css";

/** One class's datasets with All classes: its name and what it has published, over its two sections. */
interface ClassData { cls: ClassSlug; name: string; properties: number; d: GoldenResponse | null; error?: string }
interface ClassDatasetsProps { catalog: string; d: GoldenResponse; cls: ClassSlug; name: string; chosenId: string | null }
interface SilverProps {
  d: GoldenResponse; name: string; version: GoldenVersion; whereOpen: boolean;
  onChoose: (id: string) => void; onOpenWhere: () => void; onCloseWhere: () => void; onOpenFile: (f: GoldenFile) => void;
}
type Part = string | { f: GoldenFile; label: string } | { b: string };
type TreeLine = [Part[], string?];

export default function GoldenTab({ catalog, route }: TabProps) {
  const all = route.cls === "all";
  const { d, each, error } = useDatasets(catalog, all);
  usePublishHint(catalog.short, all ? "CLASS" : route.cls);
  if (error) return <div className="doc"><div className="doc-in"><p className="muted">{error}</p></div></div>;
  if (all) return each ? <AllClassesDatasets catalog={catalog} each={each} /> : <LoadingDoc />;
  if (!d) return <LoadingDoc />;
  return (
    <div className="doc"><div className="doc-in">
      <DatasetsHead />
      <ClassDatasets catalog={catalog.short} d={d} cls={route.cls as ClassSlug} name={CLASS_NAME[route.cls]}
        chosenId={route.params.get("v")} />
    </div></div>
  );
}

function useDatasets(catalog: CatalogDetail, all: boolean) {
  const [d, setD] = useState<GoldenResponse | null>(null);
  const [each, setEach] = useState<ClassData[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const classes = catalog.classes ?? [];
  const classesKey = classes.map((c) => `${c.slug}:${c.ruleset_version}`).join(",");
  const load = useCallback(() => {
    if (!all) { api.golden(catalog.short).then(setD, (e) => setError(String(e))); return; }
    loadEachClass(catalog.short, classes).then(setEach);
  }, [catalog.short, all, classesKey]);
  useEffect(load, [load]);
  return { d, each, error };
}

function usePublishHint(cat: string, cls: string) {
  useKeyHints(<span>Approving a rule on the Rules tab publishes its silver dataset. Engineers can also run{" "}
    <span className="mono">golden-datasets golden publish --catalog {cat} --class {cls} --property NAME</span></span>,
    [cat, cls]);
}

function AllClassesDatasets({ catalog, each }: { catalog: CatalogDetail; each: ClassData[] }) {
  return (
    <div className="doc"><div className="doc-in">
      <DatasetsHead />
      {each.map((x) => <ClassSection key={x.cls} catalog={catalog} data={x} />)}
    </div></div>
  );
}

function LoadingDoc() {
  return <div className="doc"><div className="doc-in"><h1>Datasets</h1></div></div>;
}

function DatasetsHead() {
  return <div className="gv-head"><h1>Datasets</h1><span className="muted">Approving a rule publishes its silver dataset. The golden dataset changes only when an expert gives a verdict.</span></div>;
}

/** One class's golden dataset and silver datasets, with where a version's files are. */
function ClassDatasets({ catalog, d, cls, name, chosenId }: ClassDatasetsProps) {
  const [open, setOpen] = useState<GoldenFile | null>(null);
  const [chosen, setChosen] = useState<string | null>(chosenId);
  const { where, openWhere, closeWhere } = useWhereModal(cls, !!open);
  const v = d.versions.find((x) => x.id === chosen) ?? d.versions[0];
  return (
    <>
      {open && v && <FilePreview catalog={catalog} version={v.id} latest={v.latest} file={open} onClose={() => setOpen(null)} />}
      <GoldenSection golden={d.golden} />
      <SilverSection d={d} name={name} version={v} whereOpen={where} onChoose={setChosen} onOpenWhere={openWhere}
        onCloseWhere={closeWhere} onOpenFile={setOpen} />
    </>
  );
}

function loadEachClass(cat: string, classes: ClassSummary[]): Promise<ClassData[]> {
  return Promise.all(classes.map((c) => loadClassData(cat, c)
    .then((x) => ({ cls: c.slug, name: c.name, properties: c.properties, ...x }))));
}

function ClassSection({ catalog, data: x }: { catalog: CatalogDetail; data: ClassData }) {
  const latest = x.d?.versions[0];
  return (
    <div className="cls-sec" data-class={x.cls}>
      <h2 className="cls-h2">{x.name}<span>{fmt(x.properties)} properties, {latest ? `published as ${latest.id}`
        : x.d ? "nothing published yet" : "no rules yet"}</span></h2>
      {x.d ? <ClassDatasets catalog={catalog.short} d={x.d} cls={x.cls} name={x.name} chosenId={null} />
        : <p className="muted gv-none">{x.error ?? `No ${x.name} rules for ${catalog.name} yet, so no datasets.`}</p>}
    </div>
  );
}

/** "Where these files are": open until Escape (unless a file's sample is open over it) or Close. */
function useWhereModal(cls: ClassSlug, fileOpen: boolean) {
  const [where, setWhere] = useState(false);
  useEscape(where && !fileOpen, () => setWhere(false));
  // with All classes, the samples a file opens are this class's (klass.ts reads ?in=)
  const openWhere = () => { if (currentClass() === "all") replaceParam("in", cls); setWhere(true); };
  return { where, openWhere, closeWhere: () => setWhere(false) };
}

function useEscape(active: boolean, onEscape: () => void) {
  useEffect(() => {
    if (!active) return;
    const esc = (e: KeyboardEvent) => { if (e.key === "Escape") onEscape(); };
    window.addEventListener("keydown", esc);
    return () => window.removeEventListener("keydown", esc);
  }, [active]);  // eslint-disable-line react-hooks/exhaustive-deps
}

/** The golden dataset as it is now: the human-reviewed values of each property (a property with none is left out). */
function GoldenSection({ golden }: { golden: GoldenResponse["golden"] }) {
  return (
    <section className="gd-sec" data-testid="golden">
      <h2>Golden dataset</h2>
      <p className="muted gd-lead">Only the values an expert reviewed, as they are now, published or not. A verdict writes its page's values at once.</p>
      <table className="gd-table">
        <thead><tr><th>Property</th><th>CTDL path</th><th className="n">Human-reviewed values</th></tr></thead>
        <GoldenRows golden={golden} />
        <GoldenTotals golden={golden} />
      </table>
    </section>
  );
}

function SilverSection(silver: SilverProps) {
  return (
    <section className="gd-sec">
      <h2>Silver datasets</h2>
      <p className="muted gd-lead">One per ruleset version: every value an approved rule found, also called the rule-matched dataset. The latest
        location holds the latest silver dataset, which xtra's scorer reads by default.</p>
      {!silver.d.versions.length ? <NoSilver name={silver.name} /> : <SilverVersions {...silver} />}
    </section>
  );
}

function loadClassData(cat: string, c: ClassSummary): Promise<{ d: GoldenResponse | null; error?: string }> {
  if (!c.ruleset_version) return Promise.resolve({ d: null });
  return inClass(c.slug, () => api.golden(cat)).then((x) => ({ d: x }), (e) => ({ d: null, error: String(e) }));
}

function GoldenRows({ golden }: { golden: GoldenResponse["golden"] }) {
  return (
    <tbody>{reviewedProperties(golden).map((x) => (
      <tr key={x.rule_id}><td>{x.property}</td><td className="mono">{x.path_shown ?? "—"}</td><td className="n">{fmt(x.human)}</td></tr>))}
    </tbody>
  );
}

function GoldenTotals({ golden }: { golden: GoldenResponse["golden"] }) {
  const none = golden.by_property.length - reviewedProperties(golden).length;
  return <tfoot><tr><td colSpan={2}>{none ? `${fmt(none)} ${none === 1 ? "property has" : "properties have"} no human-reviewed value yet` : "All properties"}</td>
    <td className="n">{fmt(golden.human)}</td></tr></tfoot>;
}

const SILVER_HEAD = <thead><tr><th>Silver dataset</th><th>Columns</th><th className="n">Human-reviewed values</th><th className="n">Rule-matched values</th></tr></thead>;

function NoSilver({ name }: { name: string }) {
  return (
    <table className="gv-table">
      {SILVER_HEAD}
      <tbody><tr><td className="empty" colSpan={4}>No silver dataset yet. Approving a{/^[AEIOU]/.test(name) ? "n" : ""} {name} rule on
        the Rules tab publishes <b>ruleset-v1</b>.</td></tr></tbody>
    </table>
  );
}

function SilverVersions({ d, version, whereOpen, onChoose, onOpenWhere, onCloseWhere, onOpenFile }: SilverProps) {
  return (
    <>
      <SilverTable versions={d.versions} chosen={version} onChoose={onChoose} />
      <div className="gv-foot"><button className="gv-help" onClick={onOpenWhere} title={`Where ${silverName(version.id)} is written`}>
        <span className="q" aria-hidden>?</span>Where these files are</button></div>
      {whereOpen && <WhereModal d={d} version={version} onClose={onCloseWhere} onOpenFile={onOpenFile} />}
    </>
  );
}

function reviewedProperties(golden: GoldenResponse["golden"]) {
  return golden.by_property.filter((x) => x.human > 0);
}

function SilverTable({ versions, chosen, onChoose }: { versions: GoldenVersion[]; chosen: GoldenVersion; onChoose: (id: string) => void }) {
  return (
    <table className="gv-table">
      {SILVER_HEAD}
      <tbody>{versions.map((x) => <SilverRow key={x.id} version={x} on={x.id === chosen.id} onChoose={onChoose} />)}
      </tbody>
    </table>
  );
}

function WhereModal({ d, version, onClose, onOpenFile }: { d: GoldenResponse; version: GoldenVersion; onClose: () => void; onOpenFile: (f: GoldenFile) => void }) {
  return (
    <div className="gv-back" onClick={onClose}>
      <div className="gv-modal" role="dialog" aria-label="Where these files are" onClick={(e) => e.stopPropagation()}>
        <div className="gv-modal-h"><h2>Where {silverName(version.id)} is written</h2><button className="btn sm" onClick={onClose}>Close</button></div>
        <div className="gv-where muted">Click a file to see a sample.</div>
        <div className="box"><Tree lines={whereLines(version, d.catalog, d.crawl)} open={onOpenFile} /></div>
      </div>
    </div>
  );
}

function SilverRow({ version: x, on, onChoose }: { version: GoldenVersion; on: boolean; onChoose: (id: string) => void }) {
  return (
    <tr className={on ? "on" : ""} onClick={() => onChoose(x.id)} data-version={x.id} title={lastWritten(x)}>
      <td><b>{silverName(x.id)}</b>{x.latest && <span className="faint"> latest</span>}</td>
      <td className="mono">{x.columns.length ? x.columns.join(", ") : <span className="muted">only human-reviewed values</span>}</td>
      <td className="n">{fmt(x.human)}</td>
      <td className="n">{fmt(x.values)}</td>
    </tr>
  );
}

/** The tree of where a version is written: each line's parts, then its comment, the comments aligned. */
function Tree({ lines, open }: { lines: TreeLine[]; open: (f: GoldenFile) => void }) {
  const width = Math.max(...lines.filter(([, c]) => c).map(([p]) => plain(p).length)) + 3;
  return (
    <div className="tree gv-tree">{lines.map(([parts, comment], i) => (
      <div key={i}>{parts.map((p, j) => <TreePart key={j} part={p} open={open} />)}
        {comment && <span className="c">{" ".repeat(Math.max(1, width - plain(parts).length))}# {comment}</span>}
        {!parts.length && "\u00a0"}</div>))}
    </div>
  );
}

function whereLines(v: GoldenVersion, catalog: string, crawl: string): TreeLine[] {
  return [...versionLines(v, catalog), ...(v.where.latest ? latestLines(catalog, crawl) : []), ...studioLines(v.where.studio)];
}

function lastWritten(x: GoldenVersion): string | undefined {
  return x.published_at ? `Last written ${x.published_at.slice(0, 10)}${x.published_by ? ` by ${x.published_by}` : ""}` : undefined;
}

function TreePart({ part: p, open }: { part: Part; open: (f: GoldenFile) => void }) {
  if (typeof p === "string") return <>{p}</>;
  if ("f" in p) return <button className="f" onClick={() => open(p.f)} title={`A sample of ${p.label}`}>{p.label}</button>;
  return <b>{p.b}</b>;
}

function versionLines(v: GoldenVersion, catalog: string): TreeLine[] {
  const w = v.where;
  const bar = w.latest ? "│" : " ";  // an older version: only its folder, not the latest location
  return [
    [[{ b: `${w.root.replace(/\/$/, "")}/` }]],
    [[w.latest ? "├── " : "└── ", `catalogs/${catalog}/versions/`, { b: `${v.id}/` }], "this version, kept for good"],
    [[`${bar}   ├── ${folder(v, "rule-matched")}`]],
    [[`${bar}   │   └── <page>/`, { f: "rule-matched.json", label: "<page>.json" }], `every value an approved rule found${pageCount(w.trees["rule-matched"].pages)}`],
    [[`${bar}   └── ${folder(v, "human-reviewed")}`]],
    [[`${bar}       └── <page>/`, { f: "human-reviewed.json", label: "<page>.json" }],
      `only the human-reviewed values${pageCount(w.trees["human-reviewed"].pages)}`],
  ];
}

function latestLines(catalog: string, crawl: string): TreeLine[] {
  return [[[`└── ${catalog}/${crawl}/`], "the latest location: the latest silver dataset, replaced whole"],
    [["    └── <page>/"]],
    [["        ├── ", { f: "page.json", label: "<page>.json" }], "the same as the silver dataset; where xtra's scorer reads by default"],
    [["        └── ", { f: "page.html", label: "<page>.html" }], "the page as crawled; the locations point into it"]];
}

function studioLines(studio: string): TreeLine[] {
  return [[[]], [[{ b: `Studio: ${studio}` }]],
    [["├── ", { f: "publication.json", label: "publication.json" }], "which ruleset, columns, approvals, where it was written"],
    [["├── ", { f: "lineage.parquet", label: "lineage.parquet" }], "one row per value → rule, version, occurrence, verdicts"],
    [["└── ", { f: "golden.parquet", label: "golden.parquet" }], "every value of this version, for Evals"]];
}

/** "Silver dataset ruleset-v3": the name a version's silver dataset goes by (its id is `ruleset-vN`). */
function silverName(id: string): string {
  return `Silver dataset ${id}`;
}

/** A tree's folder under the version (`silver/<catalog>/<crawl>/`, or `rule-matched/…` for a version written before). */
function folder(v: GoldenVersion, tree: GoldenTree): string {
  const p = v.where.trees[tree].prefix;
  return p.startsWith(v.where.version) ? p.slice(v.where.version.length) : p;
}

function plain(parts: Part[]): string {
  return parts.map((p) => (typeof p === "string" ? p : "f" in p ? p.label : p.b)).join("");
}

function pageCount(n: number | null | undefined): string {
  return n == null ? "" : ` (${fmt(n)} pages)`;
}
