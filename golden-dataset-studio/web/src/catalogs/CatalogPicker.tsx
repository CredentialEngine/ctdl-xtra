// Home: the catalogs table (Evals spec §6.1, §6.2; property-rules spec §4.9, m5; LearningProgram spec, item 12). One
// compact row per catalog: Open → (or ✦ Generate rules for a catalog without rules) in its own first column, its logo,
// its name, then one cell per property under angled headers, and Coverage. Two views, switched next to the heading:
// - Golden dataset: the date of its pages and, per property, a small fraction (KaTeX): the values an expert reviewed
//   over the values the property's rule found; "—" with no rule yet. A Classes menu ticks the classes whose columns
//   show, side by side under a heading per class, in the three tiers (Required in bold, Phase 1, Phase 2 folded into
//   one column until clicked). A catalog without a class's rules says so across that class's columns.
// - xtra score: ScoreViews (the four scopes of the score history).
// + Add a catalog (a crawl xtra-cli has already made) adds a row that shows its progress until it's ready.
//
// URL: #/?v=score&cls=course&c=wvu&p=course:name&rows=props&n=1 (homeState.ts)
import katex from "katex";
import "katex/dist/katex.min.css";
import { Fragment, useCallback, useEffect, useState } from "react";
import { api } from "../api/client";
import type { CatalogCard, CatalogSummary, CatalogsSummary } from "../api/types";
import { Tip } from "../evals/EvalsTab";
import { CLASS_NAME, CLASS_SLUGS, href, useRoute, type ClassSlug } from "../shell/router";
import { fmt, fmtDate, Ico } from "../shell/ui";
import { AddCatalogModal } from "./AddCatalogModal";
import { GenerateRulesModal } from "./GenerateRulesModal";
import { goHome, readHome } from "./homeState";
import { LoopModal, shouldShowLoop } from "./LoopModal";
import { ClassesMenu, type ClassInfo } from "./menus";
import { ScoreViews } from "./ScoreViews";
import "../evals/evals.css";
import "./ctab.css";
import "./scores.css";

const STEP: Record<string, string> = {
  starting: "Starting…", copying: "Copying pages…", indexing: "Indexing pages…", assets: "Saving page styles…",
  done: "Finishing…",
};

function addingText(c: CatalogCard): string {
  const a = c.adding;
  if (!a) return "";
  if (c.status === "failed") return "Couldn't add it";
  return a.step === "copying" && a.total ? `Copying pages… ${Math.floor((100 * a.done) / a.total)}%` : STEP[a.step] ?? "Adding…";
}

/** LaTeX for a count: thousands with a thin comma (1{,}048). */
const tex = (n: number) => fmt(n).replace(/,/g, "{,}");
const katexHtml = (src: string) => ({ __html: katex.renderToString(src, { throwOnError: false }) });

/** A column's human-reviewed values over the values its rule found: \frac{H}{N}. */
export function fractionTex(human: number, found: number): string {
  return `\\dfrac{${tex(human)}}{${tex(found)}}`;
}

/** The fraction in plain words (its delayed tooltip). */
export function fractionTip(human: number, found: number, status: string): string {
  const v = (n: number) => `${fmt(n)} value${n === 1 ? "" : "s"}`;
  return `${v(human)} an expert reviewed, of ${v(found)} the rule found`
    + (status === "needs work" ? ". Some values are marked wrong." : "");
}

export default function CatalogPicker() {
  const route = useRoute();
  const state = readHome(route.params);
  const view = state.view;

  const [cats, setCats] = useState<CatalogCard[] | null>(null);
  const [sums, setSums] = useState<Partial<Record<ClassSlug, CatalogsSummary>>>({});
  const [error, setError] = useState<string | null>(null);
  const [loop, setLoop] = useState(shouldShowLoop);
  const [adding, setAdding] = useState(false);
  const [generate, setGenerate] = useState<CatalogCard | null>(null);
  const [p2, setP2] = useState<Set<ClassSlug>>(new Set());  // the classes whose Phase 2 columns are shown
  const load = useCallback(() => api.catalogs().then(setCats, (e) => setError(String(e))), []);
  useEffect(() => { load(); }, [load]);
  // while a catalog is being added, follow its progress; once it's added, its row's summary
  const busy = !!cats?.some((c) => c.status === "adding");
  const [added, setAdded] = useState(0);
  useEffect(() => {
    if (!busy) return;
    const t = window.setInterval(load, 2000);
    return () => { window.clearInterval(t); setAdded((n) => n + 1); };
  }, [busy, load]);
  useEffect(() => {
    let live = true;
    // every class's summary: the Classes menu says what each has, the table shows the ticked ones
    for (const cls of CLASS_SLUGS) {
      api.catalogsSummary("human", cls).then((s) => live && setSums((x) => ({ ...x, [cls]: s })), (e) => live && setError(String(e)));
    }
    return () => { live = false; };
  }, [added]);

  const modal = (loop && <LoopModal onClose={() => setLoop(false)} />)
    || (adding && <AddCatalogModal onClose={() => setAdding(false)} onAdded={load} />)
    || (generate && <GenerateRulesModal card={generate} onClose={() => { setGenerate(null); load(); }} />);
  const info = Object.fromEntries(Object.entries(sums).map(([k, s]) =>
    [k, { slug: k, properties: s!.properties, catalogs: Object.keys(s!.catalogs).length } as ClassInfo]));
  const head = (
    <div className="picker-head">
      <h1>Catalogs</h1>
      <span className="seg" role="group" aria-label="View">
        <button className={view === "golden" ? "on" : ""} onClick={() => goHome({ ...state, view: "golden" })}>Golden dataset</button>
        <button className={view === "score" ? "on" : ""} onClick={() => goHome({ ...state, view: "score" })}>xtra score</button>
      </span>
      {view === "golden" && <ClassesMenu picked={state.classes} info={info} onChange={(c) => goHome({ ...state, classes: c })}
        note="Columns for each ticked class, side by side" />}
      <span className="grow" />
      <button className="btn" onClick={() => setAdding(true)}>+ Add a catalog</button>
    </div>
  );
  if (error) return <div className="picker"><div className="picker-in ctab-page">{head}<p className="muted">{error}</p></div>{modal}</div>;
  if (!cats) return <div className="picker"><div className="picker-in ctab-page">{head}</div>{modal}</div>;
  if (view === "score") {
    return (
      <div className="picker">
        <div className="picker-in ctab-page sv-page">{head}<ScoreViews cats={cats} state={state} />
          <button className="loop-again" onClick={() => setLoop(true)}>How the Studio works</button></div>
        {modal}
      </div>
    );
  }

  // the golden view: each ticked class's columns, side by side under its heading, in the three tiers (once every
  // ticked class's summary is here, so columns don't move)
  if (state.classes.some((c) => !sums[c])) return <div className="picker"><div className="picker-in ctab-page">{head}<p className="faint">Loading…</p></div>{modal}</div>;
  const groups = state.classes.flatMap((cls) => {
    const s = sums[cls];
    if (!s) return [];
    const tier = (k: string) => s.tiers?.[k] ?? (s.required.includes(k) ? "required" : "phase1");
    const req = s.columns.filter((k) => tier(k) === "required"), ph1 = s.columns.filter((k) => tier(k) === "phase1");
    const ph2 = s.columns.filter((k) => tier(k) === "phase2");
    return [{ cls, s, req, ph1, ph2, open: p2.has(cls) }];
  });
  const width = (g: (typeof groups)[number]) => g.req.length + g.ph1.length + (g.open ? g.ph2.length : g.ph2.length ? 1 : 0);
  const rot = (g: (typeof groups)[number], k: string, start: boolean) => (
    <th key={`${g.cls}:${k}`} className={`rot${g.req.includes(k) ? " req" : ""}${start ? " tier-start" : ""}`}><span>{g.s.labels[k] ?? k}</span></th>);

  return (
    <div className="picker">
      <div className="picker-in ctab-page">
        {head}
        <div className="ctab-wrap">
        <table className="ctab">
          <thead>
            <tr className="cls-row"><th colSpan={3} className="fixed" /><th className="gap" />
              {groups.map((g) => (
                <th key={g.cls} colSpan={width(g)} data-class={g.cls}><span className="in"><b>{CLASS_NAME[g.cls]}</b>
                  {g.req.length} required, {g.ph1.length} more in Phase 1, {g.ph2.length} in Phase 2</span></th>))}
              <th className="fixed right" /></tr>
            <tr>
              <th className="act" /><th className="logo" /><th className="name plain">Catalog</th><th className="date plain">Pages from</th>
              {groups.map((g) => <Fragment key={g.cls}>
                {g.req.map((k, i) => rot(g, k, i === 0))}
                {g.ph1.map((k, i) => rot(g, k, i === 0))}
                {g.open ? g.ph2.map((k, i) => rot(g, k, i === 0))
                  : g.ph2.length > 0 && <th className="rot p2 tier-start" title="Show the Phase 2 columns"
                    onClick={() => setP2((x) => new Set([...x, g.cls]))}><span>+ {g.ph2.length} Phase 2</span></th>}
              </Fragment>)}
              <th className="cov plain">Coverage</th>
            </tr>
          </thead>
          <tbody>
            {cats.map((c) => {
              const isReady = c.status === "ready";
              const inFlight = c.status === "adding" || c.status === "failed";
              const why = inFlight ? addingText(c) : c.status === "not imported" ? (c.pages ? "no rules yet" : "pages not indexed") : "";
              return (
                <tr key={c.catalog} className={isReady ? "" : `off ${inFlight ? c.status : ""}`}>
                  <td className="act">
                    {isReady ? <a className="btn sm" href={href(c.short, "rules")}>Open →</a>
                      : c.status === "failed" ? <button className="btn sm" onClick={() => api.dismissAdd(c.catalog).then(load)}>Dismiss</button>
                        : c.status === "not imported" && c.pages
                          ? <button className="btn sm" onClick={() => setGenerate(c)}><Ico name="spark" />Generate rules</button> : null}
                  </td>
                  <td className="logo">{c.logo && <img src={c.logo} alt={`${c.name} logo`} />}</td>
                  <td className="name"><span className="nm">{c.institution}</span></td>
                  <td className="date" title={c.pages != null ? `${fmt(c.pages)} pages in this crawl` : undefined}>{c.crawl ? fmtDate(c.crawl) : "—"}</td>
                  {!isReady
                    ? <td colSpan={groups.reduce((n, g) => n + width(g), 0)} className="c faint why" title={c.adding?.error ?? undefined}>{why}</td>
                    : groups.map((g) => {
                      const s = g.s.catalogs[c.catalog];
                      if (!s) {
                        return <td key={g.cls} colSpan={width(g)} className="nosrc tier-start">
                          {(c.not_sources ?? []).includes(g.cls) ? `Not a ${CLASS_NAME[g.cls]} source` : `No ${CLASS_NAME[g.cls]} rules yet`}</td>;
                      }
                      return <Fragment key={g.cls}>
                        <GoldenCells s={s} cols={g.req} start />
                        <GoldenCells s={s} cols={g.ph1} start />
                        {g.open ? <GoldenCells s={s} cols={g.ph2} start />
                          : g.ph2.length > 0 && <td className="p2c tier-start" title="Phase 2 properties with a rule here">
                            {g.ph2.filter((k) => s.columns[k] && !s.columns[k].no_rule).length} of {g.ph2.length}</td>}
                      </Fragment>;
                    })}
                  <td className="cov">{isReady ? groups.map((g) => {
                    const s = g.s.catalogs[c.catalog];
                    return s ? <span key={g.cls} className="cl"><b>{s.coverage}</b> <span className="faint">of {g.s.properties} {CLASS_NAME[g.cls]}</span></span> : null;
                  }) : <span className="faint">—</span>}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
        </div>
        <div className="ctab-key"><span><b>Bold</b>required</span><span>Regular: the rest of Phase 1</span>
          <span>+ Phase 2: click to show its columns</span></div>
        <button className="loop-again" onClick={() => setLoop(true)}>How the Studio works</button>
      </div>
      {modal}
    </div>
  );
}

/** Golden dataset: per property, its values in the golden dataset as a fraction ("—" with no rule in this catalog).
 * `start`: the first column of a tier, set apart by a rule. */
function GoldenCells({ s, cols, start }: { s: CatalogSummary; cols: string[]; start?: boolean }) {
  return (
    <>
      {cols.map((k, i) => {
        const st = s.columns[k];
        const edge = start && i === 0 ? " tier-start" : "";
        if (!st || st.no_rule) return <td key={k} className={`c faint${edge}`}>—</td>;
        return (
          <td key={k} className={"c frac " + st.status.replace(" ", "-") + edge} aria-label={`${k}: ${st.status}`}>
            <Tip tip={fractionTip(st.human, st.found, st.status)} width={300} delay={1000}>
              <span tabIndex={0} className="fr" dangerouslySetInnerHTML={katexHtml(fractionTex(st.human, st.found))} />
            </Tip>
          </td>
        );
      })}
    </>
  );
}
