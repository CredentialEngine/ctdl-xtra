// Golden (spec §7.6, screen 10): each rule version's status, Publish disabled until every rule is approved,
// what will be written, golden_id collisions to confirm, earlier publications.
import { useCallback, useEffect, useState } from "react";
import { api } from "../api/client";
import type { GoldenResponse } from "../api/types";
import { useReviewer } from "../shell/reviewer";
import { href } from "../shell/router";
import type { TabProps } from "../shell/tabProps";
import { fmt, Ico, toast, useKeyHints } from "../shell/ui";
import "./golden.css";

const pillClass = (s: string) => (s === "approved" ? "approved" : s === "needs work" ? "needs" : "review");

export default function GoldenTab({ catalog }: TabProps) {
  const [d, setD] = useState<GoldenResponse | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const me = useReviewer();
  const load = useCallback(() => { api.golden(catalog.short).then(setD, (e) => setError(String(e))); }, [catalog.short]);
  useEffect(load, [load]);
  useKeyHints(<span><span className="mono">golden-datasets golden publish --catalog {catalog.short} --to ROOT</span> does the same from the CLI</span>, [catalog.short]);

  if (error) return <div className="doc"><div className="doc-in"><p className="muted">{error}</p></div></div>;
  if (!d) return <div className="doc"><div className="doc-in"><h1>Publish the golden dataset</h1></div></div>;
  const pending = d.rules.filter((r) => r.status !== "approved");
  const needs = pending.filter((r) => r.status === "needs work").length;

  const publish = async () => {
    setBusy(true);
    try {
      const r = await api.goldenPublish(catalog.short, { author: me });
      toast(`Published ${r.publication}: ${fmt(r.files)} pages`);
      load();
    } catch (e) { toast(String(e)); } finally { setBusy(false); }
  };

  return (
    <div className="doc"><div className="doc-in">
      <h1>Publish the golden dataset</h1>
      <div className="lead">Turns extraction <span className="mono">{d.extraction}</span> (ruleset v{d.ruleset_version}) into a
        domain-only dataset plus a lineage table. Every rule version in the ruleset must be approved first.</div>
      <div className={`gate ${d.ready ? "ready" : "blocked"}`}>
        <Ico name="lock" />
        <div className="grow">{d.ready
          ? <><b>Ready to publish:</b> every rule in ruleset v{d.ruleset_version} is approved.</>
          : <><b>Publishing is blocked:</b> {pending.length} of {d.rules.length} rules are not approved yet
              ({needs} need work, {pending.length - needs} in review).</>}</div>
        <button className="btn primary" disabled={!d.ready || busy} onClick={publish} data-tour="golden-publish">
          {busy ? "Publishing…" : "Publish golden dataset"}</button>
      </div>
      <div className="gold-grid">
        <div className="box"><h3>Rule status · ruleset v{d.ruleset_version}</h3>
          {d.rules.map((r) => (
            <a key={r.rule_id} className="chk" href={href(catalog.short, "rules", r.rule_id)} style={{ color: "inherit", textDecoration: "none" }}>
              <Ico name={r.status} />
              <span><b>{r.title}</b><span className={`rid ${r.kind === "field" ? "" : "plain"}`}>{r.subtitle}</span></span>
              <span className={`pill ${pillClass(r.status)}`} title={r.approved_by ? `approved by ${r.approved_by}` : undefined}>
                <Ico name={r.status} />{r.status}</span>
            </a>
          ))}
        </div>
        <div>
          <div className="box"><h3>What will be written</h3>
            <div className="target mono">{d.target}</div>
            <div className="tree">{"."}{"\n"}
              {"└── <page>/                 "}<span className="c"># one folder per saved page with courses ({fmt(d.pages)})</span>{"\n"}
              {"    ├── <page>.json         "}<span className="c"># [{"{"}golden_id, fields: [{"{"}ctdl_property, property,</span>{"\n"}
              {"    │                       "}<span className="c">#   value, source_url, location{"}"}]{"}"}]</span>{"\n"}
              {"    └── <page>.html         "}<span className="c"># the page as crawled, if not there yet: the</span>{"\n"}
              {"                            "}<span className="c">#   locations above point into it</span>{"\n\n"}
              {"Studio: golden/<publication>/"}{"\n"}
              {"├── lineage.parquet         "}<span className="c"># one row per value → rule, version, occurrence, verdicts</span>{"\n"}
              {"└── publication.json        "}<span className="c"># which extraction and ruleset, approvals</span>
            </div>
            <div className="muted" style={{ fontSize: 12.5, marginTop: 10, lineHeight: 1.55 }}>
              {fmt(d.courses)} courses · {fmt(d.records)} course entries · {fmt(d.fields)} values. Same shape as the golden
              sets saved so far, plus <span className="mono">location</span> (css_path and character offsets on the page) on
              every value and a <span className="mono">golden_id</span> on every course. Learning Type is kept with{" "}
              <span className="mono">ctdl_property: null</span>. Rule ids and verdicts live only in{" "}
              <span className="mono">lineage.parquet</span>, which stays in the Studio.
            </div>
          </div>
          <div className="box" style={{ marginTop: 18 }}><h3>golden_id collisions to confirm · {d.collisions.length}</h3>
            {d.collisions.length === 0
              ? <div className="muted">None: every course code names one course.</div>
              : <>
                  <div className="muted" style={{ fontSize: 12.5, marginBottom: 8 }}>The same code names different courses on its course
                    pages, so each name gets its own <span className="mono">golden_id</span>. Check that these really are different courses.</div>
                  <div className="collisions">{d.collisions.slice(0, 200).map((c) => (
                    <div key={c.course_key} className="chk" style={{ gridTemplateColumns: "auto 1fr" }}>
                      <b className="mono">{c.course_key}</b>
                      <span>{c.names.map((n, i) => <div key={i}><span className="mono muted">{c.golden_ids[i]}</span> {n}</div>)}</span>
                    </div>))}
                    {d.collisions.length > 200 && <div className="muted">… and {d.collisions.length - 200} more</div>}
                  </div>
                </>}
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
