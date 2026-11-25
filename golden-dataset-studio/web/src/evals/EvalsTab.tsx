// Evals (docs/qrspi/evals/03-spec.md §6.3–6.4): how closely xtra's extract outputs match the golden dataset, scored
// by xtra's own scorer. The title is the comparison ([golden side] vs `xtra catalog extract` outputs over time), with
// the slim switch "scored against Human-reviewed | Rule-matched" at its right. Under it, one bar per extract output
// the Studio has seen; clicking one picks it, and a dashed bar (not scored against this golden side yet) holds the only
// Score button. Then the chosen pair as two chips, the exact matches, one bar per column, the outcome filter, Group
// by and the values. A value opens the shared diff (Split / Unified) with a note box and the saved page beside it.
//
// URL: #/c/<catalog>/evals?b=human|rule&g=<golden>&x=<output>&col=<column>&subj=<subject>&o=<outcome>&grp=column|subject
//      &off=<offset>&row=<row key>&wk=label|shape|diff|subject (Where it's wrong's grouping; none = auto)
//
// sme-fixes spec §8.4: each bar has an extra segment (striped: candidates with no golden value) and an unsure one; a
// column shows found (recall) and right (precision), and for a list property (durations) the courses exact; "Where
// it's wrong" groups the units that aren't a match, each group linking to its courses in the Rules tab. A column
// with no score says why with two facts: its candidates (values in xtra's extract output) and its golden values
// (rule-matched values on the Rule-matched side).
import { useCallback, useEffect, useMemo, useState } from "react";
import { api } from "../api/client";
import type { CatalogDetail, CatalogsSummary, ClassSummary, ExtractOutputs, ScoreBasis, ScoreDoc, ScoreRow, ScoreValues } from "../api/types";
import { useReviewer } from "../shell/reviewer";
import { go, href, type ClassSlug } from "../shell/router";
import { inClass } from "../shell/klass";
import type { TabProps } from "../shell/tabProps";
import { fmt, toast, useKeyHints } from "../shell/ui";
import { DiffModeSwitch } from "../valuediff/ValueDiff";
import { fmtDay, fmtDayTime } from "../valuediff/diff";
import { GoldenPicker } from "./GoldenPicker";
import { History, OutcomeLegend, PlainLegend } from "./History";
import { InfoModal } from "./InfoModal";
import { basisOf, queryParams, readQuery, type EvalsQuery, type NavChange } from "./query";
import { RowPanel } from "./RowPanel";
import { goldenName, HUMAN, outcomesOf, scoreFor, total, type Output } from "./score";
import { ScoreBody, type ScoreContext } from "./ScoreBody";
import { BASIS_TIP, MiniBar, Tip } from "./Tip";
import "./evals.css";

export { rowText } from "./ScoreBody";
export { scoreFor, shown, unscoredFacts } from "./score";
export { Tip } from "./Tip";

interface ClassOutputs { cls: ClassSlug; name: string; idx: ExtractOutputs | null }
interface ClassHistoryProps { entry: ClassOutputs; legend: boolean; cat: string; basis: ScoreBasis; onScored: () => void }
type LoadedState = ReturnType<typeof useOneClass> & { idx: ExtractOutputs };
interface PageProps { catalog: CatalogDetail; me: string; evals: LoadedState }

export default function EvalsTab(props: TabProps) {
  return props.route.cls === "all" ? <AllClasses {...props} /> : <OneClass {...props} />;
}

/** All classes (approved item 18; mockup w2-evals-all): one row of bars per class, each against its own golden dataset.
 * A bar opens that class's Evals at that extract output. */
function AllClasses({ catalog, route }: TabProps) {
  const basis = basisOf(route.params);
  const { each, reload } = useClassOutputs(catalog);
  useCliHint();
  if (!each) return <div className="evx" />;
  return (
    <div className="evx">
      <section className="evx-main">
        <AllClassesTitle cat={catalog.short} basis={basis} />
        {each.map((entry, i) => <ClassHistory key={entry.cls} entry={entry} legend={i === 0} cat={catalog.short} basis={basis} onScored={reload} />)}
      </section>
    </div>
  );
}

function OneClass({ catalog, route }: TabProps) {
  const me = useReviewer();
  const evals = useOneClass(catalog.short, route.params);
  useCliHint();
  const startScore = useStartScore(catalog.short, evals.golden, me, evals.loadIndex);
  if (evals.error) return <div className="doc"><div className="doc-in"><p className="muted">{evals.error}</p></div></div>;
  if (!evals.idx) return <div className="evx" />;
  return <OneClassPage catalog={catalog} me={me} evals={{ ...evals, idx: evals.idx }} onScore={startScore} />;
}

// --- All classes -------------------------------------------------------------------------------------------------
function useClassOutputs(catalog: CatalogDetail) {
  const cat = catalog.short;
  const ruled = (catalog.classes ?? []).filter((c) => c.ruleset_version);
  const [each, setEach] = useState<ClassOutputs[] | null>(null);
  const key = ruled.map((c) => c.slug).join(",");
  const reload = useCallback(() => loadClassOutputs(cat, ruled).then(setEach), [cat, key]);
  useEffect(() => { void reload(); }, [reload]);
  return { each, reload };
}

function useCliHint() {
  useKeyHints(<span><span className="mono">golden-datasets score</span> does the same from the CLI</span>, []);
}

function AllClassesTitle({ cat, basis }: { cat: string; basis: ScoreBasis }) {
  return (
    <header className="evx-title">
      <span className="evx-gchip big">{basis === "human" ? goldenName(HUMAN) : "Silver datasets (rule-matched)"}
        {basis === "human" && <span className="evx-gchip-d"> · as of now</span>}</span>
      <OutputsOverTime />
      <span className="grow" />
      <BasisSwitch basis={basis} onHuman={() => go(href(cat, "evals", null, {}), true)} onRule={() => go(href(cat, "evals", null, { b: "rule" }), true)} />
    </header>
  );
}

function ClassHistory({ entry: { cls, name, idx }, legend, cat, basis, onScored }: ClassHistoryProps) {
  const latestGolden = idx?.latest_golden ?? null;
  const golden = basis === "human" ? HUMAN : latestGolden ?? idx?.goldens[0]?.id ?? "";
  return (
    <div data-class={cls}>
      <h3 className="cls-h3">{name}<span>{latestScoreText(idx?.outputs[0], basis, golden, latestGolden)}</span></h3>
      {idx?.outputs.length
        ? <ClassChart cls={cls} idx={idx} cat={cat} basis={basis} golden={golden} legend={legend} onScored={onScored} />
        : <p className="muted evx-empty">{idx?.error ?? `xtra hasn't written an extract output with ${name} records yet.`}</p>}
    </div>
  );
}

function loadClassOutputs(cat: string, ruled: ClassSummary[]): Promise<ClassOutputs[]> {
  return Promise.all(ruled.map((c) => inClass(c.slug, () => api.extractOutputs(cat))
    .then((idx) => ({ cls: c.slug, name: c.name, idx }), () => ({ cls: c.slug, name: c.name, idx: null }))));
}

function ClassChart({ cls, idx, cat, basis, golden, legend, onScored }: Omit<ClassHistoryProps, "entry"> & {
  cls: ClassSlug; idx: ExtractOutputs; golden: string }) {
  const me = useReviewer();
  const last = idx.outputs[0];
  const pick = (id: string) => go(href(cat, "evals", null, { x: id === last?.id ? null : id, b: basis === "rule" ? "rule" : null }, cls));
  const score = (o: Output) => inClass(cls, () => api.startScore(cat, { golden, output: o.id, by: me })).then(onScored, (e) => toast(String(e)));
  return (
    <div className="evx-chartrow">
      <History outputs={[...idx.outputs].reverse()} latest={last?.id} basis={basis} golden={golden} latestGolden={idx.latest_golden ?? null}
        picked={last?.id ?? null} busy={!!idx.running} onPick={pick} onScore={score} />
      {legend && <PlainLegend />}
    </div>
  );
}

function latestScoreText(last: Output | undefined, basis: ScoreBasis, golden: string, latestGolden: string | null): string {
  const brief = last ? scoreFor(last, basis, golden, latestGolden) : undefined;
  const values = brief?.status === "done" ? total(outcomesOf(brief, basis)) : null;
  return values === null ? "the latest output isn't scored yet" : `${fmt(values)} values scored in the latest output`;
}

// --- One class ---------------------------------------------------------------------------------------------------
function useOneClass(cat: string, params: URLSearchParams) {
  const [error, setError] = useState<string | null>(null);
  const query = useMemo(() => readQuery(params), [params]);
  const nav = useCallback((change: NavChange, keepRow = false) =>
    go(href(cat, "evals", null, { ...queryParams(query, keepRow), ...change }), true), [cat, query]);
  const { idx, loadIndex } = useExtractOutputs(cat, setError);
  const sum = useCatalogsSummary(query.basis);
  const picked = pickScore(idx, query);
  usePollWhileRunning(idx, loadIndex);
  const doc = useScoreDoc(cat, picked.sid, setError);
  const view = useScoreValues(cat, doc, picked.sid, query, setError);
  return { error, query, nav, idx, loadIndex, sum, doc, view, ...picked };
}

function useStartScore(cat: string, golden: string, me: string, loadIndex: () => Promise<void>) {
  return useCallback(async (o: Output) => {
    try { await api.startScore(cat, { golden, output: o.id, by: me }); await loadIndex(); } catch (e) { toast(String(e)); }
  }, [cat, golden, me, loadIndex]);
}

function OneClassPage({ catalog, me, evals, onScore }: PageProps & { onScore: (o: Output) => void }) {
  const [info, setInfo] = useState(false);
  const row = evals.view?.rows.items.find((r) => r.key === evals.query.rowKey) ?? null;
  return (
    <div className={`evx${row ? " with-row" : ""}`}>
      <section className="evx-main">
        <OneClassTitle evals={evals} diffMode={!!row} onInfo={() => setInfo(true)} />
        <OutputsChart evals={evals} onScore={onScore} />
        {evals.output && <PickedOutput catalog={catalog} evals={evals} output={evals.output} />}
      </section>
      {row && <OpenRow catalog={catalog} me={me} evals={evals} row={row} />}
      {info && evals.doc && <InfoModal doc={evals.doc} basis={evals.query.basis} onClose={() => setInfo(false)} />}
    </div>
  );
}

function useExtractOutputs(cat: string, setError: (e: string) => void) {
  const [idx, setIdx] = useState<ExtractOutputs | null>(null);
  const loadIndex = useCallback(() => api.extractOutputs(cat).then(setIdx, (e) => setError(String(e))), [cat, setError]);
  useEffect(() => { void loadIndex(); }, [loadIndex]);
  return { idx, loadIndex };
}

/** Every property's column and its status here (the score lists them all, m8). */
function useCatalogsSummary(basis: ScoreBasis): CatalogsSummary | null {
  const [sum, setSum] = useState<CatalogsSummary | null>(null);
  useEffect(() => {
    let live = true;
    api.catalogsSummary(basis).then((r) => live && setSum(r), () => live && setSum(null));
    return () => { live = false; };
  }, [basis]);
  return sum;
}

/** The golden side, the extract output and the score the URL picks (the latest of each by default). */
function pickScore(idx: ExtractOutputs | null, query: EvalsQuery) {
  const latestGolden = idx?.latest_golden ?? null;
  const golden = query.basis === "human" ? HUMAN : query.goldenParam ?? latestGolden ?? idx?.goldens[0]?.id ?? "";
  const outputId = query.outputParam ?? idx?.outputs[0]?.id ?? null;
  const output = idx?.outputs.find((o) => o.id === outputId);
  const brief = output ? scoreFor(output, query.basis, golden, latestGolden) : undefined;
  return { latestGolden, golden, outputId, output, brief, sid: brief?.status === "done" ? brief.id : null };
}

/** A score running: reload the list until it's done. */
function usePollWhileRunning(idx: ExtractOutputs | null, loadIndex: () => Promise<void>) {
  const running = !!idx && (!!idx.running || idx.outputs.some((o) => o.scores.some((s) => s.status === "running")));
  useEffect(() => {
    if (!running) return;
    const t = setInterval(() => { void loadIndex(); }, 1500);
    return () => clearInterval(t);
  }, [running, loadIndex]);
}

function useScoreDoc(cat: string, sid: string | null, setError: (e: string) => void): ScoreDoc | null {
  const [doc, setDoc] = useState<ScoreDoc | null>(null);
  useEffect(() => {
    if (!sid) { setDoc(null); return; }
    let live = true;
    api.scoreDoc(cat, sid).then((d) => live && setDoc(d), (e) => live && setError(String(e)));
    return () => { live = false; };
  }, [cat, sid, setError]);
  return doc;
}

function useScoreValues(cat: string, doc: ScoreDoc | null, sid: string | null, query: EvalsQuery, setError: (e: string) => void) {
  const [view, setView] = useState<ScoreValues | null>(null);
  const { basis, col, subj, outcome, grp, offset } = query;
  useEffect(() => {
    if (!doc || doc.id !== sid || !doc.results[basis]) { setView(null); return; }
    let live = true;
    api.scoreValues(cat, doc.id, { basis, column: col, subject: subj, outcome, group: grp, offset })
      .then((r) => live && setView(r), (e) => live && setError(String(e)));
    return () => { live = false; };
  }, [cat, doc, sid, basis, col, subj, outcome, grp, offset, setError]);
  return view;
}

function OneClassTitle({ evals: { query, idx, golden, brief, doc, nav }, diffMode, onInfo }: { evals: LoadedState; diffMode: boolean; onInfo: () => void }) {
  const reset = { col: null, subj: null, o: null, off: null };
  return (
    <header className="evx-title">
      {query.basis === "human"
        ? <span className="evx-gchip big">{goldenName(HUMAN)}<span className="evx-gchip-d"> · as of {fmtDayTime(brief?.golden_as_of) || "now"}</span></span>
        : <GoldenPicker goldens={idx.goldens} value={golden} onPick={(id) => nav({ g: id, ...reset })} />}
      <OutputsOverTime />
      {doc && <button className="evx-info" title="Where these come from" aria-label="Where these come from" onClick={onInfo}>i</button>}
      <span className="grow" />
      <BasisSwitch basis={query.basis} onHuman={() => nav({ b: null, ...reset })} onRule={() => nav({ b: "rule", ...reset })} />
      {diffMode && <DiffModeSwitch />}
    </header>
  );
}

function OutputsChart({ evals: { idx, query, golden, latestGolden, outputId, doc, nav }, onScore }: { evals: LoadedState; onScore: (o: Output) => void }) {
  const latest = idx.outputs[0]?.id;
  if (!idx.outputs.length) return <p className="muted evx-empty">{idx.error ?? "xtra hasn't written an extract output for this catalog yet."}</p>;
  return (
    <div className="evx-chartrow">
      <History outputs={[...idx.outputs].reverse()} latest={latest} basis={query.basis} golden={golden} latestGolden={latestGolden} picked={outputId}
        busy={!!idx.running} onPick={(id) => nav({ x: id === latest ? null : id, off: null })} onScore={onScore} />
      <OutcomeLegend counts={doc?.results[query.basis]?.outcomes ?? null} />
    </div>
  );
}

function PickedOutput({ catalog, evals, output }: Omit<PageProps, "me"> & { output: Output }) {
  const { query, brief, doc, view, sum, nav } = evals;
  const score: ScoreContext | null = doc && view && doc.results[query.basis]
    ? { cat: catalog.short, query, view, nav, doc, sum, here: sum?.catalogs[catalog.catalog]?.columns ?? {} } : null;
  return (
    <>
      <PairChips evals={evals} output={output} />
      {brief?.slot_names && <p className="evx-flag">This output uses slot names; re-extract with the current xtra-cli.</p>}
      {output.records_mismatch && <p className="evx-flag">The folder has {fmt(output.records)} records; its report says {fmt(output.records_written)} were written (an earlier run's records may be left over).</p>}
      <ScoreStatus evals={evals} />
      {score && <ScoreBody score={score} />}
    </>
  );
}

function OpenRow({ catalog, me, evals: { doc, output, idx, query, nav }, row }: PageProps & { row: ScoreRow }) {
  if (!doc || !output) return null;
  return <RowPanel key={`${doc.id}|${row.key}`} row={row} doc={doc} catalog={catalog.short} ruleset={catalog.ruleset_version}
    goldenLabel={goldenName(query.basis === "human" ? HUMAN : doc.golden.id)}
    outputDay={fmtDay(output.last_modified)} idx={idx} me={me} onClose={() => nav({ row: null })} />;
}

function OutputsOverTime() {
  return <><span className="evx-vs">vs</span><code className="evx-cmd">xtra catalog extract</code><span>outputs over time</span></>;
}

function BasisSwitch({ basis, onHuman, onRule }: { basis: ScoreBasis; onHuman: () => void; onRule: () => void }) {
  return (
    <span className="evx-basis">scored against
      <span className="seg xs" role="group" aria-label="Scored against">
        <button className={basis === "human" ? "on" : ""} onClick={onHuman}>Human-reviewed</button>
        <button className={basis === "rule" ? "on" : ""} onClick={onRule}>Rule-matched</button>
      </span>
      <Tip width={300} tip={BASIS_TIP}><span className="evx-i" tabIndex={0} aria-label="What each scores">ⓘ</span></Tip>
    </span>
  );
}

function PairChips({ evals: { query: { basis }, idx, golden, brief }, output }: { evals: LoadedState; output: Output }) {
  return (
    <div className="evx-pair">
      <span className="evx-gchip">{basis === "human" ? `${goldenName(HUMAN)} · ${fmtDayTime(brief?.golden_as_of) || "now"}` : goldenName(golden)}</span>
      {basis === "rule" && idx.goldens.find((z) => z.id === golden)?.kind === "draft" && <span className="evx-draft">draft · unpublished</span>}
      <span className="evx-vs">vs</span>
      <span className="evx-xchip"><MiniBar c={(brief && outcomesOf(brief, basis)) ?? null} />
        {fmtDayTime(output.last_modified)}{output.id === idx.outputs[0]?.id && <span className="muted"> (latest)</span>}</span>
    </div>
  );
}

function ScoreStatus({ evals: { query: { basis }, golden, brief, doc } }: { evals: LoadedState }) {
  const name = goldenName(basis === "human" ? HUMAN : golden);
  return <>
    {!brief && <p className="muted">Not scored against {name} yet: press <b>Score</b> on its bar.</p>}
    {brief && brief.status !== "done" && <p className="muted">{brief.status === "running" ? `Scoring (${brief.id})…`
      : `${brief.id} ${brief.status}${brief.error ? `: ${brief.error}` : ""}. Press Score on its bar to score it again.`}</p>}
    {doc && !doc.results[basis] && <p className="muted">No {basis === "human" ? "human-reviewed" : "rule-matched"} values to score in {name}.</p>}
  </>;
}
