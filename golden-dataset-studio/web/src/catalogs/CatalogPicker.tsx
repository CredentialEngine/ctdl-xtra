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
import { SkelTable } from "../shell/Skeleton";
import katex from "katex";
import "katex/dist/katex.min.css";
import { Fragment, useCallback, useEffect, useState, type ReactNode } from "react";
import { api } from "../api/client";
import type { CatalogCard, CatalogSummary, CatalogsSummary } from "../api/types";
import { Tip } from "../evals/EvalsTab";
import { CLASS_NAME, CLASS_SLUGS, href, useRoute, type ClassSlug } from "../shell/router";
import { fmt, fmtDate, Ico } from "../shell/ui";
import { AddCatalogModal } from "./AddCatalogModal";
import { GenerateRulesModal } from "./GenerateRulesModal";
import { goHome, readHome, type HomeState } from "./homeState";
import { LoopModal, shouldShowLoop } from "./LoopModal";
import { ClassesMenu, type ClassInfo } from "./menus";
import { ScoreViews } from "./ScoreViews";
import "../evals/evals.css";
import "./ctab.css";
import "./scores.css";

type Summaries = Partial<Record<ClassSlug, CatalogsSummary>>;
type Catalogs = ReturnType<typeof useCatalogs>;
type Modals = ReturnType<typeof useHomeModals>;
interface ColumnGroup { cls: ClassSlug; s: CatalogsSummary; req: string[]; ph1: string[]; ph2: string[]; open: boolean }
interface ContentProps {
  state: HomeState; home: Catalogs; modals: Modals; p2: Set<ClassSlug>; showP2: (cls: ClassSlug) => void; head: ReactNode;
}
interface TableProps { cats: CatalogCard[]; groups: ColumnGroup[]; modals: Modals; load: () => void; showP2: (cls: ClassSlug) => void }

const STEP: Record<string, string> = {
  starting: "Starting…", copying: "Copying pages…", indexing: "Indexing pages…", assets: "Saving page styles…",
  done: "Finishing…",
};

export default function CatalogPicker() {
  const state = readHome(useRoute().params);
  const home = useCatalogs();
  const modals = useHomeModals(home.load);
  const [p2, setP2] = useState<Set<ClassSlug>>(new Set());  // the classes whose Phase 2 columns are shown
  const showP2 = (cls: ClassSlug) => setP2((x) => new Set([...x, cls]));
  return (
    <div className="picker">
      <PickerContent state={state} home={home} modals={modals} p2={p2} showP2={showP2}
        head={<PickerHead state={state} sums={home.sums} onAdd={modals.showAdd} />} />
      {modals.modal}
    </div>
  );
}

function PickerContent({ state, home, modals, p2, showP2, head }: ContentProps) {
  const { cats, sums, error } = home;
  if (error) return <div className="picker-in ctab-page">{head}<p className="muted">{error}</p></div>;
  if (!cats) return <div className="picker-in ctab-page">{head}</div>;
  if (state.view === "score") {
    return (
      <div className="picker-in ctab-page sv-page">{head}<ScoreViews cats={cats} state={state} />
        <button className="loop-again" onClick={modals.showLoop}>How the Studio works</button></div>
    );
  }
  // the golden view: each ticked class's columns, side by side under its heading, in the three tiers (once every
  // ticked class's summary is here, so columns don't move)
  if (state.classes.some((c) => !sums[c])) return <div className="picker-in ctab-page">{head}<SkelTable label="Loading catalogs" rows={6} cols={14} /></div>;
  const groups = columnGroups(state.classes, sums, p2);
  return <div className="picker-in ctab-page">{head}<GoldenView cats={cats} groups={groups} modals={modals} load={home.load} showP2={showP2} /></div>;
}

function PickerHead({ state, sums, onAdd }: { state: HomeState; sums: Summaries; onAdd: () => void }) {
  return (
    <div className="picker-head">
      <h1>Catalogs</h1>
      <ViewSwitch state={state} />
      {state.view === "golden" && <ClassesMenu picked={state.classes} info={classInfo(sums)} onChange={(c) => goHome({ ...state, classes: c })}
        note="Columns for each ticked class, side by side" />}
      <span className="grow" />
      <button className="btn" onClick={onAdd}>+ Add a catalog</button>
    </div>
  );
}

function ViewSwitch({ state }: { state: HomeState }) {
  const view = state.view;
  return (
    <span className="seg" role="group" aria-label="View">
      <button className={view === "golden" ? "on" : ""} onClick={() => goHome({ ...state, view: "golden" })}>Golden dataset</button>
      <button className={view === "score" ? "on" : ""} onClick={() => goHome({ ...state, view: "score" })}>xtra score</button>
    </span>
  );
}

function GoldenView(table: TableProps) {
  return (
    <>
      <div className="ctab-wrap"><GoldenTable {...table} /></div>
      <div className="ctab-key"><span><b>Bold</b>required</span><span>Regular: the rest of Phase 1</span>
        <span>+ Phase 2: click to show its columns</span></div>
      <button className="loop-again" onClick={table.modals.showLoop}>How the Studio works</button>
    </>
  );
}

function GoldenTable(table: TableProps) {
  return (
    <table className="ctab">
      <thead>
        <ClassHeadRow groups={table.groups} />
        <ColumnHeadRow groups={table.groups} showP2={table.showP2} />
      </thead>
      <tbody>
        {table.cats.map((c) => <CatalogRow key={c.catalog} card={c} {...table} />)}
      </tbody>
    </table>
  );
}

function ClassHeadRow({ groups }: { groups: ColumnGroup[] }) {
  return (
    <tr className="cls-row"><th colSpan={3} className="fixed" /><th className="gap" />
      {groups.map((g) => (
        <th key={g.cls} colSpan={groupWidth(g)} data-class={g.cls}><span className="in"><b>{CLASS_NAME[g.cls]}</b>
          {g.req.length} required, {g.ph1.length} more in Phase 1, {g.ph2.length} in Phase 2</span></th>))}
      <th className="fixed right" /></tr>
  );
}

function ColumnHeadRow({ groups, showP2 }: { groups: ColumnGroup[]; showP2: (cls: ClassSlug) => void }) {
  return (
    <tr>
      <th className="act" /><th className="logo" /><th className="name plain">Catalog</th><th className="date plain">Pages from</th>
      {groups.map((g) => <Fragment key={g.cls}>
        {g.req.map((k, i) => <PropertyHead key={`${g.cls}:${k}`} group={g} column={k} start={i === 0} />)}
        {g.ph1.map((k, i) => <PropertyHead key={`${g.cls}:${k}`} group={g} column={k} start={i === 0} />)}
        {g.open ? g.ph2.map((k, i) => <PropertyHead key={`${g.cls}:${k}`} group={g} column={k} start={i === 0} />)
          : g.ph2.length > 0 && <th className="rot p2 tier-start" title="Show the Phase 2 columns"
            onClick={() => showP2(g.cls)}><span>+ {g.ph2.length} Phase 2</span></th>}
      </Fragment>)}
      <th className="cov plain">Coverage</th>
    </tr>
  );
}

function PropertyHead({ group: g, column: k, start }: { group: ColumnGroup; column: string; start: boolean }) {
  return <th className={`rot${g.req.includes(k) ? " req" : ""}${start ? " tier-start" : ""}`}><span>{g.s.labels[k] ?? k}</span></th>;
}

function CatalogRow({ card: c, groups, modals, load }: TableProps & { card: CatalogCard }) {
  const isReady = c.status === "ready";
  return (
    <tr className={rowClass(c)}>
      <td className="act"><RowAction card={c} load={load} onGenerate={modals.setGenerate} /></td>
      <td className="logo">{c.logo && <img src={c.logo} alt={`${c.name} logo`} />}</td>
      <td className="name"><span className="nm">{c.institution}</span></td>
      <td className="date" title={c.pages != null ? `${fmt(c.pages)} pages in this crawl` : undefined}>{c.crawl ? fmtDate(c.crawl) : "—"}</td>
      {!isReady
        ? <td colSpan={groups.reduce((n, g) => n + groupWidth(g), 0)} className="c faint why" title={c.adding?.error ?? undefined}>{whyNotReady(c)}</td>
        : groups.map((g) => <ClassCells key={g.cls} card={c} group={g} />)}
      <td className="cov">{isReady ? groups.map((g) => <ClassCoverage key={g.cls} card={c} group={g} />) : <span className="faint">—</span>}</td>
    </tr>
  );
}

function RowAction({ card: c, load, onGenerate }: { card: CatalogCard; load: () => void; onGenerate: (c: CatalogCard) => void }) {
  if (c.status === "ready") return <a className="btn sm" href={href(c.short, "rules")}>Open →</a>;
  if (c.status === "failed") return <button className="btn sm" onClick={() => api.dismissAdd(c.catalog).then(load)}>Dismiss</button>;
  if (c.status === "not imported" && c.pages) {
    return <button className="btn sm" onClick={() => onGenerate(c)}><Ico name="spark" />Generate rules</button>;
  }
  return null;
}

function ClassCells({ card: c, group: g }: { card: CatalogCard; group: ColumnGroup }) {
  const s = g.s.catalogs[c.catalog];
  if (!s) {
    return <td colSpan={groupWidth(g)} className="nosrc tier-start">
      {(c.not_sources ?? []).includes(g.cls) ? `Not a ${CLASS_NAME[g.cls]} source` : `No ${CLASS_NAME[g.cls]} rules yet`}</td>;
  }
  return <>
    <GoldenCells s={s} cols={g.req} start />
    <GoldenCells s={s} cols={g.ph1} start />
    {g.open ? <GoldenCells s={s} cols={g.ph2} start />
      : g.ph2.length > 0 && <td className="p2c tier-start" title="Phase 2 properties with a rule here">
        {g.ph2.filter((k) => s.columns[k] && !s.columns[k].no_rule).length} of {g.ph2.length}</td>}
  </>;
}

function ClassCoverage({ card: c, group: g }: { card: CatalogCard; group: ColumnGroup }) {
  const s = g.s.catalogs[c.catalog];
  return s ? <span className="cl"><b>{s.coverage}</b> <span className="faint">of {g.s.properties} {CLASS_NAME[g.cls]}</span></span> : null;
}

/** Golden dataset: per property, its values in the golden dataset as a fraction ("—" with no rule in this catalog).
 * `start`: the first column of a tier, set apart by a rule. */
function GoldenCells({ s, cols, start }: { s: CatalogSummary; cols: string[]; start?: boolean }) {
  return (
    <>
      {cols.map((k, i) => <GoldenCell key={k} column={k} st={s.columns[k]} edge={start && i === 0 ? " tier-start" : ""} />)}
    </>
  );
}

function GoldenCell({ column: k, st, edge }: { column: string; st: CatalogSummary["columns"][string] | undefined; edge: string }) {
  if (!st || st.no_rule) return <td className={`c faint${edge}`}>—</td>;
  return (
    <td className={"c frac " + st.status.replace(" ", "-") + edge} aria-label={`${k}: ${st.status}`}>
      <Tip tip={fractionTip(st.human, st.found, st.status)} width={300} delay={1000}>
        <span tabIndex={0} className="fr" dangerouslySetInnerHTML={katexHtml(fractionTex(st.human, st.found))} />
      </Tip>
    </td>
  );
}

function useCatalogs() {
  const [cats, setCats] = useState<CatalogCard[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const load = useCallback(() => api.catalogs().then(setCats, (e) => setError(String(e))), []);
  useEffect(() => { load(); }, [load]);
  const added = useFollowAdding(cats, load);
  const sums = useClassSummaries(added, setError);
  return { cats, sums, error, load };
}

// while a catalog is being added, follow its progress; once it's added, its row's summary
function useFollowAdding(cats: CatalogCard[] | null, load: () => void): number {
  const busy = !!cats?.some((c) => c.status === "adding");
  const [added, setAdded] = useState(0);
  useEffect(() => {
    if (!busy) return;
    const t = window.setInterval(load, 2000);
    return () => { window.clearInterval(t); setAdded((n) => n + 1); };
  }, [busy, load]);
  return added;
}

// every class's summary: the Classes menu says what each has, the table shows the ticked ones
function useClassSummaries(added: number, setError: (e: string) => void): Summaries {
  const [sums, setSums] = useState<Summaries>({});
  useEffect(() => {
    let live = true;
    for (const cls of CLASS_SLUGS) {
      api.catalogsSummary("human", cls).then((s) => live && setSums((x) => ({ ...x, [cls]: s })), (e) => live && setError(String(e)));
    }
    return () => { live = false; };
  }, [added]);
  return sums;
}

function useHomeModals(load: () => void) {
  const [loop, setLoop] = useState(shouldShowLoop);
  const [adding, setAdding] = useState(false);
  const [generate, setGenerate] = useState<CatalogCard | null>(null);
  const modal = (loop && <LoopModal onClose={() => setLoop(false)} />)
    || (adding && <AddCatalogModal onClose={() => setAdding(false)} onAdded={load} />)
    || (generate && <GenerateRulesModal card={generate} onClose={() => { setGenerate(null); load(); }} />);
  return { modal, showLoop: () => setLoop(true), showAdd: () => setAdding(true), setGenerate };
}

function columnGroups(classes: ClassSlug[], sums: Summaries, p2: Set<ClassSlug>): ColumnGroup[] {
  return classes.flatMap((cls) => {
    const s = sums[cls];
    if (!s) return [];
    const tier = (k: string) => s.tiers?.[k] ?? (s.required.includes(k) ? "required" : "phase1");
    const inTier = (t: string) => s.columns.filter((k) => tier(k) === t);
    return [{ cls, s, req: inTier("required"), ph1: inTier("phase1"), ph2: inTier("phase2"), open: p2.has(cls) }];
  });
}

function groupWidth(g: ColumnGroup): number {
  return g.req.length + g.ph1.length + (g.open ? g.ph2.length : g.ph2.length ? 1 : 0);
}

function classInfo(sums: Summaries): Record<string, ClassInfo> {
  return Object.fromEntries(Object.entries(sums).map(([k, s]) =>
    [k, { slug: k, properties: s!.properties, catalogs: Object.keys(s!.catalogs).length } as ClassInfo]));
}

function rowClass(c: CatalogCard): string {
  const inFlight = c.status === "adding" || c.status === "failed";
  return c.status === "ready" ? "" : `off ${inFlight ? c.status : ""}`;
}

function whyNotReady(c: CatalogCard): string {
  if (c.status === "adding" || c.status === "failed") return addingText(c);
  return c.status === "not imported" ? (c.pages ? "no rules yet" : "pages not indexed") : "";
}

function addingText(c: CatalogCard): string {
  const a = c.adding;
  if (!a) return "";
  if (c.status === "failed") return "Couldn't add it";
  return a.step === "copying" && a.total ? `Copying pages… ${Math.floor((100 * a.done) / a.total)}%` : STEP[a.step] ?? "Adding…";
}

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

/** LaTeX for a count: thousands with a thin comma (1{,}048). */
const tex = (n: number) => fmt(n).replace(/,/g, "{,}");
const katexHtml = (src: string) => ({ __html: katex.renderToString(src, { throwOnError: false }) });
