// Home: the catalogs table (Evals spec §6.1, §6.2). One compact row per catalog: Open → (or ✦ Generate rules for a
// catalog without rules) in its own first column, its logo, its name (wrapped to a narrow column), then one cell per column under angled headers: the Studio's seven
// Course columns, then those xtra extracts that the Studio doesn't cover yet (greyed "—"). Two views, switched next to
// the heading:
// - Golden dataset: the date of its pages and the Rules tab's icon per column (✓ published, ○ in review, ✕ known wrong);
// - xtra score: exact matches of xtra's latest extract output against the latest golden dataset, overall and per
//   column, scored against Human-reviewed | Rule-matched; hovering a bar or a legend colour explains the outcomes.
// + Add a catalog (a crawl xtra-cli has already made) adds a row that shows its progress until it's ready.
//
// URL: #/?v=score&b=rule
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
const ICON_OF = { published: "approved", "in review": "in review", "needs work": "needs work" } as const;
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
              : <th className="plain">Exact matches<span className={`evx-basis-pill ${basis}`}>{BASIS_NAME[basis]}</span></th>}
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
            <span><Ico name="approved" />published in a golden dataset (hover for which ruleset)</span>
            <span><Ico name="in review" />in review</span>
            <span><Ico name="needs work" />known wrong values</span>
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

/** Golden dataset: the date of its pages and, per column, the Rules tab's icon for its rule. */
function GoldenCells({ c, s, cols, why }: { c: CatalogCard; s: CatalogSummary | undefined; cols: string[]; why: string }) {
  return (
    <>
      <td className="date" title={c.pages != null ? `${fmt(c.pages)} pages in this crawl` : undefined}>{c.crawl ? fmtDate(c.crawl) : "—"}</td>
      {c.status !== "ready" || !s
        ? <td colSpan={cols.length} className="c faint why" title={c.adding?.error ?? undefined}>{why}</td>
        : cols.map((k) => {
          const st = s.columns[k];
          if (!st) return <td key={k} className="c faint">—</td>;
          const icon = <Ico name={ICON_OF[st.status]} className="ri" />;
          return (
            <td key={k} className="c" aria-label={`${k}: ${st.status}`}>
              {st.status === "published"
                ? <Tip tip={`Published in golden dataset ruleset v${st.ruleset}`} width={300}><span tabIndex={0}>{icon}</span></Tip>
                : icon}
            </td>
          );
        })}
    </>
  );
}

/** xtra score: exact matches overall (with its count) and per column (%, a thin bar, the count); "—" where nothing is
 * scored, "n/s" for columns not read from the page. */
function ScoreCells({ c, s, cols, why, basis }: { c: CatalogCard; s: CatalogSummary | undefined; cols: string[]; why: string; basis: ScoreBasis }) {
  const sc = s?.score;
  if (!sc) {
    return (
      <>
        <td className="rate faint">{c.status === "ready" ? "—" : why}</td>
        {cols.map((k) => <td key={k} className="c faint">—</td>)}
      </>
    );
  }
  const total = { values: sc.values, ...sc.outcomes };
  return (
    <>
      <td className="rate">
        <div className="rate-in">
          <span className="pct">{pct(total.match, total.values)}<span className="cnt">of {fmt(total.values)}</span></span>
          <OutcomeTip counts={total} title={`${c.institution} · ${fmt(total.values)} ${BASIS_NAME[basis]} values`}><Bar c={total} /></OutcomeTip>
        </div>
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
