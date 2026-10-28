// Publish (spec §7.6, screen 10): publish the golden dataset one property at a time. Each property can be chosen
// once its field rule is approved, whatever the other fields' rules say; the button shows ✓ Published once the
// chosen properties are published from this extraction at their current rule versions. What will be written: the
// tree, each file can be opened as a sample.
import { useCallback, useEffect, useState } from "react";
import { api } from "../api/client";
import type { GoldenResponse } from "../api/types";
import { useReviewer } from "../shell/reviewer";
import { href } from "../shell/router";
import type { TabProps } from "../shell/tabProps";
import { fmt, Ico, toast, useKeyHints } from "../shell/ui";
import { FilePreview } from "./FilePreview";
import type { GoldenFile } from "./FilePreview";
import "./golden.css";

const pillClass = (s: string) => (s === "approved" ? "approved" : s === "needs work" ? "needs" : "review");

export default function GoldenTab({ catalog }: TabProps) {
  const [d, setD] = useState<GoldenResponse | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const me = useReviewer();
  const [open, setOpen] = useState<GoldenFile | null>(null);
  const [chosen, setChosen] = useState<string[] | null>(null);  // null: the server's default (every approved property)
  const load = useCallback(() => {
    api.golden(catalog.short, chosen ?? undefined).then((r) => { setD(r); setChosen((c) => c ?? r.chosen); },
                                                        (e) => setError(String(e)));
  }, [catalog.short, chosen]);
  useEffect(load, [load]);
  useKeyHints(<span><span className="mono">golden-datasets golden publish --catalog {catalog.short} --to ROOT --property NAME</span> does the same from the CLI</span>, [catalog.short]);

  if (error) return <div className="doc"><div className="doc-in"><p className="muted">{error}</p></div></div>;
  if (!d) return <div className="doc"><div className="doc-in"><h1>Publish the golden dataset</h1></div></div>;
  const sel = (chosen ?? d.chosen).filter((p) => d.properties.some((x) => x.property === p && x.status === "approved"));
  const approvable = d.properties.filter((p) => p.status === "approved");
  const identity = d.rules.filter((r) => r.kind !== "field");
  // every chosen property already published from this extraction at its current rule version: nothing new to write
  const done = sel.length > 0 && sel.every((name) => {
    const p = d.properties.find((x) => x.property === name);
    return !!p?.published && p.published.extraction === d.extraction && p.published.rule_version === p.version;
  });
  const toggle = (p: string) => setChosen((c) => {
    const cur = c ?? d.chosen;
    return cur.includes(p) ? cur.filter((x) => x !== p) : d.properties.map((x) => x.property).filter((x) => x === p || cur.includes(x));
  });

  const publish = async () => {
    setBusy(true);
    try {
      const r = await api.goldenPublish(catalog.short, { author: me, properties: sel });
      toast(`Published ${sel.join(", ")} (${r.publication}): ${fmt(r.files)} pages`);
      load();
    } catch (e) { toast(String(e)); } finally { setBusy(false); }
  };

  const F = ({ f, children }: { f: GoldenFile; children: string }) =>
    <button className="f" onClick={() => setOpen(f)} title={`Show ${children}`}>{children}</button>;

  return (
    <div className="doc"><div className="doc-in">
      {open && <FilePreview catalog={catalog.short} file={open} stems={d.page_stems} author={me} properties={sel}
                            onClose={() => setOpen(null)} />}
      <h1>Publish to the golden dataset</h1>
      <div className={`gate ${sel.length ? "ready" : "blocked"}`}>
        <Ico name="lock" />
        <div className="grow">{done
          ? <><b>Already published:</b> {sel.join(", ")} from extraction <span className="mono">{d.extraction}</span>.</>
          : sel.length
          ? <><b>Ready to publish {sel.length === 1 ? sel[0] : `${sel.length} properties`}:</b> {sel.length > 1 && <>{sel.join(", ")}. </>}
              {fmt(d.courses)} courses, {fmt(d.fields)} values
              {d.approvals && <> ({fmt(d.approvals.human)} approved by a person, {fmt(d.approvals.rule)} by the rule)</>}.</>
          : approvable.length
            ? <><b>Choose a property</b> below to publish.</>
            : <><b>Nothing to publish yet:</b> no property's rule is approved. Approve one on the Rules tab.</>}</div>
        <button className={"btn primary" + (done ? " is-done" : "")} disabled={!sel.length || busy || done} onClick={publish}
          data-tour="golden-publish" title={done ? "Already published from this extraction at these rule versions" : undefined}>
          {busy ? "Publishing…" : done ? <><Ico name="correct" />Published</>
            : sel.length === 1 ? `Publish ${sel[0]}` : `Publish ${sel.length || ""} properties`}</button>
      </div>
      <div className="gold-grid">
        <div className="box"><h3>Properties · ruleset v{d.ruleset_version} <span className="h3-note">· tick the ones to publish</span></h3>
          {d.properties.map((p) => {
            const ok = p.status === "approved";
            const on = sel.includes(p.property);
            return (
              <label key={p.property} className={"chk prop" + (ok ? "" : " off") + (on ? " on" : "")} data-property={p.property}
                title={ok ? `${p.rule_id} v${p.version}, approved by ${p.approved_by}` : `${p.rule_id} v${p.version} isn't approved yet`}>
                <input type="checkbox" checked={on} disabled={!ok} onChange={() => toggle(p.property)} />
                <span><b>{p.property}</b><span className={`rid ${p.ctdl_property ? "" : "plain"}`}>{p.ctdl_property ?? "no CTDL term"}</span>
                  <span className="pub-when">{p.published
                    ? <>published {p.published.published_at?.slice(0, 10)}{p.published.rule_version != null && <> · v{p.published.rule_version}</>}</>
                    : "not published yet"}</span></span>
                <a className={`pill ${pillClass(p.status)}`} href={href(catalog.short, "rules", p.rule_id)} onClick={(e) => e.stopPropagation()}>
                  <Ico name={p.status} />{p.status}</a>
              </label>
            );
          })}
          <div className="identity muted">Which courses exist comes from {identity.map((r, i) => (
            <span key={r.rule_id}>{i > 0 && " and "}<a href={href(catalog.short, "rules", r.rule_id)}>{r.title}</a>{" "}
              ({r.status})</span>))}: recorded with each publication, but it doesn't hold a property back.</div>
        </div>
        <div>
          <div className="box"><h3>What will be written <span className="h3-note">· click a file to see a sample</span></h3>
            <div className="target mono">{d.target}</div>
            <div className="tree">{"."}{"\n"}
              {"└── <page>/                 "}<span className="c"># one folder per saved page with courses ({fmt(d.pages)})</span>{"\n"}
              {"    ├── "}<F f="page.json">{"<page>.json"}</F>{"         "}<span className="c"># [{"{"}golden_record_id, approval, fields: [{"{"}ctdl_property,</span>{"\n"}
              {"    │                       "}<span className="c">#   property, value, source_url, location, approval,</span>{"\n"}
              {"    │                       "}<span className="c">#   approved_by, approved_at{"}"}]{"}"}]</span>{"\n"}
              {"    └── "}<F f="page.html">{"<page>.html"}</F>{"         "}<span className="c"># the page as crawled, if not there yet: the</span>{"\n"}
              {"                            "}<span className="c">#   locations above point into it</span>{"\n\n"}
              {"Studio: golden/<publication>/"}{"\n"}
              {"├── "}<F f="lineage.parquet">{"lineage.parquet"}</F>{"         "}<span className="c"># one row per value → rule, version, occurrence, verdicts</span>{"\n"}
              {"└── "}<F f="publication.json">{"publication.json"}</F>{"        "}<span className="c"># which extraction and ruleset, approvals</span>
            </div>
          </div>
        </div>
      </div>
    </div></div>
  );
}
