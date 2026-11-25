// The chosen score: the headline, one bar per column, Where it's wrong, the outcome filter, Group by and the values.
import type { ReactNode } from "react";
import type { CatalogsSummary, ColumnSummary, OutcomeCounts, ScoreDoc, ScoreOutcome, ScoreRow, ScoreValues } from "../api/types";
import { apiClass } from "../shell/klass";
import { fmt } from "../shell/ui";
import type { EvalsQuery, Nav } from "./query";
import { goldenTerm, hasCtdlTerm, num, OUTCOME_RULE, OUTCOMES, pct, rateOf, rightOf, candidateCount, shown, total, unscoredFacts,
  type Fact } from "./score";
import { Bar, COURSES_TIP, FOUND_TIP, OutcomeTip, RIGHT_TIP, Tip } from "./Tip";
import { WhereWrong } from "./WhereWrong";

export interface ScoreContext {
  cat: string; query: EvalsQuery; view: ScoreValues; nav: Nav; doc: ScoreDoc; sum: CatalogsSummary | null;
  here: Record<string, ColumnSummary>;
}
type Totals = ScoreValues["total"];
type ValueGroupCounts = NonNullable<ScoreValues["groups"]>[number];
interface ColumnGroupSpec { title: string; keys: string[] }

export function ScoreBody({ score }: { score: ScoreContext }) {
  const { cat, query, view, nav, doc } = score;
  return (
    <>
      <ScoreSummary query={query} view={view} />
      <ColumnsTable score={score} />
      <WhereWrong cat={cat} cls={apiClass()} doc={doc} basis={query.basis} col={query.col} wk={query.wk} nav={nav} />
      <ValueControls score={score} />
      {query.grp && view.groups && <ValueGroups groups={view.groups} query={query} nav={nav} />}
      <ValueRows rows={view.rows.items} query={query} nav={nav} />
      {view.rows.total > view.rows.page && <Pager offset={query.offset} rows={view.rows} nav={nav} />}
    </>
  );
}

/** What a row of values says: the candidate, or why there is none. */
export function rowText(r: ScoreRow): ReactNode {
  if (r.outcome === "unsure") return <span className="muted">golden: not on the page · xtra made no claim</span>;
  if (r.outcome === "missing") return missingText(r);
  if (r.outcome === "extra") return extraText(r);
  if (r.unit === "absent") return <span className="muted">not on the page</span>;
  return shown(r.outcome === "match" ? r.golden_value : r.extracted_value);
}

function ScoreSummary({ query, view }: { query: EvalsQuery; view: ScoreValues }) {
  return <>
    <Headline query={query} totals={view.total} />
    <FoundRight query={query} totals={view.total} />
    <ScoreNotes result={view.result} />
  </>;
}

function Headline({ query: { basis }, totals: t }: { query: EvalsQuery; totals: Totals }) {
  return (
    <div className="evx-rate" data-testid="headline">
      <b>{pct(t.values ? t.match / t.values : null)}</b>
      <span className="evx-rate-l">exact matches</span>
      <span className={`evx-basis-pill ${basis}`}>{basis === "human" ? "human-reviewed" : "rule-matched"}</span>
      <span className="muted">{fmt(t.match)} of {fmt(t.values)} values {basis === "human" ? "an expert reviewed" : "the rules matched"}</span>
    </div>
  );
}

function FoundRight({ query: { basis }, totals: t }: { query: EvalsQuery; totals: Totals }) {
  const noun = goldenTerm(basis).toLowerCase();
  return (
    <p className="muted small evx-fr" data-testid="found-right">
      <Tip tip={FOUND_TIP} width={360}><span tabIndex={0}>found <b>{pct(t.found ?? rateOf(t))}</b> of {fmt(t.values)} {noun}</span></Tip>
      {" · "}
      <Tip tip={RIGHT_TIP} width={360}><span tabIndex={0}>right <b>{pct(t.right ?? rightOf(t))}</b> of {fmt(t.extracted ?? candidateCount(t))} candidates</span></Tip>
      {num(t, "extra") > 0 && <> · <i className="sw o-extra" />{fmt(num(t, "extra"))} extra</>}
      {num(t, "unsure") > 0 && <> · <i className="sw o-unsure" />{fmt(num(t, "unsure"))} unsure</>}
    </p>
  );
}

function ScoreNotes({ result }: { result: ScoreValues["result"] }) {
  const xtra = result?.xtra;
  const leftOut = result?.left_out ?? [];
  return <>
    {xtra && <p className="muted small evx-xtra" data-testid="xtra-line">xtra's own, over every column: {pct(xtra.exact_match_rate)} exact matches
      of {fmt(xtra.values)} values</p>}
    {leftOut.length > 0 && <p className="muted small">{fmt(leftOut.length)} pages left out: {leftOut[0].why}.</p>}
  </>;
}

function ColumnsTable({ score }: { score: ScoreContext }) {
  const { query, view, nav } = score;
  return (
    <table className="evx-cols">
      <ColumnsHead query={query} />
      <tbody>
        <ColRow name="All columns" c={view.total} on={!query.col} total onClick={() => nav({ col: null, off: null })} />
        <ColumnRows score={score} />
      </tbody>
    </table>
  );
}

/** Every property's column, required ones first; without the summary, the scored columns alone. */
function ColumnRows({ score }: { score: ScoreContext }) {
  const { query, view, nav, sum } = score;
  const toggle = (k: string) => nav({ col: query.col === k ? null : k, off: null });
  const groups = columnGroups(sum, view);
  return <>
    {groups.length
      ? groups.map((g) => <ColumnGroup key={g.title} group={g} score={score} onToggle={toggle} />)
      : view.columns.map((p) => <ColRow key={p.column} name={p.column} c={p} on={query.col === p.column} column={p.column} onClick={() => toggle(p.column)} />)}
  </>;
}

function ValueControls({ score: { query, view, nav } }: { score: ScoreContext }) {
  return (
    <div className="evx-controls">
      <OutcomeFilter outcome={query.outcome} counts={view.outcomes} nav={nav} />
      {query.col && <button className="evx-chip" onClick={() => nav({ col: null, off: null })}>{query.col} ✕</button>}
      {query.subj && <button className="evx-chip" onClick={() => nav({ subj: null, off: null })}>Subject: {query.subj} ✕</button>}
      <span className="grow" />
      <label className="evx-group">Group by
        <select value={query.grp ?? ""} onChange={(e) => nav({ grp: e.target.value || null, off: null })}>
          <option value="">nothing</option><option value="column">column</option><option value="subject">subject</option>
        </select>
      </label>
    </div>
  );
}

function ValueGroups({ groups, query, nav }: { groups: ValueGroupCounts[]; query: EvalsQuery; nav: Nav }) {
  return (
    <div className="evx-groups" data-testid="groups">
      {groups.map((g) => <ValueGroup key={g.name} group={g} query={query} nav={nav} />)}
    </div>
  );
}

function ValueRows({ rows, query, nav }: { rows: ScoreRow[]; query: EvalsQuery; nav: Nav }) {
  return (
    <div className="evx-rows">
      {rows.map((r) => <ValueRow key={r.key} row={r} query={query} nav={nav} />)}
      {!rows.length && <p className="muted">No values here.</p>}
    </div>
  );
}

function Pager({ offset, rows, nav }: { offset: number; rows: ScoreValues["rows"]; nav: Nav }) {
  return (
    <div className="evx-pager">
      <button className="btn sm" disabled={offset === 0} onClick={() => nav({ off: Math.max(0, offset - rows.page) || null })}>Previous</button>
      <span className="muted">{fmt(offset + 1)}–{fmt(Math.min(rows.total, offset + rows.page))} of {fmt(rows.total)}, worst first</span>
      <button className="btn sm" disabled={offset + rows.page >= rows.total} onClick={() => nav({ off: offset + rows.page })}>Next</button>
    </div>
  );
}

function missingText(r: ScoreRow): ReactNode {
  if (r.unit === "absent") return <span className="muted">golden: not on the page · candidate {shown(r.extracted_value) || "given"}</span>;
  return <span className="muted">{r.reason === "claimed not on the page" ? "xtra claims it isn't on the page" : "no candidate"}</span>;
}

function extraText(r: ScoreRow): ReactNode {
  return r.unit === "absent" ? <span className="muted">xtra claims it isn't on the page (golden has a value)</span>
    : <>{shown(r.extracted_value)} <span className="muted">· {r.reason ?? "no golden value"}</span></>;
}

function columnGroups(sum: CatalogsSummary | null, view: ScoreValues): ColumnGroupSpec[] {
  const keys = sum?.columns ?? view.columns.map((c) => c.column);
  const required = sum?.required ?? [];
  return [
    { title: "Required", keys: keys.filter((k) => required.includes(k)) },
    { title: "Other properties", keys: keys.filter((k) => !required.includes(k)) }].filter((g) => g.keys.length);
}

function ColumnsHead({ query }: { query: EvalsQuery }) {
  return (
    <thead>
      <tr className="evx-colh">
        <th scope="col">Column</th><th scope="col">Units</th>
        <th scope="col" className="r"><Tip tip={FOUND_TIP} width={360}><span tabIndex={0}>Found</span></Tip></th>
        <th scope="col" className="r"><Tip tip={RIGHT_TIP} width={360}><span tabIndex={0}>Right</span></Tip></th>
        <th scope="col" className="r"><Tip tip={COURSES_TIP} width={320}><span tabIndex={0}>Courses</span></Tip></th>
        <th scope="col" className="r">{goldenTerm(query.basis)}</th>
      </tr>
    </thead>
  );
}

function ColumnGroup({ group, score: { query, view, doc, sum, here }, onToggle }: { group: ColumnGroupSpec; score: ScoreContext; onToggle: (k: string) => void }) {
  const scored = new Map(view.columns.map((c) => [c.column, c]));
  const implied = Object.keys(view.result?.implied ?? {});
  return (
    <>
      <tr className="evx-hrow"><th colSpan={6} scope="colgroup" className="evx-h">{group.title}</th></tr>
      {group.keys.map((k) => {
        const sc = scored.get(k), name = sum?.labels[k] ?? k;
        return sc ? <ColRow key={k} name={name} mono={hasCtdlTerm(k)} c={sc} on={query.col === k} column={k} onClick={() => onToggle(k)} />
          : <Unscored key={k} k={k} name={name} facts={unscoredFacts(k, here[k], doc, query.basis, implied)} />;
      })}
    </>
  );
}

function ColRow({ name, c, on, total: all = false, mono = true, column, onClick }: { name: string; c: OutcomeCounts; on: boolean; total?: boolean;
  mono?: boolean; column?: string; onClick: () => void }) {
  return (
    <tr className={`${on && !all ? "on" : ""}${all ? " all" : ""}`} onClick={onClick} data-column={column}>
      <td className={all || !mono ? "" : "mono"}>{name}</td>
      <td className="evx-barcell"><OutcomeTip counts={c}><Bar c={c} /></OutcomeTip></td>
      <td className="r" data-num="found"><b>{pct(c.found !== undefined ? c.found : c.values ? c.match / c.values : null)}</b></td>
      <td className="r" data-num="right">{pct(c.right !== undefined ? c.right : rightOf(c))}</td>
      <td className="r muted" data-num="courses">{c.list && c.courses ? pct((c.courses_exact ?? 0) / c.courses) : ""}</td>
      <td className="r muted">{fmt(c.values)}{all ? " values" : ""}</td>
    </tr>
  );
}

/** A column with no score: "Not scored" and its two facts, each with a tooltip saying what the term means. */
function Unscored({ k, name, facts }: { k: string; name: string; facts: { candidates: Fact; golden: Fact } }) {
  return (
    <tr className="evx-unscored" data-column={k}>
      <td className={hasCtdlTerm(k) ? "mono" : undefined}>{name}</td>
      <td colSpan={5} className="evx-why">
        <span className="evx-ns">Not scored</span>
        {[facts.candidates, facts.golden].map((f) => (
          <Tip key={f.term} width={320} tip={<>{f.tip}<br /><b>{f.full}</b></>}>
            <span className="evx-fact" tabIndex={0} title={f.full} data-fact={f.term}><span className="muted">{f.term}:</span> {f.short}</span>
          </Tip>
        ))}
      </td>
    </tr>
  );
}

function OutcomeFilter({ outcome, counts, nav }: { outcome: ScoreOutcome | null; counts: OutcomeCounts; nav: Nav }) {
  return (
    <div className="seg">
      <button className={!outcome ? "on" : ""} onClick={() => nav({ o: null, off: null })}>All <span>{fmt(total(counts))}</span></button>
      {OUTCOMES.map((o) => (
        <button key={o} className={outcome === o ? "on" : ""} disabled={!num(counts, o)} onClick={() => nav({ o: outcome === o ? null : o, off: null })}>
          <i className={`sw o-${o}`} />{o} <span>{fmt(num(counts, o))}</span>
        </button>
      ))}
    </div>
  );
}

function ValueGroup({ group, query: { grp, col, subj }, nav }: { group: ValueGroupCounts; query: EvalsQuery; nav: Nav }) {
  const on = grp === "column" ? col === group.name : subj === group.name;
  const pick = () => nav(grp === "column" ? { col: on ? null : group.name, off: null } : { subj: on ? null : group.name, off: null });
  return (
    <button className={`evx-grow${on ? " on" : ""}`} onClick={pick}>
      <span className={`evx-grow-n${grp === "column" ? " mono" : ""}`}>{group.name}</span>
      <OutcomeTip counts={group}><Bar c={group} /></OutcomeTip>
      <span className="evx-grow-r"><b>{pct(group.values ? group.match / group.values : null)}</b> <span className="muted">{fmt(group.values)}</span></span>
    </button>
  );
}

function ValueRow({ row, query: { rowKey, col }, nav }: { row: ScoreRow; query: EvalsQuery; nav: Nav }) {
  return (
    <button className={`evx-row${row.key === rowKey ? " on" : ""}${col ? " one-col" : ""}`} onClick={() => nav({ row: row.key }, true)}>
      <i className={`sw o-${row.outcome}`} title={`${row.outcome}: ${OUTCOME_RULE[row.outcome]}`} />
      <span className="evx-row-c">{row.golden_record_id ?? row.page_stem}</span>
      {!col && <span className="evx-row-p mono">{row.column}{row.field ? ` · ${row.field}` : ""}</span>}
      <span className="evx-row-v">{rowText(row)}</span>
      <span className="evx-row-s">{row.outcome === "partial" || row.outcome === "wrong" ? row.similarity?.toFixed(2) : ""}</span>
    </button>
  );
}
