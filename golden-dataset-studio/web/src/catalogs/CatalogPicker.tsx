// Home: the catalogs table (Evals spec §6.1, §6.2). One compact row per catalog: Open → (or ✦ Generate rules for a
// catalog without rules) in its own first column, its logo, its name (wrapped to a narrow column), then one cell per column under angled headers: the Studio's seven
// Course columns, then those xtra extracts that the Studio doesn't cover yet (greyed "—"). Two views, switched next to
// the heading:
// - Golden dataset: the date of its pages and, per column, a small fraction (KaTeX): the values an expert reviewed
//   over the values the column's rule found;
// - xtra score: exact matches of xtra's latest extract output against the latest golden dataset, overall and per
//   column, scored against Human-reviewed | Rule-matched; hovering a bar or a legend colour explains the outcomes.
// + Add a catalog (a crawl xtra-cli has already made) adds a row that shows its progress until it's ready.
//
// URL: #/?v=score&b=rule
import katex from "katex";
import "katex/dist/katex.min.css";
import { useCallback, useEffect, useState } from "react";
import { api } from "../api/client";
import type { CatalogCard, CatalogSummary, CatalogsSummary, ScoreBasis } from "../api/types";
import { Bar, OUTCOMES, OutcomeTip, Tip } from "../evals/EvalsTab";
import { go, href, useRoute } from "../shell/router";
import { fmt, fmtDate, Ico } from "../shell/ui";
import { AddCatalogModal } from "./AddCatalogModal";
import { GenerateRulesModal } from "./GenerateRulesModal";
import { LoopModal, shouldShowLoop } from "./LoopModal";
import "../evals/evals.css";
import "./ctab.css";

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

const pct = (match: number, values: number) => `${Math.round((100 * match) / values)}%`;
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
const BASIS_NAME: Record<ScoreBasis, string> = { human: "human-reviewed", rule: "rule-matched" };

export default function CatalogPicker() {
  const route = useRoute();
  const view = route.params.get("v") === "score" ? "score" : "golden";
  const basis: ScoreBasis = route.params.get("b") === "rule" ? "rule" : "human";
  const nav = (v: string, b: ScoreBasis) =>
    go(`#/${v === "score" ? `?v=score${b === "rule" ? "&b=rule" : ""}` : ""}`, true);

  const [cats, setCats] = useState<CatalogCard[] | null>(null);
  const [sum, setSum] = useState<CatalogsSummary | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loop, setLoop] = useState(shouldShowLoop);
  const [adding, setAdding] = useState(false);
  const [generate, setGenerate] = useState<CatalogCard | null>(null);
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
    api.catalogsSummary(basis).then((s) => live && setSum(s), (e) => live && setError(String(e)));
    return () => { live = false; };
  }, [basis, added]);

  const modal = (loop && <LoopModal onClose={() => setLoop(false)} />)
    || (adding && <AddCatalogModal onClose={() => setAdding(false)} onAdded={load} />)
    || (generate && <GenerateRulesModal card={generate} onClose={() => { setGenerate(null); load(); }} />);
  const head = (
    <div className="picker-head">
      <h1>Catalogs</h1>
      <span className="seg" role="group" aria-label="View">
        <button className={view === "golden" ? "on" : ""} onClick={() => nav("golden", basis)}>Golden dataset</button>
        <button className={view === "score" ? "on" : ""} onClick={() => nav("score", basis)}>xtra score</button>
      </span>
      <span className="grow" />
      <button className="btn" onClick={() => setAdding(true)}>+ Add a catalog</button>
    </div>
  );
  if (error) return <div className="picker"><div className="picker-in ctab-page">{head}<p className="muted">{error}</p></div>{modal}</div>;
  if (!cats) return <div className="picker"><div className="picker-in ctab-page">{head}</div>{modal}</div>;
  const cols = sum?.columns ?? [];
  const ext = sum?.not_in_studio ?? [];
  const extCells = ext.map((k) => <td key={k} className="c ext faint">—</td>);

  return (
    <div className="picker">
      <div className="picker-in ctab-page">
        {head}
        {view === "score" && <>
          <div className="ctab-title">How closely xtra's latest extract output matches each catalog's latest golden dataset</div>
          <div className="evx-basis ctab-basis">scored against
            <span className="seg xs" role="group" aria-label="Scored against">
              <button className={basis === "human" ? "on" : ""} onClick={() => nav("score", "human")}>Human-reviewed</button>
              <button className={basis === "rule" ? "on" : ""} onClick={() => nav("score", "rule")}>Rule-matched</button>
            </span>
          </div>
        </>}
        <table className="ctab">
          <thead><tr>
            <th /><th /><th className="plain">Catalog</th>
            {view === "golden" ? <th className="plain">Pages from</th>
              : <><th className="plain">Exact matches<span className={`evx-basis-pill ${basis}`}>{BASIS_NAME[basis]}</span></th><th /></>}
            {cols.map((k) => <th key={k} className="rot"><span>{k}</span></th>)}
            {ext.map((k) => <th key={k} className="rot ext"><span>{k}</span></th>)}
          </tr></thead>
          <tbody>
            {cats.map((c) => {
              const s = sum?.catalogs[c.catalog];
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
                  {view === "golden"
                    ? <GoldenCells c={c} s={s} cols={cols} why={why} />
                    : <ScoreCells c={c} s={s} cols={cols} why={why} basis={basis} />}
                  {extCells}
                </tr>
              );
            })}
          </tbody>
        </table>
        {view === "golden" ? (
          <div className="ctab-legend">
            <span className="fr" dangerouslySetInnerHTML={katexHtml(
              "\\dfrac{\\text{values an expert reviewed}}{\\text{values the rule found}}")} />
            <span><b className="faint">—</b>not in this Studio yet (xtra extracts it)</span>
          </div>
        ) : (
          <div className="ctab-legend">
            {OUTCOMES.slice().reverse().map((o) => <OutcomeTip key={o} counts={null}><span className="evx-k"><i className={`sw o-${o}`} />{o}</span></OutcomeTip>)}
            <span className="faint">— not published yet, or not in this Studio yet · n/s not scored (not read from the page)</span>
          </div>
        )}
        <button className="loop-again" onClick={() => setLoop(true)}>How the Studio works</button>
      </div>
      {modal}
    </div>
  );
}

/** Golden dataset: the date of its pages and, per column, its values in the golden dataset as a fraction. */
function GoldenCells({ c, s, cols, why }: { c: CatalogCard; s: CatalogSummary | undefined; cols: string[]; why: string }) {
  return (
    <>
      <td className="date" title={c.pages != null ? `${fmt(c.pages)} pages in this crawl` : undefined}>{c.crawl ? fmtDate(c.crawl) : "—"}</td>
      {c.status !== "ready" || !s
        ? <td colSpan={cols.length} className="c faint why" title={c.adding?.error ?? undefined}>{why}</td>
        : cols.map((k) => {
          const st = s.columns[k];
          if (!st) return <td key={k} className="c faint">—</td>;
          return (
            <td key={k} className={"c frac " + st.status.replace(" ", "-")} aria-label={`${k}: ${st.status}`}>
              <Tip tip={fractionTip(st.human, st.found, st.status)} width={300} delay={1000}>
                <span tabIndex={0} className="fr" dangerouslySetInnerHTML={katexHtml(fractionTex(st.human, st.found))} />
              </Tip>
            </td>
          );
        })}
    </>
  );
}

/** xtra score: exact matches overall (the % with its count, then its bar in a column with no heading, as tall as the
 * columns' bars) and per column (%, a thin bar, the count); "—" where nothing is scored, "n/s" for columns not read
 * from the page. */
function ScoreCells({ c, s, cols, why, basis }: { c: CatalogCard; s: CatalogSummary | undefined; cols: string[]; why: string; basis: ScoreBasis }) {
  const sc = s?.score;
  if (!sc) {
    return (
      <>
        <td className="rate faint">{c.status === "ready" ? "—" : why}</td>
        <td className="ratebar" />
        {cols.map((k) => <td key={k} className="c faint">—</td>)}
      </>
    );
  }
  const total = { values: sc.values, ...sc.outcomes };
  return (
    <>
      <td className="rate"><span className="pct">{pct(total.match, total.values)}<span className="cnt">of {fmt(total.values)}</span></span></td>
      <td className="ratebar">
        <OutcomeTip counts={total} title={`${c.institution} · ${fmt(total.values)} ${BASIS_NAME[basis]} values`}><Bar c={total} /></OutcomeTip>
      </td>
      {cols.map((k) => {
        const v = sc.by_column[k];
        if (v && v.values) {
          return (
            <td key={k} className="c sc">
              <OutcomeTip counts={v} title={`${k} · ${c.institution} · ${fmt(v.values)} ${BASIS_NAME[basis]} values`}>
                <span className="sc-in" tabIndex={0}>
                  <span className="pct">{pct(v.match, v.values)}</span>
                  <span className="cellbar">{OUTCOMES.slice().reverse().filter((o) => v[o] > 0).map((o) => <i key={o} className={`o-${o}`} style={{ flexGrow: v[o] }} />)}</span>
                  <span className="cnt">{fmt(v.values)}</span>
                </span>
              </OutcomeTip>
            </td>
          );
        }
        return sc.implied.includes(k)
          ? <td key={k} className="c faint ns" title="not scored: not read from the page">n/s</td>
          : <td key={k} className="c faint">—</td>;
      })}
    </>
  );
}
