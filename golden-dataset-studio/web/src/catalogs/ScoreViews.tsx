// The home page's xtra score view (LearningProgram spec §2; mockups w4-scores-all, w4-scores-all-numbers,
// w4-scores-one-catalog, w4-scores-one-catalog-one-property, w4-scores-props-menu, w3-scores-one-property). Three menus
// pick the scope: Catalogs (all, or one), Classes and Properties (one property, or more). Each ticked class is its own
// table. Every row has a Golden line (scored against human-reviewed values) and a Silver line (against rule-matched
// values): a stacked outcome bar with the 90% target dotted, exact and partial apart (or, with Numbers, a column per
// outcome), and its last 7 scores. A row opens the next scope down; one catalog and one property is that property's
// scores over time, with a link to the catalog's Evals tab at it. Read-only: scores come from xtra-cli's container
// (`GET /api/score-history`), never from here.
import { SkelTable } from "../shell/Skeleton";
import { Fragment, useEffect, useMemo, useState, type ReactNode } from "react";
import { api } from "../api/client";
import type { CatalogCard, ScoreHistory, ScoreLine } from "../api/types";
import { CLASS_NAME, href, type ClassSlug } from "../shell/router";
import { fmt } from "../shell/ui";
import { FindingsTable, StatusBar, useReview } from "../findings/Review";
import { goHome, homeHref, type HomeState } from "./homeState";
import { CatalogsMenu, ClassesMenu, PropertiesMenu, type ClassInfo } from "./menus";
import {
  exactOf, latest, partialOf, pct, scopeOf, scoredWith, series, SHOWN, termOf, TIER_WORD, TREES, TRIGGER,
  type Counts, type Pair, type Point, type Tree,
} from "./scoreLogic";
import "./scores.css";

const WORD: Record<string, string> = { match: "exact", partial: "partial", unsure: "unsure", wrong: "wrong", missing: "missing" };
const TREE_NAME: Record<Tree, string> = { golden: "Golden", silver: "Silver" };
const day = (iso: string) => new Date(iso).toLocaleDateString("en-GB", { day: "numeric", month: "short" });
const when = (iso: string) => new Date(iso).toLocaleString("en-GB", { day: "numeric", month: "short", hour: "numeric", minute: "2-digit", hour12: true })
  .replace(" am", " AM").replace(" pm", " PM");

function countsTip(c: Counts): string {
  return `${SHOWN.map((o) => `${fmt(c[o])} ${WORD[o]}`).join(", ")}, of ${fmt(c.values)} values`;
}

/** The latest output's stacked bar, exact at the left, with the 90% target dotted. */
export function OutcomeBar({ c, target }: { c: Counts | null; target: number }) {
  if (!c || !c.values) return <span className="sv-none faint">not scored yet</span>;
  return (
    <span className="sv-bar" title={countsTip(c)} data-testid="outcome-bar">
      {SHOWN.filter((o) => c[o] > 0).map((o) => <i key={o} className={`o-${o === "match" ? "match" : o}`} style={{ flexGrow: c[o] }} />)}
      <b className="sv-target" style={{ left: `${100 * target}%` }} />
    </span>
  );
}

/** The last scores as stacked bars (exact at the bottom), a 0–100 axis, the 90% line dashed, and the first and last
 * day; `big` adds each bar's kind (golden or output) under it. */
export function HistoryBars({ points, target, big }: { points: Point[]; target: number; big?: boolean }) {
  if (!points.length) return <span className="faint sv-nohist">—</span>;
  const W = big ? 680 : 150, H = big ? 210 : 30, L = big ? 26 : 22, B = big ? 34 : 12, T = 4;
  const slot = (W - L) / 7, bw = slot * (big ? 0.92 : 0.7);
  const y = (f: number) => T + (1 - f) * H;
  return (
    <svg className={`sv-hist${big ? " big" : ""}`} viewBox={`0 0 ${W} ${T + H + B}`} width={W} height={T + H + B}
      role="img" aria-label={`the last ${points.length} scores`} data-testid="history">
      <text x={L - 4} y={y(1) + 3} className="ax" textAnchor="end">100</text>
      {big && <text x={L - 4} y={y(target) + 3} className="ax" textAnchor="end">{Math.round(100 * target)}</text>}
      <text x={L - 4} y={y(0)} className="ax" textAnchor="end">0</text>
      <line x1={L} x2={L} y1={y(1)} y2={y(0)} className="axis" />
      {points.map((p, i) => {
        let acc = 0;
        const x = L + 2 + i * slot;
        return (
          <g key={i}>
            <title>{`${when(p.at)}, ${p.kind === "golden" ? "golden published" : "extract output"}: ${pct(exactOf(p.c))} exact`}</title>
            {SHOWN.map((o) => {
              const f = p.c.values ? p.c[o] / p.c.values : 0;
              if (!f) return null;
              const r = <rect key={o} x={x} y={y(acc + f)} width={bw} height={Math.max(0, f * H - (big ? 0 : 0.6))} className={`f-${o}`} />;
              acc += f;
              return r;
            })}
            {big && <text x={x + bw / 2} y={y(0) + 14} className={`kind ${p.kind}`} textAnchor="middle">{p.kind}</text>}
          </g>
        );
      })}
      <line x1={L} x2={W} y1={y(target)} y2={y(target)} className="target" />
      <text x={L} y={T + H + B - 1} className="ax">{day(points[0].at)}</text>
      {points.length > 1 && <text x={W} y={T + H + B - 1} className="ax" textAnchor="end">{day(points[points.length - 1].at)}</text>}
    </svg>
  );
}

interface Row { key: string; head: ReactNode; pairs: Pair[]; open?: string; evals?: string; strong?: boolean }

function Table({ h, rows, first, numbers, evals }: { h: ScoreHistory; rows: Row[]; first: string; numbers: boolean; evals: boolean }) {
  return (
    <table className={`sv-table${numbers ? " nums" : ""}`}>
      <thead><tr>
        <th className="sv-hd">{first}</th><th className="sv-tr" />
        {numbers ? <>{SHOWN.map((o) => <th key={o} className={`n c-${o}`}>{WORD[o]}</th>)}<th className="sv-n c-match">exact %</th></>
          : <><th className="sv-b">Latest extract output<span className="sv-90" style={{ left: `${100 * h.target}%` }}>{Math.round(100 * h.target)}%</span></th>
            <th className="sv-n c-match">exact</th><th className="sv-n c-partial">partial</th></>}
        <th className="sv-hs">Last 7 outputs</th>{evals && <th />}
      </tr></thead>
      {rows.map((r) => (
        <tbody key={r.key} className={r.strong ? "strong" : ""} data-row={r.key}>
          {TREES.map((t, i) => {
            const c = latest(h, r.pairs, t), ex = exactOf(c);
            return (
              <tr key={t} className={`t-${t}`}>
                {i === 0 && <td className="sv-hd" rowSpan={2}>{r.open ? <a href={r.open}>{r.head}</a> : r.head}</td>}
                <td className="sv-tr">{TREE_NAME[t]}</td>
                {numbers
                  ? <>{SHOWN.map((o) => <td key={o} className="sv-n">{c ? fmt(c[o]) : "—"}</td>)}</>
                  : <td className="sv-b"><OutcomeBar c={c} target={h.target} /></td>}
                <td className={`sv-n sv-ex${ex !== null && ex < h.target ? " under" : ""}`}>{pct(ex)}</td>
                {!numbers && <td className="sv-n">{pct(partialOf(c))}</td>}
                <td className="sv-hs"><HistoryBars points={series(h, r.pairs, t)} target={h.target} /></td>
                {evals && <td className="sv-ev">{i === 0 && r.evals && <a href={r.evals}>Evals →</a>}</td>}
              </tr>
            );
          })}
        </tbody>
      ))}
    </table>
  );
}

/** One catalog, one property: its scores over time, Golden and Silver side by side, then each score. */
function OneProperty({ h, cls, cat, name, col, short }: { h: ScoreHistory; cls: ClassSlug; cat: CatalogCard; name: string; col: string; short: string }) {
  const lines: ScoreLine[] = (h.history[cat.catalog]?.[col] ?? []).slice(-7);
  const pair: Pair[] = [[cat.catalog, col]];
  return (
    <section className="sv-sec" data-class={cls}>
      <div className="sv-h"><h2>{CLASS_NAME[cls]}</h2><span className="muted">{cat.name}, {name}, the last {lines.length || 7} scores</span>
        <span className="grow" />
        <a className="sv-evals" href={href(short, "evals", null, { col }, cls)}>Open {cat.name}'s Evals tab at {name} →</a></div>
      {!lines.length ? <p className="muted">Not scored yet. A score is made when the golden dataset or xtra's extract output changes.</p> : <>
        <div className="sv-charts">
          {TREES.map((t) => (
            <div key={t}><div className="sv-ch"><b>{TREE_NAME[t]}</b> against {t === "golden" ? "human-reviewed" : "rule-matched"} values</div>
              <HistoryBars points={series(h, pair, t)} target={h.target} big /></div>))}
        </div>
        <table className="sv-table">
          <thead><tr><th className="sv-hd">Score</th><th className="sv-tr" />
            <th className="sv-b">Latest extract output<span className="sv-90" style={{ left: `${100 * h.target}%` }}>{Math.round(100 * h.target)}%</span></th>
            <th className="sv-n c-match">exact</th><th className="sv-n c-partial">partial</th><th className="sv-sw">Scored with</th></tr></thead>
          {[...lines].reverse().map((l) => (
            <tbody key={l.score} data-score={l.score}>
              {TREES.map((t, i) => {
                const c = l[t] ? { ...l[t]! } as Counts : null, ex = exactOf(c);
                return (
                  <tr key={t}>
                    {i === 0 && <td className="sv-hd" rowSpan={2}>{when(l.at)}<div className="faint">{TRIGGER[l.trigger] ?? l.trigger}</div></td>}
                    <td className="sv-tr">{TREE_NAME[t]}</td>
                    <td className="sv-b"><OutcomeBar c={c} target={h.target} /></td>
                    <td className={`sv-n sv-ex${ex !== null && ex < h.target ? " under" : ""}`}>{pct(ex)}</td>
                    <td className="sv-n">{pct(partialOf(c))}</td>
                    {i === 0 && <td className="sv-sw" rowSpan={2}>
                      <div><span className="muted">golden</span> <b>{l.golden_version}</b></div>
                      {scoredWith(l) && <div><span className="muted">xtra-cli</span> <b>{scoredWith(l)}</b></div>}</td>}
                  </tr>
                );
              })}
            </tbody>
          ))}
        </table>
      </>}
    </section>
  );
}

export function ScoreViews({ cats, state }: { cats: CatalogCard[]; state: HomeState }) {
  const [hist, setHist] = useState<Partial<Record<ClassSlug, ScoreHistory>>>({});
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    let live = true;
    for (const cls of state.classes) {
      if (hist[cls]) continue;
      api.scoreHistory(cls).then((h) => { if (live) setHist((x) => ({ ...x, [cls]: h })); }, (e) => { if (live) setError(String(e)); });
    }
    return () => { live = false; };
  }, [state.classes.join(",")]);  // eslint-disable-line react-hooks/exhaustive-deps

  // each property's status (Needs review / Done), shown beside it in rows by property (learning-programs Phase 6)
  const [stat, setStat] = useState<Partial<Record<ClassSlug, Record<string, { status: string }>>>>({});
  useEffect(() => {
    let live = true;
    for (const cls of state.classes) api.propertyStatuses(cls).then((x) => live && setStat((s) => ({ ...s, [cls]: x })), () => {});
    return () => { live = false; };
  }, [state.classes.join(",")]);  // eslint-disable-line react-hooks/exhaustive-deps
  const byFolder = useMemo(() => new Map(cats.map((c) => [c.catalog, c])), [cats]);
  const catalogs = cats.filter((c) => Object.values(hist).some((h) => h?.catalogs.includes(c.catalog)));
  const pickedCat = state.catalog ? cats.find((c) => c.short === state.catalog) ?? null : null;
  const options = state.classes.flatMap((cls) => (hist[cls]?.properties ?? []).map((p) => ({ cls, column: p.column, name: termOf(p) })));
  const on = (cls: ClassSlug, col: string) => !state.props || state.props.has(`${cls}:${col}`);
  const tickedAll = options.filter((o) => on(o.cls, o.column));
  const oneProp = tickedAll.length === 1 ? tickedAll[0] : null;
  const scope = scopeOf(!!pickedCat, !!oneProp);
  // one property: its review (status, findings), the running notes' section made from data
  const { review, reload, catalogName } = useReview(oneProp?.cls ?? "course", oneProp?.column ?? null);
  const set = (x: Partial<HomeState>) => goHome({ ...state, ...x });
  const info = Object.fromEntries(Object.entries(hist).map(([k, h]) =>
    [k, { slug: k, properties: h!.properties.length, catalogs: h!.catalogs.length } as ClassInfo]));

  const toolbar = (
    <div className="hm-tools">
      <CatalogsMenu picked={pickedCat?.short ?? null} catalogs={catalogs.map((c) => ({ short: c.short, name: c.name }))}
        onChange={(c) => set({ catalog: c })} />
      <ClassesMenu picked={oneProp ? [oneProp.cls] : state.classes} info={info} onChange={(c) => set({ classes: c, props: null })}
        note="A table for each ticked class, one above the next" />
      <PropertiesMenu classes={state.classes} options={options} picked={state.props} onChange={(p) => set({ props: p })} />
      {scope === "all" && <span className="hm-rows">Rows
        <span className="seg xs" role="group" aria-label="Rows">
          <button className={state.rows === "catalogs" ? "on" : ""} onClick={() => set({ rows: "catalogs" })}>Catalogs</button>
          <button className={state.rows === "properties" ? "on" : ""} onClick={() => set({ rows: "properties" })}>Properties</button>
        </span></span>}
      <span className="grow" />
      {scope !== "one" && <span className="seg xs" role="group" aria-label="Bars or numbers">
        <button className={!state.numbers ? "on" : ""} onClick={() => set({ numbers: false })}>Bars</button>
        <button className={state.numbers ? "on" : ""} onClick={() => set({ numbers: true })}>Numbers</button>
      </span>}
    </div>
  );
  const legend = (
    <div className="sv-legend">
      {SHOWN.map((o) => <span key={o} className="evx-k"><i className={`sw o-${o}`} />{WORD[o]}</span>)}
      <span className="muted">Golden: scored against human-reviewed values. Silver: against rule-matched values. Dotted line: the 90% target.</span>
    </div>
  );

  const sections = state.classes.map((cls) => {
    const h = hist[cls];
    if (!h) return <section key={cls} className="sv-sec"><div className="sv-h"><h2>{CLASS_NAME[cls]}</h2></div><SkelTable label={`Loading ${CLASS_NAME[cls]} scores`} rows={5} cols={6} /></section>;
    const props = h.properties.filter((p) => on(cls, p.column));
    if (!props.length) return null;
    const inCats = pickedCat ? (h.catalogs.includes(pickedCat.catalog) ? [pickedCat.catalog] : []) : h.catalogs;
    if (!inCats.length) {
      return <section key={cls} className="sv-sec" data-class={cls}><div className="sv-h"><h2>{CLASS_NAME[cls]}</h2>
        <span className="muted">{pickedCat ? `No ${CLASS_NAME[cls]} rules in ${pickedCat.name} yet.` : `No catalog has ${CLASS_NAME[cls]} rules yet.`}</span></div></section>;
    }
    const scored = (pairs: Pair[]) => pairs.some(([c, col]) => (h.history[c]?.[col] ?? []).length);
    const catHead = (folder: string) => {
      const c = byFolder.get(folder);
      return <span className="sv-cat">{c?.logo ? <img src={c.logo} alt="" /> : <i />}<b>{c?.name ?? folder}</b></span>;
    };
    const propHead = (p: ScoreHistory["properties"][number]) => {
      const st = stat[cls]?.[p.column]?.status;
      return <span className="sv-prop"><span><span className="mono">{termOf(p)}</span>
        {st && <span className={`sv-status ${st === "done" ? "done" : "review"}`} data-testid="property-status-tag">{st === "done" ? "✓ Done" : "Needs review"}</span>}</span>
        <span className="faint mono">{TIER_WORD[p.tier]}</span></span>;
    };
    const shortOf = (folder: string) => byFolder.get(folder)?.short ?? folder;
    if (scope === "one" && pickedCat && oneProp) {
      const p = h.properties.find((x) => x.column === oneProp.column)!;
      return <Fragment key={cls}><OneProperty h={h} cls={cls} cat={pickedCat} name={termOf(p)} col={p.column} short={pickedCat.short} />
        <FindingsTable cls={cls} col={p.column} review={review} reload={reload} catalogName={catalogName} /></Fragment>;
    }
    let rows: Row[], first: string, sub: string, unscored: string;
    if (scope === "catalog" || (scope === "all" && state.rows === "properties")) {
      const one = scope === "catalog";
      rows = props.map((p) => ({
        key: p.column, head: propHead(p), pairs: inCats.map((c) => [c, p.column] as Pair),
        open: homeHref({ ...state, classes: [cls], props: new Set([`${cls}:${p.column}`]) }),  // one property: its class
        evals: one ? href(shortOf(inCats[0]), "evals", null, { col: p.column }, cls) : undefined,
      }));
      first = "Property";
      const nP = `${props.length} propert${props.length === 1 ? "y" : "ies"}`;
      sub = one ? `${byFolder.get(inCats[0])?.name}, ${nP}. A property opens its history.`
        : inCats.length === 1 ? `${nP} in ${byFolder.get(inCats[0])?.name ?? inCats[0]}. A property opens it there.`
          : `${nP}, each over every catalog. A property opens it in each catalog.`;
      unscored = "properties";
    } else {
      const cols = props.map((p) => p.column);
      rows = inCats.map((c) => ({
        key: c, head: catHead(c), pairs: cols.map((col) => [c, col] as Pair),
        open: homeHref({ ...state, catalog: shortOf(c) }),
      }));
      if (rows.length > 1) rows.push({ key: "all", head: <b>All</b>, pairs: inCats.flatMap((c) => cols.map((col) => [c, col] as Pair)), strong: true });
      first = "Catalog";
      sub = oneProp ? `${oneProp.name} in ${inCats.length} catalog${inCats.length === 1 ? "" : "s"}. A catalog opens its history.`
        : inCats.length === 1 ? `1 catalog, over its scored properties. The catalog opens its properties.`
          : `${inCats.length} catalogs, each over its scored properties. A catalog opens its properties.`;
      unscored = "catalogs";
    }
    const shown = rows.filter((r) => scored(r.pairs));
    const left = rows.length - shown.length;
    return (
      <section key={cls} className="sv-sec" data-class={cls}>
        <div className="sv-h"><h2>{CLASS_NAME[cls]}</h2><span className="muted">{sub}</span></div>
        {shown.length ? <Table h={h} rows={shown} first={first} numbers={state.numbers} evals={scope === "catalog"} />
          : <p className="muted sv-empty">Not scored yet. A score is made when the golden dataset or xtra's extract output changes.</p>}
        {shown.length > 0 && left > 0 && <p className="faint sv-left">{left} {left === 1 ? unscored.replace(/ies$/, "y").replace(/s$/, "") : unscored} not scored yet.</p>}
        {scope === "property" && oneProp && <FindingsTable cls={cls} col={oneProp.column} review={review} reload={reload} catalogName={catalogName} />}
      </section>
    );
  });
  return (
    <div className="sv" data-scope={scope}>
      {toolbar}
      {legend}
      {error && <p className="muted">{error}</p>}
      {oneProp && <StatusBar cls={oneProp.cls} col={oneProp.column} review={review} reload={reload} />}
      {sections}
    </div>
  );
}
