// Golden datasets (Evals spec §6.6, m4b): a read-only record. Approving a column's rule publishes it (Rules tab), so
// there's no Publish button here. One row per version (ruleset vN): its columns, how many of its values are
// human-reviewed and how many the rules matched (every value; scores are the Evals tab's). "Where these files are"
// (bottom right) opens where the chosen version is written, each file a link to a sample.
import { useCallback, useEffect, useState } from "react";
import { api } from "../api/client";
import type { GoldenResponse, GoldenVersion } from "../api/types";
import type { TabProps } from "../shell/tabProps";
import { fmt, useKeyHints } from "../shell/ui";
import { FilePreview } from "./FilePreview";
import type { GoldenFile } from "./FilePreview";
import "./golden.css";

const vname = (id: string) => id.replace(/^ruleset-v/, "ruleset v");

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
  const lines: [Part[], string?][] = [
    [[{ b: `${w.root.replace(/\/$/, "")}/` }]],
    [[w.latest ? "├── " : "└── ", `catalogs/${catalog}/versions/`, { b: `${v.id}/` }], "this version, kept for good"],
    [[`${bar}   ├── rule-matched/${catalog}/${crawl}/`]],
    [[`${bar}   │   └── <page>/`, { f: "rule-matched.json", label: "<page>.json" }], `every value${pages(w.trees["rule-matched"].pages)}`],
    [[`${bar}   └── human-reviewed/${catalog}/${crawl}/`]],
    [[`${bar}       └── <page>/`, { f: "human-reviewed.json", label: "<page>.json" }],
      `only the human-reviewed values${pages(w.trees["human-reviewed"].pages)}`],
  ];
  if (w.latest) {
    lines.push([[`└── ${catalog}/${crawl}/`], "the latest version, replaced whole"],
      [["    └── <page>/"]],
      [["        ├── ", { f: "page.json", label: "<page>.json" }], "the same as rule-matched; where readers look today"],
      [["        └── ", { f: "page.html", label: "<page>.html" }], "the page as crawled; the locations point into it"]);
  }
  lines.push([[]], [[{ b: `Studio: ${w.studio}` }]],
    [["├── ", { f: "publication.json", label: "publication.json" }], "which ruleset, columns, approvals, where it was written"],
    [["├── ", { f: "lineage.parquet", label: "lineage.parquet" }], "one row per value → rule, version, occurrence, verdicts"],
    [["└── ", { f: "golden.parquet", label: "golden.parquet" }], "every value of this version, for Evals"]);
  return lines;
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
  useKeyHints(<span>Approving a column's rule on the Rules tab publishes it. Engineers can also run{" "}
    <span className="mono">golden-datasets golden publish --catalog {catalog.short} --property NAME</span></span>, [catalog.short]);

  if (error) return <div className="doc"><div className="doc-in"><p className="muted">{error}</p></div></div>;
  if (!d) return <div className="doc"><div className="doc-in"><h1>Golden datasets</h1></div></div>;
  const v = d.versions.find((x) => x.id === chosen) ?? d.versions[0];

  return (
    <div className="doc"><div className="doc-in">
      {open && v && <FilePreview catalog={catalog.short} version={v.id} latest={v.latest} file={open} onClose={() => setOpen(null)} />}
      <div className="gv-head"><h1>Golden datasets</h1><span className="muted">Published when a column's rule is approved.</span></div>
      {!d.versions.length ? (
        <p className="muted gv-none">No golden dataset yet. Approving a column's rule on the Rules tab publishes it, and so does
          a subject matter expert's first check of a value.</p>
      ) : (
        <>
          <table className="gv-table">
            <thead><tr><th>Golden dataset</th><th>Columns</th><th className="n">Human-reviewed values</th><th className="n">Rule-matched values</th></tr></thead>
            <tbody>{d.versions.map((x) => (
              <tr key={x.id} className={x.id === v.id ? "on" : ""} onClick={() => setChosen(x.id)} data-version={x.id}
                  title={x.published_at ? `Last written ${x.published_at.slice(0, 10)}${x.published_by ? ` by ${x.published_by}` : ""}` : undefined}>
                <td><b>{vname(x.id)}</b>{x.latest && <span className="faint"> latest</span>}</td>
                <td className="mono">{x.columns.length ? x.columns.join(", ") : <span className="muted">only human-reviewed values</span>}</td>
                <td className="n">{fmt(x.human)}</td>
                <td className="n">{fmt(x.values)}</td>
              </tr>))}
            </tbody>
          </table>
          <div className="gv-foot"><button className="gv-help" onClick={() => setWhere(true)} title={`Where ${vname(v.id)} is written`}>
            <span className="q" aria-hidden>?</span>Where these files are</button></div>
          {where && (
            <div className="gv-back" onClick={() => setWhere(false)}>
              <div className="gv-modal" role="dialog" aria-label="Where these files are" onClick={(e) => e.stopPropagation()}>
                <div className="gv-modal-h"><h2>Where {vname(v.id)} is written</h2><button className="btn sm" onClick={() => setWhere(false)}>Close</button></div>
                <div className="gv-where muted">Click a file to see a sample.</div>
                <div className="box"><Tree lines={whereLines(v, d.catalog, d.crawl)} open={setOpen} /></div>
              </div>
            </div>)}
        </>
      )}
    </div></div>
  );
}
