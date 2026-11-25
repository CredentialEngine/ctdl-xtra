// Compare (spec §7.4, screens 08-compare*): is ruleset version B better than A?
// Top: From / To only. Left: the rules that changed. Right: summary line, why, Jared's earlier verdicts, signals
// before → after (expandable into the records that lost / gained them), then every other changed record, paged and
// filterable by strata.
// Every record links to the Rules tab ("See on page →") in the ruleset that has it: To's, or From's for a record or rule
// To dropped (?ext=, none for the latest); Compare has no page pane.
import { SkelTable } from "../shell/Skeleton";
import { createContext, useContext, useEffect, useState, type KeyboardEvent, type ReactNode } from "react";
import { api } from "../api/client";
import type { BriefRow, CompareRecords } from "../api/types";
import { go, href } from "../shell/router";
import type { TabProps } from "../shell/tabProps";
import { SampleDrawer, samplePrefs, sampleQuery, StrataTags, type SamplePrefs } from "../shell/Sample";
import { fmt, Ico, useKeyHints } from "../shell/ui";
import { useReviewer } from "../shell/reviewer";
import { DiffModeSwitch } from "../valuediff/ValueDiff";
import { CompareCtx, CompareValue } from "./CompareValue";
import { delta, outcomeLabel } from "./diff";
import type { AnnotatedRowX, CompareResponseX, RuleCardX, SignalDeltaX } from "./types";
import "./compare.css";

const VERDICT_LABEL = { correct: "Correct", wrong: "Wrong" } as const;
/** The extraction each side's "See on page →" opens on the Rules tab: null for the latest (no ?ext). */
const SeeCtx = createContext<{ a: string | null; b: string | null }>({ a: null, b: null });
export const PAGE_SIZES = [25, 50, 100, 200, 500];
const PAGE_SIZE_KEY = "studio.compare.pageSize";

interface Pick { a?: number; b?: number; rule?: string }
type Nav = (p: { a?: number; b?: number; rule?: string | null }) => void;
interface CardsProps { cards: RuleCardX[]; short: string; many: boolean }
interface RowProps { card: RuleCardX; short: string; many: boolean }
type ChangedRule = CompareResponseX["changed_rules"][number];
type Paging = ReturnType<typeof useOtherChangedPaging>;

export default function CompareTab({ catalog, route }: TabProps) {
  const short = catalog.short;
  const me = useReviewer();
  const pick = readPick(route.params);
  const { data, error, loading } = useComparison(short, pick);
  useKeyHints(<span>The same numbers <span className="mono">golden-datasets rule try</span> prints</span>, []);
  const nav: Nav = (p) => go(href(short, "compare", null, nextPick(p, pick, data)));
  if (error && !data) return <div className="cmp-layout"><div /><section className="doc"><div className="doc-in">
    <h1>Compare ruleset versions</h1><p className="muted cmp-empty">{error}</p></div></section></div>;
  if (!data) return <div className="cmp-layout"><aside className="col" /><section className="doc"><div className="doc-in">
    <h1>Compare ruleset versions</h1><SkelTable label="Loading the comparison" rows={6} cols={5} /></div></section></div>;
  return <ComparePage data={data} short={short} me={me} rule={pick.rule} error={error} loading={loading} nav={nav} />;
}

function readPick(params: URLSearchParams): Pick {
  return { a: versionOf(params.get("a")), b: versionOf(params.get("b")), rule: params.get("rule") || undefined };
}

function useComparison(short: string, { a, b, rule }: Pick) {
  const [data, setData] = useState<CompareResponseX | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    let live = true;
    setLoading(true);
    api.compare(short, { a, b, rule }).then(
      (d) => { if (live) { setData(d as unknown as CompareResponseX); setError(null); setLoading(false); } },
      (e) => { if (live) { setError(String(e.message ?? e)); setLoading(false); } });
    return () => { live = false; };
  }, [short, a, b, rule]);
  return { data, error, loading };
}

function nextPick(p: Parameters<Nav>[0], pick: Pick, data: CompareResponseX | null) {
  return { a: p.a ?? data?.a ?? pick.a, b: p.b ?? data?.b ?? pick.b, rule: p.rule === undefined ? pick.rule : p.rule };
}

function ComparePage({ data, short, me, rule, error, loading, nav }: {
  data: CompareResponseX; short: string; me: string; rule?: string; error: string | null; loading: boolean; nav: Nav }) {
  return (
    <div className={"cmp-layout" + (loading ? " loading" : "")}>
      <RuleColumn data={data} rule={rule} onPick={(r) => nav({ rule: r })} />
      <section className="doc">
        <div className="doc-in">
          <CompareHead data={data} nav={nav} />
          {error && <p className="cmp-error">{error}</p>}
          <CompareBody data={data} short={short} me={me} rule={rule} />
        </div>
      </section>
    </div>
  );
}

/** The comparison's rows, which share its versions and where each side's "See on page →" opens. */
function CompareBody({ data, short, me, rule }: { data: CompareResponseX; short: string; me: string; rule?: string }) {
  return (
    <CompareCtx.Provider value={{ short, a: data.a, b: data.b, bExtraction: data.b_extraction, me }}>
      <SeeCtx.Provider value={seeExt(data)}><Body data={data} short={short} rule={rule} /></SeeCtx.Provider>
    </CompareCtx.Provider>
  );
}

function versionOf(v: string | null): number | undefined {
  return v && /^\d+$/.test(v) ? Number(v) : undefined;
}

function RuleColumn({ data, rule, onPick }: { data: CompareResponseX; rule?: string; onPick: (r: string | null) => void }) {
  const items = changedRules(data, rule);
  const total = data.changed_rules.reduce((t, r) => t + r.records_changed, 0);
  return (
    <aside className="col">
      <div className="rule-list">
        <div className="group-h"><span className="panel-title">Rules that changed</span></div>
        <AllRulesItem total={total} on={!rule} onPick={() => onPick(null)} />
        {items.map((r) => <ChangedRuleItem key={r.rule_id} rule={r} on={rule === r.rule_id} onPick={() => onPick(r.rule_id)} />)}
        {items.length > 0 && <div className="faint cmp-foot">Counts are records whose value changed.</div>}
      </div>
    </aside>
  );
}

function CompareHead({ data, nav }: { data: CompareResponseX; nav: Nav }) {
  return (
    <div className="cmp-head">
      <h1>Compare ruleset versions</h1>
      <div className="ctl">
        <label>From <VersionSelect data={data} value={data.a} onChange={(v) => nav({ a: v })} name="from" /></label>
        <span className="faint">→</span>
        <label>To <VersionSelect data={data} value={data.b} onChange={(v) => nav({ b: v })} name="to" /></label>
      </div>
      <DiffModeSwitch />
    </div>
  );
}

function Body({ data, short, rule }: { data: CompareResponseX; short: string; rule?: string }) {
  if (!isComparable(data)) return <NothingToCompare data={data} />;
  const many = data.rules.length > 1 && !rule;
  return (
    <>
      <SumLine data={data} />
      <WhyCards cards={data.rules} many={many} />
      <EarlierVerdicts cards={data.rules} short={short} many={many} />
      <Signals cards={data.rules} short={short} many={many} />
      <NewAndGone data={data} short={short} many={many} />
      <OtherChanged data={data} short={short} rule={rule} many={many} />
    </>
  );
}

function seeExt(data: CompareResponseX): { a: string | null; b: string | null } {
  const latest = Math.max(...data.versions.map((v) => v.version));
  return { a: data.a === latest ? null : data.a_extraction, b: data.b === latest ? null : data.b_extraction };
}

function changedRules(data: CompareResponseX, rule: string | undefined): ChangedRule[] {
  const items = [...data.changed_rules];
  // A link to a rule that didn't change still shows it, with 0.
  const extra = rule && !items.some((r) => r.rule_id === rule) ? data.rules.find((c) => c.rule_id === rule) : undefined;
  if (extra) items.push({ ...extra, records_changed: 0 });
  return items;
}

function RuleItem({ on, onPick, ruleId, children }: { on: boolean; onPick: () => void; ruleId?: string; children: ReactNode }) {
  return <div className={"rule-item" + (on ? " on" : "")} role="button" tabIndex={0}
    onClick={onPick} onKeyDown={onEnterOrSpace(onPick)} data-rule={ruleId}>{children}</div>;
}

function AllRulesItem({ total, on, onPick }: { total: number; on: boolean; onPick: () => void }) {
  return (
    <RuleItem on={on} onPick={onPick}>
      <div /><div><div className="nm">All changed rules</div></div><div className="meta"><span>{fmt(total)}</span></div>
    </RuleItem>
  );
}

function ChangedRuleItem({ rule: r, on, onPick }: { rule: ChangedRule; on: boolean; onPick: () => void }) {
  return (
    <RuleItem on={on} onPick={onPick} ruleId={r.rule_id}>
      <div />
      <div style={{ minWidth: 0 }}>
        <div className={"nm" + (r.ctdl_property ? " mono-t" : "")}>{r.ctdl_property ?? r.title}</div>
        <div className="id plain">{r.title} · {ver(r.a_version)} → {ver(r.b_version)}</div>
      </div>
      <div className="meta"><span>{fmt(r.records_changed)}</span></div>
    </RuleItem>
  );
}

function VersionSelect({ data, value, onChange, name }:
  { data: CompareResponseX; value: number; onChange: (v: number) => void; name: string }) {
  const latest = Math.max(...data.versions.map((v) => v.version));
  return (
    <select className="vsel" aria-label={name} value={value} onChange={(e) => onChange(Number(e.target.value))}>
      {data.versions.map((v) => <option key={v.version} value={v.version} title={v.note ?? ""}>
        ruleset v{v.version}{v.version === latest ? " (latest)" : ""}</option>)}
    </select>
  );
}

function isComparable(data: CompareResponseX): boolean {
  return data.versions.length >= 2 && data.a !== data.b && data.rules.length > 0;
}

function NothingToCompare({ data }: { data: CompareResponseX }) {
  if (data.versions.length < 2) return <p className="muted cmp-empty">
    Only one ruleset version so far (v{data.b}), so there is nothing to compare. Publishing a rule makes the next one.</p>;
  if (data.a === data.b) return <p className="muted cmp-empty">From and To are the same version. Pick two different ones.</p>;
  return <p className="muted cmp-empty">No rule changed between v{data.a} and v{data.b}.</p>;
}

function SumLine({ data }: { data: CompareResponseX }) {
  const t = data.totals;
  return (
    <div className="sumline" data-testid="sumline">
      <Num n={data.records_changed} label="records changed" />
      <Dot /><Num n={t.fixed} label="fixed" cls="good" />
      <Dot /><Num n={t.still_wrong} label="still wrong" cls="bad" />
      <Dot /><Num n={t.newly_wrong} label="newly wrong" cls="bad" />
    </div>
  );
}

function WhyCards({ cards, many }: { cards: RuleCardX[]; many: boolean }) {
  return <>{cards.map((c) => (
    <details key={c.rule_id} className="why1">
      <summary>Why this version{many && <> of <span className="mono">{c.ctdl_property ?? c.title}</span></>}</summary>
      <p>{c.why || "No reason given."}</p>
    </details>
  ))}</>;
}

function EarlierVerdicts({ cards, short, many }: CardsProps) {
  const verdicts = cards.flatMap((c) => c.annotated_rows.map((r) => ({ r, c })));
  const authors = [...new Set(verdicts.map((v) => v.r.author))];
  return <>
    <h2>{authors.length === 1 ? `${authors[0]}'s earlier verdicts` : "Earlier verdicts"}
      <span className="c">{fmt(verdicts.length)} records</span></h2>
    {verdicts.length ? (
      <div className="clist">
        {verdicts.map(({ r, c }) => <VerdictRow key={c.rule_id + r.key} r={r} card={c} short={short} many={many} />)}
      </div>
    ) : <p className="muted cmp-none">No verdicts on these rules yet.</p>}
  </>;
}

function Signals({ cards, short, many }: CardsProps) {
  return <>
    <h2>Signals <span className="c">click a signal to see the records that lost or gained it</span></h2>
    {cards.some((c) => c.signals.length)
      ? <div className="sigt">{cards.flatMap((c) => c.signals.map((s) =>
          <SignalRow key={c.rule_id + s.signal} s={s} card={c} short={short} many={many} />))}</div>
      : <p className="muted cmp-none">No signals on these rules.</p>}
  </>;
}

function NewAndGone({ data, short, many }: { data: CompareResponseX; short: string; many: boolean }) {
  const added = data.rules.flatMap((c) => c.new_rows.map((r) => ({ r, c })));
  const gone = data.rules.flatMap((c) => c.vanished_rows.map((r) => ({ r, c })));
  const addedN = data.rules.reduce((s, c) => s + c.values.new, 0), goneN = data.rules.reduce((s, c) => s + c.values.vanished, 0);
  return <>
    {addedN > 0 && <ChangedRecords heading={<>New in v{data.b}</>} count={addedN} rows={added} short={short} many={many} />}
    {goneN > 0 && <ChangedRecords heading={<>Gone in v{data.b}</>} count={goneN} rows={gone} short={short} many={many} />}
  </>;
}

/** Every other changed record, a page at a time, filtered by strata (routes_compare.py `/compare/records`). */
function OtherChanged({ data, short, rule, many }: { data: CompareResponseX; short: string; rule?: string; many: boolean }) {
  const paging = useOtherChangedPaging(short, data, rule);
  const { res, err } = useCompareRecords(short, data, rule, paging);
  const pager = res && res.total > 0 && <Pager paging={paging} total={res.total} />;
  return (
    <>
      <OtherHeading res={res} prefs={paging.prefs} />
      {err && <p className="cmp-error">{err}</p>}
      {res && res.all > 0 && <OtherSample res={res} paging={paging} />}
      {pager}
      {res && <OtherRecords res={res} data={data} short={short} many={many} />}
      {res && res.records.length > 10 && pager}
    </>
  );
}

function Num({ n, label, cls = "" }: { n: number; label: string; cls?: string }) {
  return <span className={n ? cls : "zero"}><b>{fmt(n)}</b> {label}</span>;
}

function Dot() {
  return <span className="dot">·</span>;
}

function VerdictRow({ r, card, short, many }: RowProps & { r: AnnotatedRowX }) {
  return (
    <div className="crec vrec cv" data-outcome={r.outcome}>
      <CompareValue r={r} ruleId={card.rule_id} kind={card.kind} column={card.ctdl_property ?? card.title}
        head={<VerdictHead r={r} card={card} many={many} />} foot={<VerdictNotes r={r} />}>
        <See r={r} card={card} short={short} />
      </CompareValue>
    </div>
  );
}

function SignalRow({ s, card, short, many }: RowProps & { s: SignalDeltaX }) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <SignalLine s={s} card={card} many={many} open={open} onToggle={() => setOpen((o) => !o)} />
      {open && <SignalDrill s={s} card={card} short={short} />}
    </>
  );
}

function ChangedRecords({ heading, count, rows, short, many }: {
  heading: ReactNode; count: number; rows: { r: BriefRow; c: RuleCardX }[]; short: string; many: boolean }) {
  return <>
    <h2>{heading} <span className="c">{fmt(count)} records{count > rows.length ? `, first ${rows.length}` : ""}</span></h2>
    <div className="clist">{rows.map(({ r, c }) => <RecLine key={c.rule_id + r.key} r={r} card={c} short={short} many={many} />)}</div>
  </>;
}

function useOtherChangedPaging(short: string, data: CompareResponseX, rule: string | undefined) {
  const [size, setSize] = useState<number>(storedPageSize);
  const [offset, setOffset] = useState(0);
  const [prefs, setPrefs] = useState<SamplePrefs>(() => samplePrefs("shuffle"));
  // another pair of versions or rule: back to the first page, shuffled, unfiltered
  useEffect(() => { setOffset(0); setPrefs(samplePrefs("shuffle")); }, [short, data.a, data.b, rule]);
  const pickSize = (n: number) => { setSize(n); setOffset(0); storePageSize(n); };
  const onPrefs = (p: SamplePrefs) => { setPrefs(p); setOffset(0); };
  return { size, offset, setOffset, prefs, pickSize, onPrefs };
}

function useCompareRecords(short: string, data: CompareResponseX, rule: string | undefined, { offset, size, prefs }: Paging) {
  const [res, setRes] = useState<CompareRecords | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const qKey = JSON.stringify(sampleQuery(prefs, "shuffle"));
  useEffect(() => {
    let live = true;
    api.compareRecords(short, { a: data.a, b: data.b, rule, offset, limit: size, ...JSON.parse(qKey) })
      .then((r) => { if (live) { setRes(r); setErr(null); } }, (e) => { if (live) setErr(String(e.message ?? e)); });
    return () => { live = false; };
  }, [short, data.a, data.b, rule, offset, size, qKey]);
  return { res, err };
}

function Pager({ paging: { offset, size, setOffset, pickSize }, total }: { paging: Paging; total: number }) {
  return (
    <div className="cmp-pager" data-testid="pager">
      <button className="btn" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - size))}>← Previous</button>
      <span>{fmt(offset + 1)}–{fmt(Math.min(total, offset + size))} of {fmt(total)}</span>
      <button className="btn" disabled={offset + size >= total} onClick={() => setOffset(offset + size)}>Next →</button>
      <label className="faint">Per page <select aria-label="Per page" value={size} onChange={(e) => pickSize(Number(e.target.value))}>
        {PAGE_SIZES.map((n) => <option key={n} value={n}>{n}</option>)}</select></label>
    </div>
  );
}

function OtherHeading({ res, prefs }: { res: CompareRecords | null; prefs: SamplePrefs }) {
  const total = res?.total ?? 0;
  const how = prefs.mode === "auto" ? "autostratified: 3 of each combination, rarest first" : "in random order";
  return <h2>Other changed records <span className="c">{res ? <>{fmt(total)}{total !== res.all && <> of {fmt(res.all)}</>}, {how}</> : "…"}</span></h2>;
}

function OtherSample({ res, paging }: { res: CompareRecords; paging: Paging }) {
  return <SampleDrawer sample={res.sample} prefs={paging.prefs} onPrefs={paging.onPrefs} modes={["auto", "shuffle", "manual"]}
    storageKey="studio.compare.sample" />;
}

function OtherRecords({ res, data, short, many }: { res: CompareRecords; data: CompareResponseX; short: string; many: boolean }) {
  if (!res.records.length) return <p className="muted cmp-none">{res.all ? "No changed record is in every stratum you picked." : "No other record changed."}</p>;
  return <div className="clist">{res.records.map((r) => {
    const c = data.rules.find((x) => x.rule_id === r.rule_id);
    return c ? <RecLine key={r.rule_id + r.key} r={r} card={c} short={short} many={many}><StrataTags tags={r.tags} /></RecLine> : null;
  })}</div>;
}

/** A changed value: the shared value diff (Split by default) with Note… and "The new value is wrong…" (property rules). */
function RecLine({ r, card, short, many, children }: RowProps & { r: BriefRow; children?: ReactNode }) {
  return (
    <div className="crec vrec">
      <CompareValue r={r} ruleId={card.rule_id} kind={card.kind} column={card.ctdl_property ?? card.title}
        head={<><Ck r={r} card={card} many={many} />{children}</>}>
        <See r={r} card={card} short={short} />
      </CompareValue>
    </div>
  );
}

function VerdictHead({ r, card, many }: { r: AnnotatedRowX; card: RuleCardX; many: boolean }) {
  const o = outcomeLabel(r);
  return <>
    <Ck r={r} card={card} many={many} />
    <span className="vb">
      <span className={`verdict ${r.verdict}`}><Ico name={r.verdict} />{VERDICT_LABEL[r.verdict]}</span>
      <span className="arr">→</span>
      <span className={`outcome ${o.cls}`}>{o.label}</span>
    </span>
  </>;
}

function VerdictNotes({ r }: { r: AnnotatedRowX }) {
  return <>
    {r.note && <div className="cnote">{r.author}: “{r.note}”</div>}
    {r.verdict === "wrong" && r.outcome !== "fixed" && r.expected != null &&
      <div className="cnote">Expected: “{r.expected.length > 160 ? r.expected.slice(0, 160) + "…" : r.expected}”</div>}
  </>;
}

function See({ r, card, short }: { r: BriefRow; card: RuleCardX; short: string }) {
  return <a className="see" href={seeHref(short, r, card, useContext(SeeCtx))}>See on page →</a>;
}

function SignalLine({ s, card, many, open, onToggle }: { s: SignalDeltaX; card: RuleCardX; many: boolean; open: boolean; onToggle: () => void }) {
  const d = s.b - s.a;
  return (
    <div className={"sigrow" + (open ? " open" : "")} role="button" tabIndex={0} aria-expanded={open} onClick={onToggle}
         onKeyDown={onEnterOrSpace(onToggle)}>
      <Ico name="chevron-right" className="tw" />
      <span className="sname">{many && <span className="rtag-i">{card.ctdl_property ?? card.title} · </span>}{s.signal}</span>
      <span className="num">{fmt(s.a)}</span>
      <span className="arrow">→</span>
      <span className="num">{fmt(s.b)}</span>
      <span className={"num " + (d < 0 ? "delta-down" : d > 0 ? "delta-up" : "faint")}>{delta(s.a, s.b)}</span>
    </div>
  );
}

function SignalDrill({ s, card, short }: { s: SignalDeltaX; card: RuleCardX; short: string }) {
  const lostN = s.lost_total ?? s.lost.length, gainedN = s.gained_total ?? s.gained.length;
  return (
    <div className="sigdrill">
      {lostN > 0 && <SignalRecords tone="good" rows={s.lost} card={card} short={short}
        heading={<>− {fmt(lostN)} lost it{lostN > s.lost.length ? ` (first ${s.lost.length})` : ""}</>} />}
      {gainedN > 0 && <SignalRecords tone="bad" rows={s.gained} card={card} short={short}
        heading={<>+ {fmt(gainedN)} gained it{gainedN > s.gained.length ? ` (first ${s.gained.length})` : ""}</>} />}
      {lostN === 0 && gainedN === 0 &&
        <div className="muted cmp-none">No record lost or gained it.</div>}
    </div>
  );
}

function storedPageSize(): number {
  try { const n = Number(localStorage.getItem(PAGE_SIZE_KEY)); if (PAGE_SIZES.includes(n)) return n; } catch { /* private */ }
  return 50;
}

function storePageSize(n: number) {
  try { localStorage.setItem(PAGE_SIZE_KEY, String(n)); } catch { /* private */ }
}

function Ck({ r, card, many }: { r: BriefRow; card: RuleCardX; many: boolean }) {
  return <span className="ck">{r.record_external_identifier ?? "—"}{many && <span className="rtag">{card.ctdl_property ?? card.title}</span>}</span>;
}

/** The Rules tab with this record selected, in To's ruleset; in From's when To has no such rule or record (a rule or
 *  a program-page line To dropped), so the link never lands on a rule the ruleset doesn't have. */
function seeHref(short: string, r: BriefRow, card: RuleCardX, ext: { a: string | null; b: string | null }): string {
  const inB = card.b_version != null && !card.vanished_rows.some((v) => v.key === r.key);
  return href(short, "rules", card.rule_id, { row: r.key, ext: inB ? ext.b : ext.a });
}

function SignalRecords({ tone, heading, rows, card, short }: { tone: string; heading: ReactNode; rows: BriefRow[]; card: RuleCardX; short: string }) {
  return <>
    <div className={`dh ${tone}`}>{heading}</div>
    <div className="clist">{rows.map((r) => <RecLine key={r.key} r={r} card={card} short={short} many={false} />)}</div>
  </>;
}

function onEnterOrSpace(action: () => void) {
  return (e: KeyboardEvent) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); action(); } };
}

function ver(v: number | null): string {
  return v == null ? "none" : `v${v}`;
}
