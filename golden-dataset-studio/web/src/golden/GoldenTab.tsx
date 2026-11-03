// Datasets (Evals spec §6.6, m4b; property-rules spec §4.16): a read-only record of the two datasets. The golden dataset is
// only the values an expert reviewed, by property, as they are now. The silver datasets are one per ruleset version (every
// value an approved rule found, also called the rule-matched dataset): its columns, values and where it's written. Approving
// a rule publishes its silver dataset (Rules tab), so there's no Publish button here. "Where these files are" opens where
// the chosen version is written, each file a link to a sample.
import { useCallback, useEffect, useState } from "react";
import { api } from "../api/client";
import type { GoldenResponse, GoldenTree, GoldenVersion } from "../api/types";
import type { TabProps } from "../shell/tabProps";
import { fmt, useKeyHints } from "../shell/ui";
import { FilePreview } from "./FilePreview";
import type { GoldenFile } from "./FilePreview";
import "./golden.css";

/** "Silver dataset ruleset-v3": the name a version's silver dataset goes by (its id is `ruleset-vN`). */
const silverName = (id: string) => `Silver dataset ${id}`;

/** A tree's folder under the version (`silver/<catalog>/<crawl>/`, or `rule-matched/…` for a version written before). */
const folder = (v: GoldenVersion, tree: GoldenTree) => {
  const p = v.where.trees[tree].prefix;
  return p.startsWith(v.where.version) ? p.slice(v.where.version.length) : p;
};

type Part = string | { f: GoldenFile; label: string } | { b: string };
const plain = (parts: Part[]) => parts.map((p) => (typeof p === "string" ? p : "f" in p ? p.label : p.b)).join("");

/** The tree of where a version is written: each line's parts, then its comment, the comments aligned. */
function Tree({ lines, open }: { lines: [Part[], string?][]; open: (f: GoldenFile) => void }) {
  const width = Math.max(...lines.filter(([, c]) => c).map(([p]) => plain(p).length)) + 3;
  return (
    <div className="tree gv-tree">{lines.map(([parts, comment], i) => (
      <div key={i}>{parts.map((p, j) => (typeof p === "string" ? p
        : "f" in p ? <button key={j} className="f" onClick={() => open(p.f)} title={`A sample of ${p.label}`}>{p.label}</button>
        : <b key={j}>{p.b}</b>))}
        {comment && <span className="c">{" ".repeat(Math.max(1, width - plain(parts).length))}# {comment}</span>}
        {!parts.length && " "}</div>))}
    </div>
  );
}

function whereLines(v: GoldenVersion, catalog: string, crawl: string): [Part[], string?][] {
  const w = v.where;
  const pages = (n: number | null | undefined) => (n == null ? "" : ` (${fmt(n)} pages)`);
  const bar = w.latest ? "│" : " ";  // an older version: only its folder, not the latest location
  const silver = folder(v, "rule-matched"), golden = folder(v, "human-reviewed");
  const lines: [Part[], string?][] = [
    [[{ b: `${w.root.replace(/\/$/, "")}/` }]],
    [[w.latest ? "├── " : "└── ", `catalogs/${catalog}/versions/`, { b: `${v.id}/` }], "this version, kept for good"],
    [[`${bar}   ├── ${silver}`]],
    [[`${bar}   │   └── <page>/`, { f: "rule-matched.json", label: "<page>.json" }], `every value an approved rule found${pages(w.trees["rule-matched"].pages)}`],
    [[`${bar}   └── ${golden}`]],
    [[`${bar}       └── <page>/`, { f: "human-reviewed.json", label: "<page>.json" }],
      `only the human-reviewed values${pages(w.trees["human-reviewed"].pages)}`],
  ];
  if (w.latest) {
    lines.push([[`└── ${catalog}/${crawl}/`], "the latest location: the latest silver dataset, replaced whole"],
      [["    └── <page>/"]],
      [["        ├── ", { f: "page.json", label: "<page>.json" }], "the same as the silver dataset; where xtra's scorer reads by default"],
      [["        └── ", { f: "page.html", label: "<page>.html" }], "the page as crawled; the locations point into it"]);
  }
  lines.push([[]], [[{ b: `Studio: ${w.studio}` }]],
    [["├── ", { f: "publication.json", label: "publication.json" }], "which ruleset, columns, approvals, where it was written"],
    [["├── ", { f: "lineage.parquet", label: "lineage.parquet" }], "one row per value → rule, version, occurrence, verdicts"],
    [["└── ", { f: "golden.parquet", label: "golden.parquet" }], "every value of this version, for Evals"]);
  return lines;
}

/** The golden dataset as it is now: the human-reviewed values of each property (a property with none is left out). */
function GoldenSection({ golden }: { golden: GoldenResponse["golden"] }) {
  const rows = golden.by_property.filter((x) => x.human > 0);
  const none = golden.by_property.length - rows.length;
  return (
    <section className="gd-sec" data-testid="golden">
      <h2>Golden dataset</h2>
      <p className="muted gd-lead">Only the values an expert reviewed, as they are now, published or not. A verdict writes its page's values at once.</p>
      <table className="gd-table">
        <thead><tr><th>Property</th><th>CTDL path</th><th className="n">Human-reviewed values</th></tr></thead>
        <tbody>{rows.map((x) => (
          <tr key={x.rule_id}><td>{x.property}</td><td className="mono">{x.path_shown ?? "—"}</td><td className="n">{fmt(x.human)}</td></tr>))}
        </tbody>
        <tfoot><tr><td colSpan={2}>{none ? `${fmt(none)} ${none === 1 ? "property has" : "properties have"} no human-reviewed value yet` : "All properties"}</td>
          <td className="n">{fmt(golden.human)}</td></tr></tfoot>
      </table>
    </section>
  );
}

export default function GoldenTab({ catalog, route }: TabProps) {
  const [d, setD] = useState<GoldenResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [open, setOpen] = useState<GoldenFile | null>(null);
  const [chosen, setChosen] = useState<string | null>(route.params.get("v"));
  const load = useCallback(() => {
    api.golden(catalog.short).then(setD, (e) => setError(String(e)));
  }, [catalog.short]);
  useEffect(load, [load]);
  const [where, setWhere] = useState(false);
  useEffect(() => {
    if (!where || open) return;
    const esc = (e: KeyboardEvent) => { if (e.key === "Escape") setWhere(false); };
    window.addEventListener("keydown", esc);
    return () => window.removeEventListener("keydown", esc);
  }, [where, open]);
  useKeyHints(<span>Approving a rule on the Rules tab publishes its silver dataset. Engineers can also run{" "}
    <span className="mono">golden-datasets golden publish --catalog {catalog.short} --property NAME</span></span>, [catalog.short]);

  if (error) return <div className="doc"><div className="doc-in"><p className="muted">{error}</p></div></div>;
  if (!d) return <div className="doc"><div className="doc-in"><h1>Datasets</h1></div></div>;
  const v = d.versions.find((x) => x.id === chosen) ?? d.versions[0];

  return (
    <div className="doc"><div className="doc-in">
      {open && v && <FilePreview catalog={catalog.short} version={v.id} latest={v.latest} file={open} onClose={() => setOpen(null)} />}
      <div className="gv-head"><h1>Datasets</h1><span className="muted">Approving a rule publishes its silver dataset. The golden dataset changes only when an expert gives a verdict.</span></div>
      <GoldenSection golden={d.golden} />
      <section className="gd-sec">
        <h2>Silver datasets</h2>
        <p className="muted gd-lead">One per ruleset version: every value an approved rule found, also called the rule-matched dataset. The latest
          location holds the latest silver dataset, which xtra's scorer reads by default.</p>
        {!d.versions.length ? (
          <p className="muted gv-none">No silver dataset yet. Approving a rule on the Rules tab publishes its silver dataset.</p>
        ) : (
          <>
            <table className="gv-table">
              <thead><tr><th>Silver dataset</th><th>Columns</th><th className="n">Human-reviewed values</th><th className="n">Rule-matched values</th></tr></thead>
              <tbody>{d.versions.map((x) => (
                <tr key={x.id} className={x.id === v.id ? "on" : ""} onClick={() => setChosen(x.id)} data-version={x.id}
                    title={x.published_at ? `Last written ${x.published_at.slice(0, 10)}${x.published_by ? ` by ${x.published_by}` : ""}` : undefined}>
                  <td><b>{silverName(x.id)}</b>{x.latest && <span className="faint"> latest</span>}</td>
                  <td className="mono">{x.columns.length ? x.columns.join(", ") : <span className="muted">only human-reviewed values</span>}</td>
                  <td className="n">{fmt(x.human)}</td>
                  <td className="n">{fmt(x.values)}</td>
                </tr>))}
              </tbody>
            </table>
            <div className="gv-foot"><button className="gv-help" onClick={() => setWhere(true)} title={`Where ${silverName(v.id)} is written`}>
              <span className="q" aria-hidden>?</span>Where these files are</button></div>
            {where && (
              <div className="gv-back" onClick={() => setWhere(false)}>
                <div className="gv-modal" role="dialog" aria-label="Where these files are" onClick={(e) => e.stopPropagation()}>
                  <div className="gv-modal-h"><h2>Where {silverName(v.id)} is written</h2><button className="btn sm" onClick={() => setWhere(false)}>Close</button></div>
                  <div className="gv-where muted">Click a file to see a sample.</div>
                  <div className="box"><Tree lines={whereLines(v, d.catalog, d.crawl)} open={setOpen} /></div>
                </div>
              </div>)}
          </>
        )}
      </section>
    </div></div>
  );
}
