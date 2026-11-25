// The home page's xtra score view (LearningProgram spec §2; mockups w4-scores-all, w4-scores-all-numbers,
// w4-scores-one-catalog, w4-scores-one-catalog-one-property, w4-scores-props-menu, w3-scores-one-property). Three menus
// pick the scope: Catalogs (all, or one), Classes and Properties (one property, or more). Each ticked class is its own
// table. Every row has a Golden line (scored against human-reviewed values) and a Silver line (against rule-matched
// values): a stacked outcome bar with the 90% target dotted, exact and partial apart (or, with Numbers, a column per
// outcome), and its last 7 scores. A row opens the next scope down; one catalog and one property is that property's
// scores over time, with a link to the catalog's Evals tab at it. Read-only: scores come from xtra-cli's container
// (`GET /api/score-history`), never from here.
import { SkelTable } from "../shell/Skeleton";
import { useEffect, useMemo, useState, type ReactNode } from "react";
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

type Histories = Partial<Record<ClassSlug, ScoreHistory>>;
type Statuses = Partial<Record<ClassSlug, Record<string, { status: string }>>>;
type Property = ScoreHistory["properties"][number];
type ScoreView = ReturnType<typeof useScoreView>;
type SetHome = (x: Partial<HomeState>) => void;
interface Row { key: string; head: ReactNode; pairs: Pair[]; open?: string; evals?: string; strong?: boolean }
interface TreeRowProps { h: ScoreHistory; row: Row; tree: Tree; first: boolean; numbers: boolean; evals: boolean }
interface ScoreTable { rows: Row[]; first: string; sub: string; unscored: string }
interface Frame { W: number; H: number; L: number; B: number; T: number; slot: number; bw: number; y: (f: number) => number }

const WORD: Record<string, string> = { match: "exact", partial: "partial", unsure: "unsure", wrong: "wrong", missing: "missing" };
const TREE_NAME: Record<Tree, string> = { golden: "Golden", silver: "Silver" };
const NOT_SCORED = "Not scored yet. A score is made when the golden dataset or xtra's extract output changes.";

export function ScoreViews({ cats, state }: { cats: CatalogCard[]; state: HomeState }) {
  const view = useScoreView(cats, state);
  const { review, reload } = view.findings;
  return (
    <div className="sv" data-scope={view.scope}>
      <Toolbar view={view} />
      <Legend />
      {view.error && <p className="muted">{view.error}</p>}
      {view.oneProp && <StatusBar cls={view.oneProp.cls} col={view.oneProp.column} review={review} reload={reload} />}
      {state.classes.map((cls) => <ClassSection key={cls} cls={cls} view={view} />)}
    </div>
  );
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
  const f = historyFrame(!!big);
  return (
    <svg className={`sv-hist${big ? " big" : ""}`} viewBox={`0 0 ${f.W} ${f.T + f.H + f.B}`} width={f.W} height={f.T + f.H + f.B}
      role="img" aria-label={`the last ${points.length} scores`} data-testid="history">
      <HistoryAxis f={f} target={target} big={big} />
      {points.map((p, i) => <HistoryBar key={i} p={p} x={f.L + 2 + i * f.slot} f={f} big={big} />)}
      <line x1={f.L} x2={f.W} y1={f.y(target)} y2={f.y(target)} className="target" />
      <text x={f.L} y={f.T + f.H + f.B - 1} className="ax">{day(points[0].at)}</text>
      {points.length > 1 && <text x={f.W} y={f.T + f.H + f.B - 1} className="ax" textAnchor="end">{day(points[points.length - 1].at)}</text>}
    </svg>
  );
}

function useScoreView(cats: CatalogCard[], state: HomeState) {
  const { hist, error } = useScoreHistories(state.classes);
  const stat = usePropertyStatuses(state.classes);
  const byFolder = useMemo(() => new Map(cats.map((c) => [c.catalog, c])), [cats]);
  const scope = pickScope(cats, state, hist);
  // one property: its review (status, findings), the running notes' section made from data
  const findings = useReview(scope.oneProp?.cls ?? "course", scope.oneProp?.column ?? null);
  return { state, hist, error, stat, byFolder, findings, ...scope };
}

function useScoreHistories(classes: ClassSlug[]) {
  const [hist, setHist] = useState<Histories>({});
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    let live = true;
    for (const cls of classes) {
      if (hist[cls]) continue;
      api.scoreHistory(cls).then((h) => { if (live) setHist((x) => ({ ...x, [cls]: h })); }, (e) => { if (live) setError(String(e)); });
    }
    return () => { live = false; };
  }, [classes.join(",")]);  // eslint-disable-line react-hooks/exhaustive-deps
  return { hist, error };
}

// each property's status (Needs review / Done), shown beside it in rows by property (learning-programs Phase 6)
function usePropertyStatuses(classes: ClassSlug[]): Statuses {
  const [stat, setStat] = useState<Statuses>({});
  useEffect(() => {
    let live = true;
    for (const cls of classes) api.propertyStatuses(cls).then((x) => live && setStat((s) => ({ ...s, [cls]: x })), () => {});
    return () => { live = false; };
  }, [classes.join(",")]);  // eslint-disable-line react-hooks/exhaustive-deps
  return stat;
}

function pickScope(cats: CatalogCard[], state: HomeState, hist: Histories) {
  const catalogs = cats.filter((c) => Object.values(hist).some((h) => h?.catalogs.includes(c.catalog)));
  const pickedCat = state.catalog ? cats.find((c) => c.short === state.catalog) ?? null : null;
  const options = state.classes.flatMap((cls) => (hist[cls]?.properties ?? []).map((p) => ({ cls, column: p.column, name: termOf(p) })));
  const on = (cls: ClassSlug, col: string) => !state.props || state.props.has(`${cls}:${col}`);
  const tickedAll = options.filter((o) => on(o.cls, o.column));
  const oneProp = tickedAll.length === 1 ? tickedAll[0] : null;
  return { catalogs, pickedCat, options, on, oneProp, scope: scopeOf(!!pickedCat, !!oneProp) };
}

function Toolbar({ view }: { view: ScoreView }) {
  const { state } = view;
  const set: SetHome = (x) => goHome({ ...state, ...x });
  return (
    <div className="hm-tools">
      <ScopeMenus view={view} set={set} />
      {view.scope === "all" && <RowsSwitch state={state} set={set} />}
      <span className="grow" />
      {view.scope !== "one" && <BarsSwitch state={state} set={set} />}
    </div>
  );
}

function ScopeMenus({ view, set }: { view: ScoreView; set: SetHome }) {
  const { state, catalogs, pickedCat, oneProp, options } = view;
  return <>
    <CatalogsMenu picked={pickedCat?.short ?? null} catalogs={catalogs.map((c) => ({ short: c.short, name: c.name }))}
      onChange={(c) => set({ catalog: c })} />
    <ClassesMenu picked={oneProp ? [oneProp.cls] : state.classes} info={historyInfo(view.hist)} onChange={(c) => set({ classes: c, props: null })}
      note="A table for each ticked class, one above the next" />
    <PropertiesMenu classes={state.classes} options={options} picked={state.props} onChange={(p) => set({ props: p })} />
  </>;
}

function RowsSwitch({ state, set }: { state: HomeState; set: SetHome }) {
  return (
    <span className="hm-rows">Rows
      <span className="seg xs" role="group" aria-label="Rows">
        <button className={state.rows === "catalogs" ? "on" : ""} onClick={() => set({ rows: "catalogs" })}>Catalogs</button>
        <button className={state.rows === "properties" ? "on" : ""} onClick={() => set({ rows: "properties" })}>Properties</button>
      </span></span>
  );
}

function BarsSwitch({ state, set }: { state: HomeState; set: SetHome }) {
  return (
    <span className="seg xs" role="group" aria-label="Bars or numbers">
      <button className={!state.numbers ? "on" : ""} onClick={() => set({ numbers: false })}>Bars</button>
      <button className={state.numbers ? "on" : ""} onClick={() => set({ numbers: true })}>Numbers</button>
    </span>
  );
}

function Legend() {
  return (
    <div className="sv-legend">
      {SHOWN.map((o) => <span key={o} className="evx-k"><i className={`sw o-${o}`} />{WORD[o]}</span>)}
      <span className="muted">Golden: scored against human-reviewed values. Silver: against rule-matched values. Dotted line: the 90% target.</span>
    </div>
  );
}

function ClassSection({ cls, view }: { cls: ClassSlug; view: ScoreView }) {
  const h = view.hist[cls];
  if (!h) return <section className="sv-sec"><div className="sv-h"><h2>{CLASS_NAME[cls]}</h2></div><SkelTable label={`Loading ${CLASS_NAME[cls]} scores`} rows={5} cols={6} /></section>;
  const props = h.properties.filter((p) => view.on(cls, p.column));
  if (!props.length) return null;
  const { pickedCat } = view;
  const inCats = pickedCat ? (h.catalogs.includes(pickedCat.catalog) ? [pickedCat.catalog] : []) : h.catalogs;
  if (!inCats.length) return <NoRules cls={cls} pickedCat={pickedCat} />;
  if (view.scope === "one" && pickedCat && view.oneProp) return <OnePropertyScores cls={cls} h={h} cat={pickedCat} column={view.oneProp.column} view={view} />;
  return <ScoreTableSection cls={cls} h={h} table={scoreTable(cls, props, inCats, view)} view={view} />;
}

function NoRules({ cls, pickedCat }: { cls: ClassSlug; pickedCat: CatalogCard | null }) {
  return <section className="sv-sec" data-class={cls}><div className="sv-h"><h2>{CLASS_NAME[cls]}</h2>
    <span className="muted">{pickedCat ? `No ${CLASS_NAME[cls]} rules in ${pickedCat.name} yet.` : `No catalog has ${CLASS_NAME[cls]} rules yet.`}</span></div></section>;
}

function OnePropertyScores({ cls, h, cat, column, view }: { cls: ClassSlug; h: ScoreHistory; cat: CatalogCard; column: string; view: ScoreView }) {
  const { review, reload, catalogName } = view.findings;
  const p = h.properties.find((x) => x.column === column)!;
  return <><OneProperty h={h} cls={cls} cat={cat} name={termOf(p)} col={p.column} short={cat.short} />
    <FindingsTable cls={cls} col={p.column} review={review} reload={reload} catalogName={catalogName} /></>;
}

function ScoreTableSection({ cls, h, table, view }: { cls: ClassSlug; h: ScoreHistory; table: ScoreTable; view: ScoreView }) {
  const shown = table.rows.filter((r) => isScored(h, r.pairs));
  const left = table.rows.length - shown.length;
  const { findings: { review, reload, catalogName }, oneProp, scope } = view;
  return (
    <section className="sv-sec" data-class={cls}>
      <div className="sv-h"><h2>{CLASS_NAME[cls]}</h2><span className="muted">{table.sub}</span></div>
      {shown.length ? <Table h={h} rows={shown} first={table.first} numbers={view.state.numbers} evals={scope === "catalog"} />
        : <p className="muted sv-empty">{NOT_SCORED}</p>}
      {shown.length > 0 && left > 0 && <p className="faint sv-left">{left} {left === 1 ? singular(table.unscored) : table.unscored} not scored yet.</p>}
      {scope === "property" && oneProp && <FindingsTable cls={cls} col={oneProp.column} review={review} reload={reload} catalogName={catalogName} />}
    </section>
  );
}

function Table({ h, rows, first, numbers, evals }: { h: ScoreHistory; rows: Row[]; first: string; numbers: boolean; evals: boolean }) {
  return (
    <table className={`sv-table${numbers ? " nums" : ""}`}>
      <ScoreTableHead target={h.target} first={first} numbers={numbers} evals={evals} />
      {rows.map((r) => (
        <tbody key={r.key} className={r.strong ? "strong" : ""} data-row={r.key}>
          {TREES.map((t, i) => <TreeRow key={t} h={h} row={r} tree={t} first={i === 0} numbers={numbers} evals={evals} />)}
        </tbody>
      ))}
    </table>
  );
}

function ScoreTableHead({ target, first, numbers, evals }: { target: number; first: string; numbers: boolean; evals: boolean }) {
  return (
    <thead><tr>
      <th className="sv-hd">{first}</th><th className="sv-tr" />
      {numbers ? <NumberHeads /> : <BarHeads target={target} />}
      <th className="sv-hs">Last 7 outputs</th>{evals && <th />}
    </tr></thead>
  );
}

function NumberHeads() {
  return <>{SHOWN.map((o) => <th key={o} className={`n c-${o}`}>{WORD[o]}</th>)}<th className="sv-n c-match">exact %</th></>;
}

function BarHeads({ target }: { target: number }) {
  return <><th className="sv-b">Latest extract output<span className="sv-90" style={{ left: `${100 * target}%` }}>{Math.round(100 * target)}%</span></th>
    <th className="sv-n c-match">exact</th><th className="sv-n c-partial">partial</th></>;
}

function TreeRow({ h, row: r, tree: t, first, numbers, evals }: TreeRowProps) {
  const c = latest(h, r.pairs, t), ex = exactOf(c);
  return (
    <tr className={`t-${t}`}>
      {first && <td className="sv-hd" rowSpan={2}>{r.open ? <a href={r.open}>{r.head}</a> : r.head}</td>}
      <td className="sv-tr">{TREE_NAME[t]}</td>
      <LatestCells c={c} target={h.target} numbers={numbers} />
      <td className={exactClass(ex, h.target)}>{pct(ex)}</td>
      {!numbers && <td className="sv-n">{pct(partialOf(c))}</td>}
      <td className="sv-hs"><HistoryBars points={series(h, r.pairs, t)} target={h.target} /></td>
      {evals && <td className="sv-ev">{first && r.evals && <a href={r.evals}>Evals →</a>}</td>}
    </tr>
  );
}

function LatestCells({ c, target, numbers }: { c: Counts | null; target: number; numbers: boolean }) {
  if (numbers) return <>{SHOWN.map((o) => <td key={o} className="sv-n">{c ? fmt(c[o]) : "—"}</td>)}</>;
  return <td className="sv-b"><OutcomeBar c={c} target={target} /></td>;
}

/** One catalog, one property: its scores over time, Golden and Silver side by side, then each score. */
function OneProperty({ h, cls, cat, name, col, short }: { h: ScoreHistory; cls: ClassSlug; cat: CatalogCard; name: string; col: string; short: string }) {
  const lines: ScoreLine[] = (h.history[cat.catalog]?.[col] ?? []).slice(-7);
  return (
    <section className="sv-sec" data-class={cls}>
      <div className="sv-h"><h2>{CLASS_NAME[cls]}</h2><span className="muted">{cat.name}, {name}, the last {lines.length || 7} scores</span>
        <span className="grow" />
        <a className="sv-evals" href={href(short, "evals", null, { col }, cls)}>Open {cat.name}'s Evals tab at {name} →</a></div>
      {!lines.length ? <p className="muted">{NOT_SCORED}</p> : <PropertyHistory h={h} pair={[[cat.catalog, col]]} lines={lines} />}
    </section>
  );
}

function PropertyHistory({ h, pair, lines }: { h: ScoreHistory; pair: Pair[]; lines: ScoreLine[] }) {
  return <>
    <PropertyCharts h={h} pair={pair} />
    <table className="sv-table">
      <thead><tr><th className="sv-hd">Score</th><th className="sv-tr" />
        <BarHeads target={h.target} /><th className="sv-sw">Scored with</th></tr></thead>
      {[...lines].reverse().map((l) => (
        <tbody key={l.score} data-score={l.score}>
          {TREES.map((t, i) => <ScoreLineRow key={t} h={h} line={l} tree={t} first={i === 0} />)}
        </tbody>
      ))}
    </table>
  </>;
}

function PropertyCharts({ h, pair }: { h: ScoreHistory; pair: Pair[] }) {
  return (
    <div className="sv-charts">
      {TREES.map((t) => (
        <div key={t}><div className="sv-ch"><b>{TREE_NAME[t]}</b> against {t === "golden" ? "human-reviewed" : "rule-matched"} values</div>
          <HistoryBars points={series(h, pair, t)} target={h.target} big /></div>))}
    </div>
  );
}

function ScoreLineRow({ h, line: l, tree: t, first }: { h: ScoreHistory; line: ScoreLine; tree: Tree; first: boolean }) {
  const c = l[t] ? { ...l[t]! } as Counts : null, ex = exactOf(c);
  return (
    <tr>
      {first && <td className="sv-hd" rowSpan={2}>{when(l.at)}<div className="faint">{TRIGGER[l.trigger] ?? l.trigger}</div></td>}
      <td className="sv-tr">{TREE_NAME[t]}</td>
      <td className="sv-b"><OutcomeBar c={c} target={h.target} /></td>
      <td className={exactClass(ex, h.target)}>{pct(ex)}</td>
      <td className="sv-n">{pct(partialOf(c))}</td>
      {first && <td className="sv-sw" rowSpan={2}>
        <div><span className="muted">golden</span> <b>{l.golden_version}</b></div>
        {scoredWith(l) && <div><span className="muted">xtra-cli</span> <b>{scoredWith(l)}</b></div>}</td>}
    </tr>
  );
}

function HistoryAxis({ f, target, big }: { f: Frame; target: number; big?: boolean }) {
  return <>
    <text x={f.L - 4} y={f.y(1) + 3} className="ax" textAnchor="end">100</text>
    {big && <text x={f.L - 4} y={f.y(target) + 3} className="ax" textAnchor="end">{Math.round(100 * target)}</text>}
    <text x={f.L - 4} y={f.y(0)} className="ax" textAnchor="end">0</text>
    <line x1={f.L} x2={f.L} y1={f.y(1)} y2={f.y(0)} className="axis" />
  </>;
}

function HistoryBar({ p, x, f, big }: { p: Point; x: number; f: Frame; big?: boolean }) {
  return (
    <g>
      <title>{`${when(p.at)}, ${p.kind === "golden" ? "golden published" : "extract output"}: ${pct(exactOf(p.c))} exact`}</title>
      {stackedRects(p.c, x, f, big)}
      {big && <text x={x + f.bw / 2} y={f.y(0) + 14} className={`kind ${p.kind}`} textAnchor="middle">{p.kind}</text>}
    </g>
  );
}

function stackedRects(c: Counts, x: number, f: Frame, big?: boolean) {
  let acc = 0;
  return SHOWN.map((o) => {
    const share = c.values ? c[o] / c.values : 0;
    if (!share) return null;
    const r = <rect key={o} x={x} y={f.y(acc + share)} width={f.bw} height={Math.max(0, share * f.H - (big ? 0 : 0.6))} className={`f-${o}`} />;
    acc += share;
    return r;
  });
}

function PropertyRowHead({ p, status: st }: { p: Property; status: string | undefined }) {
  return <span className="sv-prop"><span><span className="mono">{termOf(p)}</span>
    {st && <span className={`sv-status ${st === "done" ? "done" : "review"}`} data-testid="property-status-tag">{st === "done" ? "✓ Done" : "Needs review"}</span>}</span>
    <span className="faint mono">{TIER_WORD[p.tier]}</span></span>;
}

function CatalogRowHead({ catalog: c, folder }: { catalog: CatalogCard | undefined; folder: string }) {
  return <span className="sv-cat">{c?.logo ? <img src={c.logo} alt="" /> : <i />}<b>{c?.name ?? folder}</b></span>;
}

function scoreTable(cls: ClassSlug, props: Property[], inCats: string[], view: ScoreView): ScoreTable {
  const byProperty = view.scope === "catalog" || (view.scope === "all" && view.state.rows === "properties");
  return byProperty ? propertyTable(cls, props, inCats, view) : catalogTable(props, inCats, view);
}

function propertyTable(cls: ClassSlug, props: Property[], inCats: string[], { scope, state, stat, byFolder }: ScoreView): ScoreTable {
  const one = scope === "catalog";
  const rows = props.map((p) => ({
    key: p.column, head: <PropertyRowHead p={p} status={stat[cls]?.[p.column]?.status} />, pairs: inCats.map((c) => [c, p.column] as Pair),
    open: homeHref({ ...state, classes: [cls], props: new Set([`${cls}:${p.column}`]) }),  // one property: its class
    evals: one ? href(shortOf(byFolder, inCats[0]), "evals", null, { col: p.column }, cls) : undefined,
  }));
  return { rows, first: "Property", sub: propertySub(props.length, inCats, one, byFolder), unscored: "properties" };
}

function catalogTable(props: Property[], inCats: string[], { state, byFolder, oneProp }: ScoreView): ScoreTable {
  const cols = props.map((p) => p.column);
  const rows: Row[] = inCats.map((c) => ({
    key: c, head: <CatalogRowHead catalog={byFolder.get(c)} folder={c} />, pairs: cols.map((col) => [c, col] as Pair),
    open: homeHref({ ...state, catalog: shortOf(byFolder, c) }),
  }));
  if (rows.length > 1) rows.push({ key: "all", head: <b>All</b>, pairs: inCats.flatMap((c) => cols.map((col) => [c, col] as Pair)), strong: true });
  return { rows, first: "Catalog", sub: catalogSub(inCats.length, oneProp?.name ?? null), unscored: "catalogs" };
}

function propertySub(count: number, inCats: string[], one: boolean, byFolder: Map<string, CatalogCard>): string {
  const nP = `${count} propert${count === 1 ? "y" : "ies"}`;
  if (one) return `${byFolder.get(inCats[0])?.name}, ${nP}. A property opens its history.`;
  return inCats.length === 1 ? `${nP} in ${byFolder.get(inCats[0])?.name ?? inCats[0]}. A property opens it there.`
    : `${nP}, each over every catalog. A property opens it in each catalog.`;
}

function catalogSub(count: number, onePropName: string | null): string {
  if (onePropName !== null) return `${onePropName} in ${count} catalog${count === 1 ? "" : "s"}. A catalog opens its history.`;
  return count === 1 ? `1 catalog, over its scored properties. The catalog opens its properties.`
    : `${count} catalogs, each over its scored properties. A catalog opens its properties.`;
}

function historyFrame(big: boolean): Frame {
  const W = big ? 680 : 150, H = big ? 210 : 30, L = big ? 26 : 22, B = big ? 34 : 12, T = 4;
  const slot = (W - L) / 7, bw = slot * (big ? 0.92 : 0.7);
  return { W, H, L, B, T, slot, bw, y: (f: number) => T + (1 - f) * H };
}

function historyInfo(hist: Histories): Record<string, ClassInfo> {
  return Object.fromEntries(Object.entries(hist).map(([k, h]) =>
    [k, { slug: k, properties: h!.properties.length, catalogs: h!.catalogs.length } as ClassInfo]));
}

function isScored(h: ScoreHistory, pairs: Pair[]): boolean {
  return pairs.some(([c, col]) => (h.history[c]?.[col] ?? []).length > 0);
}

function shortOf(byFolder: Map<string, CatalogCard>, folder: string): string {
  return byFolder.get(folder)?.short ?? folder;
}

function singular(plural: string): string {
  return plural.replace(/ies$/, "y").replace(/s$/, "");
}

function exactClass(ex: number | null, target: number): string {
  return `sv-n sv-ex${ex !== null && ex < target ? " under" : ""}`;
}

function countsTip(c: Counts): string {
  return `${SHOWN.map((o) => `${fmt(c[o])} ${WORD[o]}`).join(", ")}, of ${fmt(c.values)} values`;
}

function day(iso: string): string {
  return new Date(iso).toLocaleDateString("en-GB", { day: "numeric", month: "short" });
}

function when(iso: string): string {
  return new Date(iso).toLocaleString("en-GB", { day: "numeric", month: "short", hour: "numeric", minute: "2-digit", hour12: true })
    .replace(" am", " AM").replace(" pm", " PM");
}
