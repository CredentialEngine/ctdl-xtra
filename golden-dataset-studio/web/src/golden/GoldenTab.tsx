// Publish (spec §7.6, screen 10): publish the golden dataset one property at a time. Each property can be chosen
// once its field rule is approved, whatever the other fields' rules say; what will be written (each file can be
// opened as a sample, merged with what the golden set has), course codes shared by different courses, earlier
// publications.
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
      <div className="lead">One property at a time: a property can be published once its rule is approved, whatever the
        other fields' rules say. Publishing writes the chosen properties' values from extraction{" "}
        <span className="mono">{d.extraction}</span> (ruleset v{d.ruleset_version}) into each page's file, and keeps what
        earlier publications wrote for the other properties.</div>
      <div className={`gate ${sel.length ? "ready" : "blocked"}`}>
        <Ico name="lock" />
        <div className="grow">{sel.length
          ? <><b>Ready to publish {sel.length === 1 ? sel[0] : `${sel.length} properties`}:</b> {sel.length > 1 && <>{sel.join(", ")}. </>}
              {fmt(d.courses)} courses, {fmt(d.fields)} values.</>
          : approvable.length
            ? <><b>Choose a property</b> below to publish.</>
            : <><b>Nothing to publish yet:</b> no property's rule is approved. Approve one on the Rules tab.</>}</div>
        <button className="btn primary" disabled={!sel.length || busy} onClick={publish} data-tour="golden-publish">
          {busy ? "Publishing…" : sel.length === 1 ? `Publish ${sel[0]}` : `Publish ${sel.length || ""} properties`}</button>
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
              {"    ├── "}<F f="page.json">{"<page>.json"}</F>{"         "}<span className="c"># [{"{"}golden_id, fields: [{"{"}ctdl_property, property,</span>{"\n"}
              {"    │                       "}<span className="c">#   value, source_url, location{"}"}]{"}"}]</span>{"\n"}
              {"    └── "}<F f="page.html">{"<page>.html"}</F>{"         "}<span className="c"># the page as crawled, if not there yet: the</span>{"\n"}
              {"                            "}<span className="c">#   locations above point into it</span>{"\n\n"}
              {"Studio: golden/<publication>/"}{"\n"}
              {"├── "}<F f="lineage.parquet">{"lineage.parquet"}</F>{"         "}<span className="c"># one row per value → rule, version, occurrence, verdicts</span>{"\n"}
              {"└── "}<F f="publication.json">{"publication.json"}</F>{"        "}<span className="c"># which extraction and ruleset, approvals</span>
            </div>
            <div className="muted" style={{ fontSize: 12.5, marginTop: 10, lineHeight: 1.55 }}>
              {fmt(d.courses)} courses · {fmt(d.records)} course entries · {fmt(d.fields)} values. Same shape as the golden
              sets saved so far, plus <span className="mono">location</span> (css_path and character offsets on the page) on
              every value and an id on every course (<span className="mono">golden_id</span>: its course code, like{" "}
              <span className="mono">GEOG222</span>). Learning Type is kept with{" "}
              <span className="mono">ctdl_property: null</span>. Rule ids and verdicts live only in{" "}
              <span className="mono">lineage.parquet</span>, which stays in the Studio.
            </div>
          </div>
          <div className="box" style={{ marginTop: 18 }}><h3>One course code, different courses · {d.collisions.length}</h3>
            <div className="muted" style={{ fontSize: 12.5, marginBottom: 8, lineHeight: 1.55 }}>
              Each course in the dataset is identified by its course code. When course pages use one code for courses with
              different names, each name gets its own id (<span className="mono">GEOG222~1</span>,{" "}
              <span className="mono">GEOG222~2</span>) so they stay apart, and they're listed here so you can check they
              really are different courses and not one course whose title changed.</div>
            {d.collisions.length === 0
              ? <div>None in this catalog: every course code is used for one course.</div>
              : <div className="collisions">{d.collisions.slice(0, 200).map((c) => (
                  <div key={c.course_key} className="chk" style={{ gridTemplateColumns: "auto 1fr" }}>
                    <b className="mono">{c.course_key}</b>
                    <span>{c.names.map((n, i) => <div key={i}>{n} <span className="mono muted">→ {c.golden_ids[i]}</span></div>)}</span>
                  </div>))}
                  {d.collisions.length > 200 && <div className="muted">… and {d.collisions.length - 200} more</div>}
                </div>}
          </div>
          {d.publications.length > 0 && (
            <div className="box" style={{ marginTop: 18 }}><h3>Earlier publications</h3>
              {d.publications.map((p) => (
                <div key={p.publication} className="chk" style={{ gridTemplateColumns: "1fr auto" }}>
                  <span><b className="mono">{p.publication}</b><br />
                    <span className="muted">{fmt(p.courses)} courses · {fmt(p.lineage_rows)} lineage rows · {p.extraction} ·
                      {" "}{p.published_by} → <span className="mono">{p.to}</span></span></span>
                  {!p.all_rules_approved && <span className="pill review">test (not all approved)</span>}
                </div>))}
            </div>)}
        </div>
      </div>
    </div></div>
  );
}
