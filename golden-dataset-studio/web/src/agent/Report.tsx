// An AI run's report, rendered from `report.resolved.json` with the app's own components (one-rule-runs spec §1.4,
// §1.6, §2.3, pass 7): the outcome band, the facts, the values Claude worked out, what you need to decide, one section per rule
// (the rules to improve, then each rule Claude also changed), progress notes folded, and a footer with Past AI runs,
// Revert vN, View the prompt and, once rows have new feedback, ✦ Run again. Every course is its Rules tab row card
// (RowCard), whose verdict and history are refetched when the report opens and whenever its window gets focus. ✓ and
// comments act here; ✕ and Open in Rules → open the row in a new browser tab, pinned to the run's ruleset (`ext`).
// A decision tells its story first (pass 7): the question and why, then its answers as buttons (each posts one verdict
// per course, after the app's confirm, with Undo), then the evidence, every row card introduced in words and shown
// once per report; a set of courses is a table. Times are relative, the date and time zone in their tooltip.
// No " · " in anything rendered here: one fact per row, one history item per line, sentences.
import { useCallback, useEffect, useMemo, useRef, useState, type Dispatch, type ReactNode, type SetStateAction } from "react";
import { api } from "../api/client";
import type { CatalogDetail, EventBrief, NewEvent, RuleSummary } from "../api/types";
import "../evals/evals.css";
import type { RowX } from "../rules/api";
import { briefOf, fullTime, markWord, newDraft, reportHistory, rowTarget, verdictEvent, whereWord, type Draft, type HistItem } from "../rules/logic";
import { Expansion, When } from "../rules/parts";
import { RowCard } from "../rules/RowCard";
import { Ico } from "../shell/icons";
import { useReviewer } from "../shell/reviewer";
import { href } from "../shell/router";
import { fmt, termUrl, toast, toastAction } from "../shell/ui";
import { CATALOG_CHANGED, compareOf, agentApi, agentApi2, elapsed, endedIcon, endedLine, rowKey, type AgentRun, type HistEvent, type ReportCourse,
  type ReportInferred, type ReportRow, type ReportRowState, type ReportRows, type ReportRule, type ReportToDo, type ResolvedReport, type RunNote,
  type ToDoEvidence, type ToDoOption,
} from "./api";
import { openRunDialog } from "./RunDialog";
import "../rules/rules.css";
import "./agent.css";

export interface ReportProps {
  catalog: string; run: AgentRun; report: ResolvedReport; notes: RunNote[];
  /** the Watch panel shows Past AI runs in the footer; the runs panel has its own way back */
  pastRuns?: () => void;
}

/** A verdict posted from the report, and the one it replaced: Undo posts the replaced one again, superseding it. */
interface Posted { rule: string; course: string; target: NewEvent["target"]; id: string; prev: EventBrief | null }
type Post = (base: ReportRowState, ev: NewEvent, refetch?: boolean) => Promise<HistEvent | null>;
type Undo = (done: Posted[], what: string) => Promise<void>;
type Answer = NonNullable<ToDoOption["do"]>;

/** A decision's answer: the one waiting for its confirm, the one being posted, and what each posted (for Undo). */
interface AnswerState {
  asking: { t: number; o: number } | null; setAsking: (a: { t: number; o: number } | null) => void;
  busy: boolean; setBusy: (b: boolean) => void;
  posted: Record<string, Posted[]>; setPosted: Dispatch<SetStateAction<Record<string, Posted[]>>>;
}

interface ReportModel extends AnswerState {
  catalog: string; run: AgentRun; report: ResolvedReport; me: string; ext: string | null;
  ruleMeta: Map<string, RuleSummary>; states: Map<string, ReportRowState>; newFeedback: number;
  drafts: Record<string, Draft>; setDraftOf: (key: string, d: Draft | null) => void;
  post: Post; undo: Undo; reload: () => void;
}

/** One render of the report's sections: `seen` keeps every row card to once per report. */
interface RenderCtx extends ReportModel { seen: Set<string>; toDoOpen: boolean[] }

export function Report({ catalog, run, report, notes, pastRuns }: ReportProps) {
  const m = useReportModel(catalog, run, report);
  const revert = useRevert(catalog, run, report, m.me);
  const prompt = usePromptView(catalog, run.run_id);
  return (
    <>
      <ReportBody m={m} notes={notes} prompt={prompt} />
      <ReportFoot m={m} pastRuns={pastRuns} revert={revert} onViewPrompt={prompt.view} />
      {revert.asking && revert.version != null && <RevertDialog revert={revert} />}
      <AnswerDialog m={m} />
    </>
  );
}

// --- the report's state ------------------------------------------------------------------------------------------
function useReportModel(catalog: string, run: AgentRun, report: ResolvedReport): ReportModel {
  const me = useReviewer();
  const { data, reload, setData } = useReportRows(catalog, run.run_id);
  const ext = useExtraction(catalog, pinnedVersion(run), report.ruleset?.ext);
  const ruleMeta = useRuleMeta(catalog);
  const states = useMemo(() => new Map((data?.rows ?? []).map((s) => [rowKey(s.rule, s.course), s])), [data]);
  const { drafts, setDraftOf } = useDrafts();
  const answers = useAnswerState();
  const post = postFrom(catalog, setData, reload);
  return { catalog, run, report, me, ext, ruleMeta, states, drafts, setDraftOf, post, reload, ...answers,
    newFeedback: data?.new_feedback ?? 0, undo: undoFrom(me, states, post, reload) };
}

// --- the rows' current verdicts (refetched on open, focus and visibility) ----------------------------------------
/** GET …/rows on open, on window focus and when the page becomes visible (spec §1.6, the run poll's pattern). */
export function useReportRows(catalog: string, runId: string | null) {
  const [data, setData] = useState<ReportRows | null>(null);
  const load = useCallback(() => {
    if (!runId) return;
    agentApi2.rows(catalog, runId).then(setData, () => {});
  }, [catalog, runId]);
  useEffect(() => {
    setData(null);
    if (!runId) return;
    load();
    return refetchOnReturn(load);
  }, [runId, load]);
  return { data, reload: load, setData };
}

function refetchOnReturn(load: () => void): () => void {
  const onFocus = () => load();
  const onVis = () => { if (document.visibilityState === "visible") load(); };
  window.addEventListener("focus", onFocus);
  document.addEventListener("visibilitychange", onVis);
  return () => { window.removeEventListener("focus", onFocus); document.removeEventListener("visibilitychange", onVis); };
}

/** The extraction of a ruleset version (the Rules tab's `?ext=`): from the report when it says, else the catalog's list. */
function useExtraction(catalog: string, version: number | null, given?: string | null): string | null {
  const [ext, setExt] = useState<string | null>(given ?? null);
  useEffect(() => {
    if (given || version == null) { setExt(given ?? null); return; }
    let on = true;
    api.catalog(catalog).then((c: CatalogDetail) => {
      if (!on) return;
      const hit = [...c.extractions].filter((x) => x.ruleset_version === version).sort((a, b) => b.extraction.localeCompare(a.extraction))[0];
      setExt(hit?.extraction ?? null);
    }, () => {});
    return () => { on = false; };
  }, [catalog, version, given]);
  return ext;
}

/** Each rule's name, kind, where it looks and CTDL term, for the report's section headings (the latest ruleset). */
function useRuleMeta(catalog: string): Map<string, RuleSummary> {
  const [m, setM] = useState<Map<string, RuleSummary>>(new Map());
  useEffect(() => {
    let on = true;
    api.rules(catalog).then((r) => { if (on) setM(new Map(r.groups.flatMap((g) => g.rules).map((x) => [x.rule_id, x]))); }, () => {});
    return () => { on = false; };
  }, [catalog]);
  return m;
}

function useDrafts(): { drafts: Record<string, Draft>; setDraftOf: (key: string, d: Draft | null) => void } {
  const [drafts, setDrafts] = useState<Record<string, Draft>>({});
  const setDraftOf = (key: string, d: Draft | null) => setDrafts((x) => { const y = { ...x }; if (d) y[key] = d; else delete y[key]; return y; });
  return { drafts, setDraftOf };
}

function useAnswerState(): AnswerState {
  const [asking, setAsking] = useState<{ t: number; o: number } | null>(null);
  const [busy, setBusy] = useState(false);
  const [posted, setPosted] = useState<Record<string, Posted[]>>({});
  return { asking, setAsking, busy, setBusy, posted, setPosted };
}

/** Saving from the report: the event the Rules tab would post; the row shows it at once, then the rows refetch. */
function postFrom(catalog: string, setData: Dispatch<SetStateAction<ReportRows | null>>, reload: () => void): Post {
  return async (base, ev, refetch = true) => {
    try {
      const r = await api.annotate(catalog, ev);
      const b = postedBrief(r.event as Parameters<typeof briefOf>[0] & { reasons?: string[] });
      setData((d) => withEvent(d, base, b));
      if (refetch) reload();
      return b;
    } catch (e) {
      toast(`Not saved: ${String(e instanceof Error ? e.message : e)}`);
      return null;
    }
  };
}

function postedBrief(stored: Parameters<typeof briefOf>[0] & { reasons?: string[] }): HistEvent {
  return { ...briefOf(stored), ...(stored.reasons?.length ? { reasons: stored.reasons } : {}), after_run: true };
}

function withEvent(d: ReportRows | null, base: ReportRowState, b: HistEvent): ReportRows {
  const key = rowKey(base.rule, base.course);
  const add = (s: ReportRowState): ReportRowState =>
    ({ ...s, history: [...s.history, b], ...(b.type === "verdict" && b.verdict ? { verdict: b, state: b.verdict } : {}) });
  const all = d?.rows ?? [];
  const has = all.some((s) => rowKey(s.rule, s.course) === key);
  const rows = has ? all.map((s) => (rowKey(s.rule, s.course) === key ? add(s) : s)) : [...all, add(base)];
  return { annotations_as_of: null, new_feedback: 0, ...d, rows };
}

/** Undo verdicts posted from the report: one superseding verdict per course, restoring what was there before. */
function undoFrom(me: string, states: Map<string, ReportRowState>, post: Post, reload: () => void): Undo {
  return async (done, what) => {
    let n = 0;
    for (const p of done) {
      const ev = undoEvent(me, p);
      if (!ev) continue;
      const st = states.get(rowKey(p.rule, p.course));
      if (await post(st ?? { rule: p.rule, course: p.course, state: null, verdict: null, history: [] }, ev, false)) n++;
    }
    reload();
    toast(n ? `Undone: ${what}` : "Nothing to undo: there was no earlier mark");
  };
}

/** The event that undoes a verdict posted from the report: the log is append-only (no retract), so it is a new
 * verdict that supersedes the mistaken one and restores the earlier verdict's verdict, expected value and note. */
export function undoEvent(author: string, p: Posted): NewEvent | null {
  if (!p.prev?.verdict) return null;
  return { type: "verdict", author, target: p.target, verdict: p.prev.verdict, supersedes: p.id,
           note: p.prev.note ?? null, expected: p.prev.expected ?? null, ...(p.prev.reasons?.length ? { reasons: p.prev.reasons } : {}) };
}

type Revert = ReturnType<typeof useRevert>;

function useRevert(catalog: string, run: AgentRun, report: ResolvedReport, me: string) {
  const [asking, setAsking] = useState(false);
  const [revertedIn, setRevertedIn] = useState<number | null>(report.reverted_in ?? null);
  const version = revertVersion(run, report, revertedIn);
  // the confirm is the app's own dialog (the run button's `.ac.run-ask`), not the browser's
  const revert = async () => {
    if (version == null) return;
    setAsking(false);
    const revertedTo = await postRevert(catalog, version, me);
    if (revertedTo != null) { setRevertedIn(revertedTo); window.dispatchEvent(new Event(CATALOG_CHANGED)); }
  };
  return { asking, setAsking, revertedIn, version, text: revertText(run, report, version), revert };
}

async function postRevert(catalog: string, version: number, me: string): Promise<number | null> {
  try {
    const r = await agentApi2.revert(catalog, version, me);
    toast(`Reverted: ruleset v${r.version} is published`);
    return r.version;
  } catch (e) {
    toast(`Not reverted: ${String(e instanceof Error ? e.message : e)}`);
    return null;
  }
}

function revertVersion(run: AgentRun, report: ResolvedReport, revertedIn: number | null): number | null {
  if (revertedIn != null || report.reverted_in != null) return null;
  return report.revert?.version ?? (published(run) ? run.ruleset_after : null);
}

function revertText(run: AgentRun, report: ResolvedReport, version: number | null): string {
  if (version == null) return "";
  const changed = [...report.rules, ...report.also_changed].map((r) => r.name);
  return report.revert?.text ?? `Revert v${version}? This publishes v${version + 1} with `
    + `${andList(changed)} back to how ${changed.length === 1 ? "it was" : "they were"} in v${run.ruleset_before}.`;
}

type PromptView = ReturnType<typeof usePromptView>;

function usePromptView(catalog: string, runId: string) {
  const [shown, setShown] = useState(false);
  const [text, setText] = useState<string | null>(null);
  const ref = useRef<HTMLElement>(null);
  const view = () => {
    setShown(true);
    if (text === null) agentApi.prompt(catalog, runId).then((p) => setText(p.text), () => setText("(the prompt wasn't kept)"));
    setTimeout(() => ref.current?.scrollIntoView?.({ block: "start" }), 0);
  };
  return { shown, text, ref, view };
}

// --- the report --------------------------------------------------------------------------------------------------
function ReportBody({ m, notes, prompt }: { m: ReportModel; notes: RunNote[]; prompt: PromptView }) {
  return (
    <div className="runs-detail" data-testid="run-report">
      <OutcomeBand m={m} />
      <RulesToc report={m.report} version={m.run.ruleset_after} />
      <ReportFacts run={m.run} report={m.report} />
      {renderSections(m)}
      {m.report.notes && <details className="runs-sec run-fold"><summary>Claude's notes</summary>
        <p className="report-notes">{m.report.notes}</p></details>}
      <ReportProgressNotes run={m.run} notes={notes} />
      {prompt.shown && <section className="runs-sec" ref={prompt.ref}><h3>The prompt Claude was given</h3>
        <pre className="prompt-pre runs-prompt">{prompt.text ?? "Loading…"}</pre></section>}
    </div>
  );
}

function OutcomeBand({ m: { catalog, run, report, newFeedback } }: { m: ReportModel }) {
  const cmp = reportCompare(run, report);
  return (
    <div className={`run-done is-${partialReport(report) ? "partial" : run.state}`}>
      <Ico name={partialReport(report) ? "question" : endedIcon(run)} />
      <span className="run-done-t">{bandLine(report) || endedLine(run)}</span>
      {cmp && <a className={`btn${newFeedback ? "" : " primary"}`} href={href(catalog, "compare", null, cmp)}
        title="What changed between the two rulesets, rule by rule">Compare v{cmp.a} → v{cmp.b}</a>}
    </div>
  );
}

/** The report's own pair (the CLI read this run's publishes), else the run record's. */
function reportCompare(run: AgentRun, report: ResolvedReport): { a: number; b: number } | null {
  if (!published(run)) return null;
  return report.ruleset?.compare ? { a: report.ruleset.compare.a, b: report.ruleset.compare.b } : compareOf(run);
}

function RulesToc({ report, version }: { report: ResolvedReport; version: number | null }) {
  const toc = tocOf(report);
  if (toc.length <= 1) return null;
  return (
    <nav className="report-toc" data-testid="report-toc" aria-label="Rules in this report">
      <ul>{toc.map(([r, also]) => {
        const [ico, cls, words] = resultOf(r, also, version);
        return (
          <li key={`${also ? "a" : "g"}-${r.rule}`} className={cls}>
            <button className="linkish" onClick={() => scrollToSection(r.rule)} title={`Scroll to ${r.name}`}>
              <Ico name={ico} /><b>{r.name}</b> <span>{words}</span></button>
          </li>);
      })}</ul></nav>
  );
}

function ReportFacts({ run, report }: { run: AgentRun; report: ResolvedReport }) {
  const facts = factsOf(run, report);
  const listed = tocOf(report).length > 1;
  return (
    <dl className="run-facts" data-testid="report-facts">
      {facts.filter((f) => !isRuleset(f) && !(listed && (f.label === "Rules to improve" || f.label === "Also changed")))
        .map((f) => <Fact key={f.label} label={f.label} text={f.text} />)}
      <dt>Started</dt><dd><When at={run.created_at} /> by {run.started_by}</dd>
      {run.ended_at && <><dt>Ran</dt><dd>{elapsed(run.sent_at ?? run.created_at, run.ended_at)}</dd></>}
      {facts.filter(isRuleset).map((f) => <Fact key={f.label} label={f.label} text={f.text} />)}
      {report.ending === "failed" && report.reason && <Fact label="Why" text={report.reason} />}
    </dl>
  );
}

function factsOf(run: AgentRun, report: ResolvedReport): { label: string; text: string }[] {
  const facts = [...report.facts ?? defaultFacts(report)];
  if (!published(run) && run.ruleset_before != null && !facts.some(isRuleset)) {
    facts.push({ label: "Ruleset", text: `v${run.ruleset_before}, unchanged` });
  }
  return facts;
}

function defaultFacts(report: ResolvedReport): { label: string; text: string }[] {
  return [
    ...(report.rules.length ? [{ label: "Rules to improve", text: andList(report.rules.map((r) => r.name)) }] : []),
    ...(report.also_changed.length ? [{ label: "Also changed", text: andList(report.also_changed.map((r) => r.name)) }] : []),
  ];
}

// --- the sections: decisions, values Claude worked out, and one per rule ------------------------------------------
// Plain render functions, not components: every row card is shown once per report, in the order this render reaches it.
function renderSections(m: ReportModel): ReactNode {
  const ctx: RenderCtx = { ...m, seen: new Set(), toDoOpen: openToDos(m.report.to_do) };
  const { goals, otherToDos, otherInf } = sectionsOf(m.report);
  return <>
    {(otherToDos.length > 0 || otherInf.length > 0) && <section className="runs-sec">
      {otherToDos.map(([t, i]) => renderToDo(ctx, t, i))}
      {otherInf.map((x, i) => renderInferred(ctx, x, i === 0, true))}</section>}
    {goals.map((r) => renderRuleSection(ctx, r, false))}
    {m.report.also_changed.map((r) => renderRuleSection(ctx, r, true))}
  </>;
}

/** The rules to improve, held first; decisions and values on no rule of the report keep a section of their own. */
function sectionsOf(report: ResolvedReport) {
  const ruleIds = new Set([...report.rules, ...report.also_changed].map((r) => r.rule));
  const otherToDos = report.to_do.map((t, i) => [t, i] as const).filter(([t]) => !ruleIds.has(toDoRule(t) ?? ""));
  const otherInf = report.inferred.filter((x) => !ruleIds.has(x.rule));
  return { goals: goalsInOrder(report), otherToDos, otherInf };
}

function renderRuleSection(ctx: RenderCtx, r: ReportRule, also: boolean): ReactNode {
  const prose = also ? r.why : [r.now && `Now ${r.now}.`, r.why].filter(Boolean).join(" ");
  const toDos = ctx.report.to_do.map((t, i) => [t, i] as const).filter(([t]) => toDoRule(t) === r.rule);
  return (
    <section key={`${also ? "a" : "g"}-${r.rule}`} id={sectionId(r.rule)} className="runs-sec report-rule" data-testid="rule-section">
      <RuleSectionHead rule={r} also={also} version={ctx.run.ruleset_after} meta={ctx.ruleMeta.get(r.rule)} />
      {toDos.map(([t, i]) => renderToDo(ctx, t, i))}
      {ctx.report.inferred.filter((x) => x.rule === r.rule).map((x, i) => renderInferred(ctx, x, i === 0))}
      {r.values_changed && <ValuesChanged catalog={ctx.catalog} rule={r.rule} vc={r.values_changed} />}
      {prose && <p>{prose}</p>}
      {r.rows.map((rr) => renderCard(ctx, rr))}
    </section>
  );
}

/** Values Claude worked out and decisions, each kept with its rule: the first open, the rest folded. */
function renderInferred(ctx: RenderCtx, inf: ReportInferred, first: boolean, other = false): ReactNode {
  const body = <><p>{inferredWhy(inf)}</p>{renderCard(ctx, inf.row, { hist: pageQuotes(inf) })}</>;
  const key = `inf-${inf.rule}-${inf.course}`;
  const label = `${other ? `${inf.rule_name ?? inf.rule}: a` : "A"} value Claude worked out for ${inf.row.title ?? inf.course}`;
  return first
    ? <div key={key} className="report-sub" data-testid="inferred"><h3>{label}</h3>{body}</div>
    : <details key={key} className="report-sub run-fold" data-testid="inferred"><summary>{label}</summary>{body}</details>;
}

function inferredWhy(inf: ReportInferred): string {
  const v = inf.row.verdict;
  return v?.verdict === "wrong" && !v.expected?.text
    ? `${v.author} marked ${inf.course} wrong without selecting the right text. Claude worked out the value below from the notes and the page.`
    : "Claude worked out the value below from the notes and the page.";
}

function pageQuotes(inf: ReportInferred): HistItem[] {
  return (inf.evidence ?? []).filter((e) => e.source?.kind === "page").map((e) => ({ cls: "muted" as const, text: `On the page: “${e.quote}”` }));
}

function renderToDo(ctx: RenderCtx, t: ReportToDo, i: number): ReactNode {
  const body = renderToDoBody(ctx, t, i);
  return ctx.toDoOpen[i]
    ? <div key={`td${i}`} className="report-sub" data-testid="to-do"><h3>{t.ask}</h3>{body}</div>
    : <details key={`td${i}`} className="report-sub run-fold" data-testid="to-do"><summary>{t.ask}</summary>{body}</details>;
}

/** A decision: what to decide and why, the answers, then the evidence (pass 7). */
function renderToDoBody(ctx: RenderCtx, t: ReportToDo, ti: number): ReactNode {
  const optionEffects = t.options.some((o) => o.effect);
  return <>
    {t.why && <p className="report-why" data-testid="to-do-why">{t.why}</p>}
    <Answers m={ctx} toDo={t} index={ti} />
    {!optionEffects && (t.effect ?? []).length > 0 && <p className="faint">{(t.effect ?? []).map((e) => e.text).join(" ")}</p>}
    {t.about.map((r) => <div key={`ab-${rowKey(r.rule, r.course)}`}>{renderCard(ctx, r, { intro: aboutIntro(ctx.states, r) })}</div>)}
    {renderEvidence(ctx, t)}
  </>;
}

function aboutIntro(states: Map<string, ReportRowState>, r: ReportRow & { lead?: string | null }): string {
  if (r.lead) return r.lead;
  const v = states.get(rowKey(r.rule, r.course))?.verdict ?? r.verdict;
  return v && (v.verdict === "correct" || v.verdict === "wrong") ? `Here is the row ${v.author} marked ${v.verdict}:` : "Here is the row this question is about:";
}

function renderEvidence(ctx: RenderCtx, t: ReportToDo): ReactNode[] {
  const shown = new Set(t.about.map((r) => rowKey(r.rule, r.course)));
  return t.evidence.map((e, i) => (e.kind === "quote" ? renderQuote(e, i, shown) : renderCourseSet(ctx, e, i)));
}

function renderQuote(e: Extract<ToDoEvidence, { kind: "quote" }>, i: number, shown: Set<string>): ReactNode {
  const src = e.source;
  if (src?.kind === "note" && src.course && src.rule && shown.has(rowKey(src.rule, src.course))) return null;  // on the card
  const who = src?.kind === "page" ? `On ${src.course}'s page:` : src?.author ? `${src.author}'s note${src.course ? ` on ${src.course}` : ""}:` : null;
  return <div key={i} className="report-quote">{who && <div className="faint">{who}</div>}
    <blockquote className="sel-quote">{e.quote}</blockquote></div>;
}

function renderCourseSet(ctx: RenderCtx, e: Extract<ToDoEvidence, { kind: "set" }>, i: number): ReactNode {
  const first = e.rows[0];
  return (
    <div key={i}>
      {first && renderCard(ctx, first, { intro: first.lead ?? (e.count > 1 ? `Here is one of the ${fmt(e.count)} courses ${e.label}:` : `Here is the course ${e.label}:`) })}
      {e.courses.length > 0 && <CourseTable key={`t-${e.rule}`} m={ctx} rule={e.rule} courses={e.courses} lead={e.others_lead
        ?? `The other ${fmt(e.courses.length)} ${e.courses.length === 1 ? "course" : "courses"} ${e.label}:`} />}
    </div>);
}

/** Every row card once per report (pass 7): a later mention links back to the card above. */
function renderCard(ctx: RenderCtx, rr: ReportRow, o: { hist?: HistItem[]; intro?: string | null } = {}): ReactNode {
  const key = rowKey(rr.rule, rr.course);
  if (ctx.seen.has(key)) return shownAbove(ctx.run.run_id, rr);
  ctx.seen.add(key);
  return <ReportCard key={key} m={ctx} rr={rr} hist={o.hist} intro={o.intro} />;
}

function shownAbove(runId: string, rr: ReportRow): ReactNode {
  const go = () => document.getElementById(domId(runId, rr.rule, rr.course))?.scrollIntoView?.({ block: "start", behavior: "smooth" });
  const link = <button className="linkish" onClick={go}>shown above</button>;
  return (
    <p key={`above-${rowKey(rr.rule, rr.course)}-c`} className="report-above" data-testid="shown-above">
      {rr.comment ? <>Claude's comment is on {rr.course}'s row, {link}.</> : <>{rr.course}'s row is {link}.</>}
    </p>);
}

// --- a row card ---------------------------------------------------------------------------------------------------
interface Card {
  rr: ReportRow; row: RowX; history: HistEvent[]; base: ReportRowState; target: NewEvent["target"]; lab: string;
  saves: boolean; draft: Draft | null; setDraft: (d: Draft | null) => void;
}

function ReportCard({ m, rr, hist, intro }: { m: ReportModel; rr: ReportRow; hist?: HistItem[]; intro?: string | null }) {
  const c = cardOf(m, rr);
  return (
    <div id={domId(m.run.run_id, rr.rule, rr.course)}>
      {intro && <p className="report-lead" data-testid="row-lead">{intro}</p>}
      <div className="rows"><RowCard row={c.row} kind="property" label={c.lab} on stacked review={false} lead={[...valueBefore(rr), ...(hist ?? [])]}
        history={reportHistory(c.history)} draft={c.draft} onPick={(v) => void pickVerdict(m, c, v)}
        {...cardTitles(rr.course, c.lab, c.saves)}
        links={<CardLinks m={m} rr={rr} lab={c.lab} occurrence={c.row.occurrence_key} />}
        below={rr.left_out?.length ? <LeftOut passages={rr.left_out} /> : null}
        expansion={c.draft ? <Expansion draft={c.draft} propertyRule onChange={c.setDraft} onSave={() => void saveComment(m, c)}
          onCancel={() => c.setDraft(null)} /> : null} /></div>
    </div>
  );
}

function cardOf(m: ReportModel, rr: ReportRow): Card {
  const key = rowKey(rr.rule, rr.course);
  const st = m.states.get(key);
  const history = st?.history ?? rr.history ?? [];
  const row = toRow(rr, st, history);
  return {
    rr, row, history,
    base: st ?? { rule: rr.rule, course: rr.course, state: row.state, verdict: row.verdict, history },
    target: rowTarget("property", rr.rule, { occurrence_key: row.occurrence_key, page_stem: rr.page_stem }),
    lab: rr.legend ?? rr.rule_name ?? rr.rule,
    saves: rr.inferred?.saves === "expected",
    draft: m.drafts[key] ?? null,
    setDraft: (d) => m.setDraftOf(key, d),
  };
}

function cardTitles(course: string, lab: string, saves: boolean) {
  return {
    okTitle: saves ? `Mark ${course}'s ${lab} correct: saves the value Claude worked out as its expected ${lab}` : `Mark ${course}'s ${lab} correct`,
    wrongTitle: `Mark ${course}'s ${lab} wrong: opens the row in the Rules tab, in a new browser tab, to select the right text`,
    talkTitle: `Comment on ${course}'s ${lab}`,
  };
}

function CardLinks({ m, rr, lab, occurrence }: { m: ReportModel; rr: ReportRow; lab: string; occurrence: string | null }) {
  return <>
    <a className="xbtn" href={href(m.catalog, "records", rr.course, { prop: lab, occ: occurrence })}
      title="Open this course in the Records tab">Open in Records →</a>{" "}
    <a className="xbtn" href={rr.links?.rules ?? rulesHref(m.catalog, rr.rule, rr.course, m.ext)} target="_blank" rel="noopener"
      title="Opens this row in the Rules tab in a new browser tab, at the ruleset the run published, with its page beside it">Open in Rules →</a>
  </>;
}

function valueBefore(rr: ReportRow): HistItem[] {
  return rr.value_before ? [{ cls: "muted" as const, text: `In v${rr.value_before.version}: ${rr.value_before.value || "empty"}` }] : [];
}

async function pickVerdict(m: ReportModel, c: Card, v: "correct" | "wrong" | "comment"): Promise<void> {
  if (v === "wrong") { window.open(c.rr.links?.wrong ?? rulesHref(m.catalog, c.rr.rule, c.rr.course, m.ext, true), "_blank", "noopener"); return; }
  if (v === "comment") { c.setDraft(c.draft?.mode === "comment" ? null : newDraft("comment", c.row.verdict, c.row.state)); return; }
  if (!c.saves && c.row.verdict?.verdict === "correct" && c.row.state === "correct") {
    toast(`${c.rr.course}'s ${c.lab} is already marked correct`);  // a second ✓ would only repeat it
    return;
  }
  await markCorrect(m, c);
}

async function markCorrect(m: ReportModel, c: Card): Promise<void> {
  const prev = c.row.verdict ?? null;
  const b = await m.post(c.base, correctEvent(m.me, c, prev));
  if (!b) return;
  const { course } = c.rr;
  const what = c.saves ? `Saved the value Claude worked out as ${course}'s expected ${c.lab}` : `Marked ${course}'s ${c.lab} correct`;
  const p: Posted = { rule: c.rr.rule, course, target: c.target, id: b.annotation_id, prev: prev?.type === "verdict" ? prev : null };
  if (undoEvent(m.me, p)) toastAction(what, "Undo", () => void m.undo([p], `${course}'s ${c.lab} is back to ${markWord(prev).toLowerCase()}`));
  else toast(what);
}

/** ✓ (spec §2.4): an inferred value the run didn't publish is saved as the expected value of the open ✕. */
function correctEvent(me: string, c: Card, prev: EventBrief | null): NewEvent {
  const inf = c.rr.inferred;
  return c.saves
    ? { type: "verdict", author: me, target: c.target, verdict: "wrong", supersedes: inf!.annotation,
        expected: { text: inf!.value, css_path: null, char_start: null, char_end: null } }
    : verdictEvent(me, c.target, prev, { verdict: "correct" });
}

async function saveComment(m: ReportModel, c: Card): Promise<void> {
  if (!c.draft) return;
  const b = await m.post(c.base, verdictEvent(m.me, c.target, c.row.verdict, { draft: c.draft }));
  if (b) { c.setDraft(null); toast(`Comment saved on ${c.rr.course}'s ${c.lab}`); }
}

function toRow(r: ReportRow, st: ReportRowState | undefined, history: HistEvent[]): RowX {
  const inf = r.inferred && r.inferred.saves === "expected" ? r.inferred : null;
  const value = inf ? inf.value : r.value;
  return {
    key: rowKey(r.rule, r.course), occurrence_key: r.occurrence_key ?? st?.occurrence_key ?? null, record_external_identifier: r.course,
    page_stem: r.page_stem, url: r.url, page_title: r.title, context: r.title,
    value, status: inf ? (value ? "found" : "absent") : r.status,
    css_path: null, char_start: null, char_end: null, occurrence_css_path: null,
    state: st ? st.state : r.state ?? null, verdict: st ? st.verdict : r.verdict ?? null, reattached: !!st?.reattached,
    comments: history.filter((e) => e.type === "comment"),
    human_reviewed: st?.human_reviewed, engineer_checked: st?.engineer_checked, signal_count: 0, group: null,
  };
}

// --- a decision's answers -----------------------------------------------------------------------------------------
function Answers({ m, toDo: t, index: ti }: { m: ReportModel; toDo: ReportToDo; index: number }) {
  if (!t.options.length) return null;
  if (!t.options.some((o) => o.do?.event || o.button)) {  // a report resolved before pass 7: the answers as sentences
    return <>{t.options.map((o, i) => <p key={i} className="report-option">{optionText(o.text)}</p>)}</>;
  }
  const doneAt = t.options.findIndex((o) => isDone(m.states, o));
  if (doneAt >= 0) return <AnswerDone m={m} option={t.options[doneAt]} postKey={`${ti}:${doneAt}`} />;
  return (
    <div className="report-options" data-testid="answers">
      {t.options.map((o, oi) => <AnswerOption key={oi} option={o} busy={m.busy} onAsk={() => m.setAsking({ t: ti, o: oi })} />)}
    </div>);
}

function AnswerDone({ m, option: o, postKey }: { m: ReportModel; option: ToDoOption; postKey: string }) {
  const mine = m.posted[postKey];
  const again = o.then?.run_again?.map((r) => r.rule) ?? [];
  return (
    <div className="report-options" data-testid="answer-done">
      <p className="report-option"><b>Done:</b> {o.done ?? doWords(o)}.{mine && <>{" "}
        <button className="linkish" disabled={m.busy} onClick={() => undoAnswer(m, postKey, mine)}>Undo</button></>}
      </p>
      {again.length > 0 && <p className="report-option">{o.then?.text}{" "}
        <button className="btn primary" onClick={() => openRunDialog(again)}><Ico name="spark" />Run again</button></p>}
    </div>);
}

function AnswerOption({ option: o, busy, onAsk }: { option: ToDoOption; busy: boolean; onAsk: () => void }) {
  const extra = [o.effect, ...(o.no_rule_yet ?? []), o.then?.text].filter(Boolean).join(" ");
  return (
    <div className="report-option">
      {o.do?.event
        ? <button className="btn" disabled={busy} onClick={onAsk}
            title={`${doWords(o)} for ${o.do.rule_name ?? o.do.rule}. You confirm first, and can undo it.`}>{o.button ?? doWords(o)}</button>
        : o.link
          ? <a className="btn" href={o.link} target="_blank" rel="noopener" title="Opens the rows in the Rules tab, in a new browser tab">{o.button ?? o.answer}</a>
          : <span><b>{o.button ?? o.answer}</b></span>}
      {extra && <span className="faint">{extra}</span>}
    </div>);
}

async function answer(m: ReportModel, ti: number, oi: number): Promise<void> {
  const d = m.report.to_do[ti].options[oi].do;
  m.setAsking(null);
  if (!d?.event) return;
  m.setBusy(true);
  const done = await postAnswer(m, d);
  m.setBusy(false);
  m.reload();
  if (done.length) offerUndo(m, `${ti}:${oi}`, done, d.words);
}

async function postAnswer(m: ReportModel, d: Answer): Promise<Posted[]> {
  const done: Posted[] = [];
  for (const c of d.courses) {
    const now = nowOf(m.states, c, d.rule);
    const target = rowTarget("property", d.rule, { occurrence_key: now.occurrence_key, page_stem: c.page_stem ?? "" });
    const prev = now.verdict?.type === "verdict" ? now.verdict : null;
    if (hasMark(prev, d.mark)) continue;  // already so: nothing to post
    const st = m.states.get(rowKey(d.rule, c.course));
    const b = await m.post(st ?? { rule: d.rule, course: c.course, state: c.state ?? null, verdict: prev, history: [] }, answerEvent(m.me, target, d, prev), false);
    if (!b) break;
    done.push({ rule: d.rule, course: c.course, target, id: b.annotation_id, prev });
  }
  return done;
}

function answerEvent(me: string, target: NewEvent["target"], d: Answer, prev: EventBrief | null): NewEvent {
  return { type: "verdict", author: me, target, verdict: d.event!.verdict, supersedes: prev?.annotation_id ?? null,
           ...(d.event!.reasons ? { reasons: d.event!.reasons } : {}) };
}

function offerUndo(m: ReportModel, key: string, done: Posted[], words: string): void {
  m.setPosted((x) => ({ ...x, [key]: done }));
  const what = done.length === 1 ? `${done[0].course} marked ${words}` : `${fmt(done.length)} courses marked ${words}`;
  toastAction(`Done: ${what}`, "Undo", () => undoAnswer(m, key, done));
}

function undoAnswer(m: ReportModel, key: string, done: Posted[]): void {
  m.setPosted((x) => { const y = { ...x }; delete y[key]; return y; });
  void m.undo(done, `${done.length === 1 ? done[0].course : `${fmt(done.length)} courses`} back to their earlier marks`);
}

/** A course's verdict now: from the refetched rows, else as the run ended. */
function nowOf(states: Map<string, ReportRowState>, c: ReportCourse, rule: string): { verdict: EventBrief | null; occurrence_key: string | null } {
  const st = states.get(rowKey(rule, c.course));
  return { verdict: st ? st.verdict : c.current ?? null, occurrence_key: st?.occurrence_key ?? c.occurrence_key ?? null };
}

function isDone(states: Map<string, ReportRowState>, o: ToDoOption): boolean {
  return !!o.do?.event && o.do.courses.length > 0 && o.do.courses.every((c) => hasMark(nowOf(states, c, o.do!.rule).verdict, o.do!.mark));
}

function doWords(o: ToDoOption): string {
  const d = o.do!;
  return `Mark ${d.count === 1 ? d.courses[0]?.course : `${fmt(d.count)} courses`} ${d.words}`;
}

/** The rest of a set of courses: a table, one row per course, folded when long. */
function CourseTable({ m, rule, courses, lead }: { m: ReportModel; rule: string; courses: ReportCourse[]; lead: string }) {
  const table = (
    <table className="evx-wrong-t report-courses" data-testid="course-table">
      <thead><tr><th>Course</th><th>Title</th><th>Value</th><th>Mark</th><th /></tr></thead>
      <tbody>{courses.map((c) => <CourseLine key={c.course} m={m} rule={rule} course={c} />)}</tbody>
    </table>);
  return courses.length > 5
    ? <details className="run-fold"><summary>{lead.replace(/:$/, "")}</summary>{table}</details>
    : <div><p className="report-lead">{lead}</p>{table}</div>;
}

function CourseLine({ m, rule, course: c }: { m: ReportModel; rule: string; course: ReportCourse }) {
  const v = nowOf(m.states, c, c.rule ?? rule).verdict;
  return (
    <tr>
      <td>{c.course}</td><td>{c.title ?? ""}</td><td className="report-val">{valueText(c.value, c.status)}</td>
      <td>{v ? markWord(v) : c.verdict === "correct" ? "Correct" : c.verdict === "wrong" ? "Wrong" : "Not reviewed"}</td>
      <td><a className="xbtn" href={c.links?.rules ?? rulesHref(m.catalog, c.rule ?? rule, c.course, m.ext)} target="_blank" rel="noopener"
        title={`Opens ${c.course}'s row in the Rules tab, in a new browser tab`}>Open in Rules →</a></td>
    </tr>);
}

// --- the foot and its dialogs ---------------------------------------------------------------------------------------
function ReportFoot({ m, pastRuns, revert, onViewPrompt }: { m: ReportModel; pastRuns?: () => void; revert: Revert; onViewPrompt: () => void }) {
  return (
    <div className="ac-foot" data-testid="report-foot">
      {pastRuns ? <button className="linkish" onClick={pastRuns}>Past AI runs</button> : <span />}
      <FootActions m={m} revert={revert} onViewPrompt={onViewPrompt} />
    </div>
  );
}

function FootActions({ m: { run, report, newFeedback }, revert, onViewPrompt }: { m: ReportModel; revert: Revert; onViewPrompt: () => void }) {
  return (
    <span className="report-foot-r">
      {newFeedback > 0 && <span className="faint" data-testid="new-feedback">{newFeedback === 1 ? "1 row has" : `${fmt(newFeedback)} rows have`} new
        feedback since this run.</span>}
      {revert.revertedIn != null && <span className="faint" data-testid="reverted-in">Reverted in v{revert.revertedIn}.</span>}
      {revert.version != null && <button className="btn" onClick={() => revert.setAsking(true)}
        title={`Publishes a new ruleset with every rule v${revert.version} changed back to how it was`}>Revert v{revert.version}</button>}
      <button className="btn" onClick={onViewPrompt}>View the prompt</button>
      {newFeedback > 0 && <button className="btn primary" onClick={() => openRunDialog(run.scope.rules ?? report.rules.map((r) => r.rule))}>
        <Ico name="spark" />Run again</button>}
    </span>
  );
}

function RevertDialog({ revert }: { revert: Revert }) {
  const close = () => revert.setAsking(false);
  return (
    <ConfirmDialog labelId="revert-ask-h" testId="revert-ask" title={<>Revert v{revert.version}?</>} onClose={close}
      confirm={<button className="btn primary" onClick={() => void revert.revert()} autoFocus>Revert v{revert.version}</button>}>
      <div className="ac-body"><p>{revert.text.replace(/^Revert v\d+\? /, "")}</p></div>
    </ConfirmDialog>
  );
}

function AnswerDialog({ m }: { m: ReportModel }) {
  const ask = m.asking ? m.report.to_do[m.asking.t]?.options[m.asking.o] : null;
  const d = ask?.do ?? null;
  if (!ask || !d || !m.asking) return null;
  const { t, o } = m.asking;
  const toPost = d.courses.filter((c) => !hasMark(nowOf(m.states, c, d.rule).verdict, d.mark));
  return (
    <ConfirmDialog labelId="answer-ask-h" testId="answer-ask" title={<>{doWords(ask)}?</>} onClose={() => m.setAsking(null)}
      confirm={<button className="btn primary" disabled={!toPost.length} onClick={() => void answer(m, t, o)} autoFocus>{doWords(ask)}</button>}>
      <AnswerAskBody m={m} option={ask} toPost={toPost} />
    </ConfirmDialog>
  );
}

function AnswerAskBody({ m, option, toPost }: { m: ReportModel; option: ToDoOption; toPost: ReportCourse[] }) {
  const d = option.do!;
  return (
    <div className="ac-body">
      <p>{toPost.length === 0 ? `Every course is already marked ${d.words}. Nothing will be posted.`
        : `This records ${toPost.length === 1 ? "one verdict" : `${fmt(toPost.length)} verdicts`} on ${d.rule_name ?? d.rule}, `
          + `one per course, as ${m.me}. Each replaces the course's current mark. You can undo it afterwards.`}</p>
      {toPost.length > 0 && <AnswerCourses m={m} answer={d} toPost={toPost} />}
      {(option.then?.text || option.no_rule_yet?.length) && <p className="run-note">{[...(option.no_rule_yet ?? []), option.then?.text].filter(Boolean).join(" ")}</p>}
    </div>
  );
}

function AnswerCourses({ m, answer: d, toPost }: { m: ReportModel; answer: Answer; toPost: ReportCourse[] }) {
  return (
    <div className="report-ask-list"><table className="evx-wrong-t" data-testid="answer-ask-courses">
      <thead><tr><th>Course</th><th>Title</th><th>Now</th><th>After</th></tr></thead>
      <tbody>{toPost.map((c) => (
        <tr key={c.course}><td>{c.course}</td><td>{c.title ?? ""}</td><td>{markWord(nowOf(m.states, c, d.rule).verdict)}</td>
          <td>{markWord({ verdict: d.event!.verdict, reasons: d.event!.reasons })}</td></tr>))}</tbody>
    </table></div>
  );
}

interface ConfirmDialogProps { labelId: string; testId: string; title: ReactNode; onClose: () => void; confirm: ReactNode; children: ReactNode }

function ConfirmDialog({ labelId, testId, title, onClose, confirm, children }: ConfirmDialogProps) {
  return (
    <div className="ac-back" onClick={onClose}>
      <div className="ac run-ask" role="dialog" aria-modal="true" aria-labelledby={labelId} data-testid={testId}
        onClick={(e) => e.stopPropagation()}>
        <div className="ac-head"><h2 id={labelId}>{title}</h2>
          <button className="ac-x" aria-label="Close" onClick={onClose}>×</button></div>
        {children}
        <div className="ac-foot"><button className="btn" onClick={onClose}>Cancel</button>{confirm}</div>
      </div>
    </div>
  );
}

// --- small pieces ---------------------------------------------------------------------------------------------------
function ReportProgressNotes({ run, notes }: { run: AgentRun; notes: RunNote[] }) {
  return (
    <details className="runs-sec run-fold">
      <summary>Progress notes ({notes.length})</summary>
      <ol className="run-notes">
        {notes.length === 0 && <li className="faint">No notes.</li>}
        {notes.map((n, i) => <li key={i} className={`rn-${n.kind}`}>
          <time dateTime={n.at} title={fullTime(n.at)}>{elapsed(run.sent_at ?? run.created_at, n.at)} in</time><span>{n.text}</span></li>)}
      </ol>
    </details>
  );
}

function RuleSectionHead({ rule: r, also, version, meta }: { rule: ReportRule; also: boolean; version: number | null; meta?: RuleSummary }) {
  const [ico, cls, words] = resultOf(r, also, version);
  return <>
    <ReportRuleHead name={r.name} meta={meta} />
    <p className={`report-rule-status ${cls}`} data-testid="rule-status"><Ico name={ico} />{words}</p>
  </>;
}

/** A rule's section heading, as the Rules tab heads a rule: its name, where it looks, and its CTDL term. */
function ReportRuleHead({ name, meta }: { name: string; meta?: RuleSummary }) {
  const shown = (meta?.path_shown ?? meta?.ctdl_property?.replace(/>/g, " → ")) || "";
  const steps = shown.split(" → ");
  const leaf = steps.pop() ?? "";
  const where = meta?.kind === "property" ? [meta.parent_label ? `part of ${meta.parent_label}` : null, whereWord(meta.locator)].filter(Boolean)
    : meta ? [meta.subtitle] : [];
  return (
    <div className="rule-head report-rule-head">
      <h2>{name}</h2>
      {where.length > 0 && <span className="rh-sub">{where.map((w) => <span key={w}>{w}</span>)}</span>}
      {shown && <div className="rh-line"><span className="rh-path">{steps.length > 0 && <>{steps.join(" → ")} → </>}
        <a className="term" href={termUrl(meta?.ctdl_property ?? null) ?? undefined} target="_blank" rel="noopener noreferrer">{leaf}<Ico name="ext" /></a></span></div>}
    </div>
  );
}

function ValuesChanged({ catalog, rule, vc }: { catalog: string; rule: string; vc: NonNullable<ReportRule["values_changed"]> }) {
  const compare = vc.compare_url ?? (vc.base != null && vc.published != null
    ? href(catalog, "compare", null, { a: vc.base, b: vc.published, rule }) : null);
  return (
    <dl className="run-facts"><dt>Values changed</dt><dd data-testid="values-changed">
      {vc.text ?? `${fmt(vc.count)} of ${fmt(vc.of)} courses`}.{compare && vc.base != null && vc.published != null && <>{" "}
        <a href={compare}>Compare v{vc.base} and v{vc.published}</a></>}</dd></dl>
  );
}

const Fact = ({ label, text }: { label: string; text: string }) => <><dt>{label}</dt><dd>{text}</dd></>;

/** Page passages Claude left out of a value: the ✕ expansion's pieces, struck through (mockup 5). */
function LeftOut({ passages }: { passages: { text: string }[] }) {
  return (
    <div className="report-left-out" data-testid="left-out">
      <div className="faint">Claude left these lines on the page out of the value:</div>
      {passages.map((p, i) => (
        <div className="sel-piece" key={i}>
          <span className="sel-pol" title="Not part of the value">✕ not in answer</span>
          <blockquote className="sel-quote out">{p.text}</blockquote>
        </div>))}
    </div>
  );
}

/** "If yes, mark …": the answer in bold (a report resolved before pass 7, whose answers are sentences). */
function optionText(text: string): ReactNode {
  const m = /^(If [^,]+,)(.*)$/s.exec(text);
  return m ? <><b>{m[1]}</b>{m[2]}</> : text;
}

// --- pure helpers ---------------------------------------------------------------------------------------------------
/** Published, yet some rules to improve wait for a decision: the band is amber, not green. */
export const partialReport = (r: ResolvedReport) => r.ending === "published"
  && (r.to_do.length > 0 || r.rules.some((x) => x.outcome === "held"));

/** The band's sentence; an older partial report's says only what was published, so add what still waits. */
function bandLine(r: ResolvedReport): string {
  const o = (r.outcome ?? "").trim();
  if (!o || !partialReport(r) || /\b(needs?|wait)\b/.test(o)) return o;
  const held = r.rules.filter((x) => x.outcome === "held").map((x) => x.name), n = r.to_do.length;
  const need = n ? `${n} decision${n === 1 ? "" : "s"}` : "you";
  return held.length ? `${o} ${andList(held)} ${held.length === 1 ? "needs" : "need"} ${need} first.` : n ? `${o} ${need} still wait${n === 1 ? "s" : ""} for you.` : o;
}

/** What became of a rule, for the contents and its section: [icon, class, words]. */
function resultOf(r: ReportRule, also: boolean, version: number | null): [string, string, string] {
  const inV = version != null ? ` in v${version}` : "";
  if (also) return ["approved", "is-ok", `Also changed${inV}`];
  switch (r.outcome) {
    case "published": return ["approved", "is-ok", `Published${inV}`];
    case "held": return ["question", "is-held", "Needs input"];
    case "failed": return ["needs work", "is-bad", "Couldn't be fixed"];
    default: return ["in review", "is-same", "Not changed"];
  }
}

/** The rules of the contents: the rules to improve (held first), then the rules Claude also changed. */
function tocOf(report: ResolvedReport): (readonly [ReportRule, boolean])[] {
  return [...goalsInOrder(report).map((r) => [r, false] as const), ...report.also_changed.map((r) => [r, true] as const)];
}

function goalsInOrder(report: ResolvedReport): ReportRule[] {
  const order = (r: ReportRule) => ({ held: 0, failed: 1, published: 2 } as Record<string, number>)[r.outcome ?? ""] ?? 3;
  return [...report.rules].sort((a, b) => order(a) - order(b));
}

/** Decisions open as the CLI says, at most 3; the rest are folded. */
function openToDos(toDos: ReportToDo[]): boolean[] {
  let opened = 0;
  return toDos.map((t, i) => {
    const open = (t.open ?? i === 0) && opened < 3;
    if (open) opened++;
    return open;
  });
}

const toDoRule = (t: ReportToDo) => t.rule ?? t.options.find((o) => o.do)?.do?.rule ?? null;

/** Does a row's verdict already say what an answer marks? (Then the answer is done.) */
function hasMark(v: { verdict?: string | null; reasons?: string[] } | null | undefined, mark: string): boolean {
  if (!v?.verdict) return false;
  const nop = !!v.reasons?.includes("not_on_page");
  if (mark === "correct") return v.verdict === "correct";
  if (mark === "not_on_page") return v.verdict === "wrong" && nop;
  if (mark === "wrong") return v.verdict === "wrong" && !nop;
  return false;
}

/** The Rules tab's address for one row, pinned to the run's ruleset; `mark` opens it with ✕ pressed. */
export function rulesHref(catalog: string, rule: string, course: string, ext: string | null, mark = false): string {
  return href(catalog, "rules", rule, { row: course, by: "anyone", ext, mark: mark ? "wrong" : null });
}

/** "Credit Value", "Subject Webpage and In Catalog", "A, B and C". */
export const andList = (xs: string[]) => (xs.length < 2 ? xs.join("") : `${xs.slice(0, -1).join(", ")} and ${xs[xs.length - 1]}`);
const published = (r: AgentRun) => r.ruleset_after != null && r.ruleset_before != null && r.ruleset_after > r.ruleset_before;
/** The version a report's rows are pinned to: the one the run published, else the one it started from. */
export const pinnedVersion = (run: AgentRun) => (published(run) ? run.ruleset_after : run.ruleset_before);
const isRuleset = (f: { label: string }) => f.label === "Ruleset";
const sectionId = (rule: string) => `report-rule-${rule}`;
function scrollToSection(rule: string) {
  document.getElementById(sectionId(rule))?.scrollIntoView?.({ block: "start", behavior: "smooth" });
}
const valueText = (value: string | null | undefined, status?: string | null) =>
  value ? value : status === "absent" ? "Not on the page (rule's claim)" : "empty";
const domId = (run: string, rule: string, course: string) => `rc-${run}-${rule}-${course}`.replace(/[^A-Za-z0-9_-]/g, "_");
