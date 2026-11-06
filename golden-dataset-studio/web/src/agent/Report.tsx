// An AI run's report, rendered from `report.resolved.json` with the app's own components (one-rule-runs spec §1.4,
// §1.6, §2.3): the outcome band, the facts, the values Claude worked out, what you need to decide, one section per rule
// (the rules to improve, then each rule Claude also changed), progress notes folded, and a footer with Past AI runs,
// Revert vN, View the prompt and, once rows have new feedback, ✦ Run again. Every course is its Rules tab row card
// (RowCard), whose verdict and history are refetched when the report opens and whenever its window gets focus. ✓ and
// comments act here; ✕ and Open in Rules → open the row in a new browser tab, pinned to the run's ruleset (`ext`).
// No " · " in anything rendered here: one fact per row, one history item per line, sentences.
import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { api } from "../api/client";
import type { CatalogDetail, NewEvent } from "../api/types";
import { Tip } from "../evals/EvalsTab";
import type { RowX } from "../rules/api";
import { briefOf, newDraft, reportHistory, rowTarget, verdictEvent, type Draft, type HistItem } from "../rules/logic";
import { Expansion } from "../rules/parts";
import { RowCard } from "../rules/RowCard";
import { Ico } from "../shell/icons";
import { useReviewer } from "../shell/reviewer";
import { href } from "../shell/router";
import { fmt, toast } from "../shell/ui";
import { CATALOG_CHANGED, compareOf, agentApi, agentApi2, elapsed, endedIcon, endedLine, rowKey, type AgentRun, type HistEvent, type ReportRow, type ReportRowState,
  type ReportRows, type ReportRule, type ReportToDo, type ResolvedReport, type RunNote,
} from "./api";
import { openRunDialog } from "./RunDialog";
import "../rules/rules.css";
import "./agent.css";

const when = (iso: string) => new Date(iso).toLocaleString("en-US", { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
const clock = (iso: string) => new Date(iso).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
/** "Credit Value", "Subject Webpage and In Catalog", "A, B and C". */
export const andList = (xs: string[]) => (xs.length < 2 ? xs.join("") : `${xs.slice(0, -1).join(", ")} and ${xs[xs.length - 1]}`);
const published = (r: AgentRun) => r.ruleset_after != null && r.ruleset_before != null && r.ruleset_after > r.ruleset_before;
/** The version a report's rows are pinned to: the one the run published, else the one it started from. */
export const pinnedVersion = (run: AgentRun) => (published(run) ? run.ruleset_after : run.ruleset_before);

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
    const onFocus = () => load();
    const onVis = () => { if (document.visibilityState === "visible") load(); };
    window.addEventListener("focus", onFocus);
    document.addEventListener("visibilitychange", onVis);
    return () => { window.removeEventListener("focus", onFocus); document.removeEventListener("visibilitychange", onVis); };
  }, [runId, load]);
  return { data, reload: load, setData };
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

/** The Rules tab's address for one row, pinned to the run's ruleset; `mark` opens it with ✕ pressed. */
export function rulesHref(catalog: string, rule: string, course: string, ext: string | null, mark = false): string {
  return href(catalog, "rules", rule, { row: course, by: "anyone", ext, mark: mark ? "wrong" : null });
}

function toRow(r: ReportRow, st: ReportRowState | undefined, history: HistEvent[]): RowX {
  const inf = r.inferred && r.inferred.saves === "expected" ? r.inferred : null;
  const value = inf ? inf.value : r.value;
  return {
    key: rowKey(r.rule, r.course), occurrence_key: r.occurrence_key ?? st?.occurrence_key ?? null, course_key: r.course,
    page_stem: r.page_stem, url: r.url, page_title: r.title, context: r.title,
    value, status: inf ? (value ? "found" : "absent") : r.status,
    css_path: null, char_start: null, char_end: null, occurrence_css_path: null,
    state: st ? st.state : r.state ?? null, verdict: st ? st.verdict : r.verdict ?? null, reattached: !!st?.reattached,
    comments: history.filter((e) => e.type === "comment"),
    human_reviewed: st?.human_reviewed, engineer_checked: st?.engineer_checked, signal_count: 0, group: null,
  };
}

const verdictWord = (v: string | null | undefined) => (v === "correct" ? "Marked correct." : v === "wrong" ? "Marked wrong."
  : v === "not_on_page" ? "Marked not on the page." : "No verdict yet.");
/** "If yes, mark …": the answer in bold, as the mockups show it. */
function optionText(text: string): ReactNode {
  const m = /^(If [^,]+,)(.*)$/s.exec(text);
  return m ? <><b>{m[1]}</b>{m[2]}</> : text;
}

// --- the report --------------------------------------------------------------------------------------------------
export interface ReportProps {
  catalog: string; run: AgentRun; report: ResolvedReport; notes: RunNote[];
  /** the Watch panel shows Past AI runs in the footer; the runs panel has its own way back */
  pastRuns?: () => void;
}

export function Report({ catalog, run, report, notes, pastRuns }: ReportProps) {
  const me = useReviewer();
  const { data, reload, setData } = useReportRows(catalog, run.run_id);
  const ext = useExtraction(catalog, pinnedVersion(run), report.ruleset?.ext);
  const [drafts, setDrafts] = useState<Record<string, Draft>>({});
  const [showPrompt, setShowPrompt] = useState(false);
  const [askRevert, setAskRevert] = useState(false);
  const [revertedIn, setRevertedIn] = useState<number | null>(report.reverted_in ?? null);
  const [prompt, setPrompt] = useState<string | null>(null);
  const promptRef = useRef<HTMLElement>(null);
  const states = useMemo(() => new Map((data?.rows ?? []).map((s) => [rowKey(s.rule, s.course), s])), [data]);

  // saving from a row card: the event the Rules tab would post; the row shows it at once, then the rows refetch
  const post = async (base: ReportRowState, ev: NewEvent) => {
    const key = rowKey(base.rule, base.course);
    try {
      const r = await api.annotate(catalog, ev);
      const b: HistEvent = { ...briefOf(r.event as Parameters<typeof briefOf>[0]), after_run: true };
      const add = (s: ReportRowState): ReportRowState =>
        ({ ...s, history: [...s.history, b], ...(b.type === "verdict" && b.verdict ? { verdict: b, state: b.verdict } : {}) });
      setData((d) => {
        const all = d?.rows ?? [];
        const has = all.some((s) => rowKey(s.rule, s.course) === key);
        const rows = has ? all.map((s) => (rowKey(s.rule, s.course) === key ? add(s) : s)) : [...all, add(base)];
        return { annotations_as_of: null, new_feedback: 0, ...d, rows };
      });
      reload();
      return b;
    } catch (e) {
      toast(`Not saved: ${String(e instanceof Error ? e.message : e)}`);
      return null;
    }
  };

  const card = (rr: ReportRow, lead: HistItem[] = []): ReactNode => {
    const key = rowKey(rr.rule, rr.course);
    const st = states.get(key);
    const history = st?.history ?? rr.history ?? [];
    const row = toRow(rr, st, history);
    const base: ReportRowState = st ?? { rule: rr.rule, course: rr.course, state: row.state, verdict: row.verdict, history };
    const target = rowTarget("property", rr.rule, { occurrence_key: row.occurrence_key, page_stem: rr.page_stem });
    const lab = rr.legend ?? rr.rule_name ?? rr.rule;
    const inf = rr.inferred ?? null;
    const draft = drafts[key] ?? null;
    const setDraft = (d: Draft | null) => setDrafts((x) => { const y = { ...x }; if (d) y[key] = d; else delete y[key]; return y; });
    const wrongHref = rr.links?.wrong ?? rulesHref(catalog, rr.rule, rr.course, ext, true);
    const pick = async (v: "correct" | "wrong" | "comment") => {
      if (v === "wrong") { window.open(wrongHref, "_blank", "noopener"); return; }
      if (v === "comment") { setDraft(draft?.mode === "comment" ? null : newDraft("comment", row.verdict, row.state)); return; }
      // ✓ (spec §2.4): an inferred value the run didn't publish is saved as the expected value of the open ✕
      const ev: NewEvent = inf?.saves === "expected"
        ? { type: "verdict", author: me, target, verdict: "wrong", supersedes: inf.annotation,
            expected: { text: inf.value, css_path: null, char_start: null, char_end: null } }
        : verdictEvent(me, target, row.verdict, { verdict: "correct" });
      const b = await post(base, ev);
      if (b) toast(inf?.saves === "expected" ? `Saved as ${rr.course}'s expected ${lab}` : `Correct: ${rr.course}`);
    };
    const saveComment = async () => {
      if (!draft) return;
      const b = await post(base, verdictEvent(me, target, row.verdict, { draft }));
      if (b) { setDraft(null); toast(`Comment saved on ${rr.course}`); }
    };
    const before = rr.value_before ? [{ cls: "muted" as const, text: `In v${rr.value_before.version}: ${rr.value_before.value || "empty"}` }] : [];
    return (
      <div className="rows" key={key}>
        <RowCard row={row} kind="property" label={lab} on stacked review={false} lead={[...before, ...lead]}
          history={reportHistory(history)} draft={draft} onPick={(v) => void pick(v)}
          okTitle={inf ? `Correct (1): this is the right value. Saves it as ${rr.course}'s expected ${lab}` : "Correct (1)"}
          wrongTitle="Wrong: opens this row in the Rules tab, in a new browser tab, to select the right text"
          links={<>
            <a className="xbtn" href={href(catalog, "records", rr.course, { prop: lab, occ: row.occurrence_key })}
              title="Open this course in the Records tab">Open in Records →</a>{" "}
            <a className="xbtn" href={rr.links?.rules ?? rulesHref(catalog, rr.rule, rr.course, ext)} target="_blank" rel="noopener"
              title="Opens this row in the Rules tab in a new browser tab, at the ruleset the run published, with its page beside it">Open in Rules →</a>
          </>}
          below={rr.left_out?.length ? <LeftOut passages={rr.left_out} /> : null}
          expansion={draft ? <Expansion draft={draft} propertyRule onChange={setDraft} onSave={() => void saveComment()}
            onCancel={() => setDraft(null)} /> : null} />
      </div>
    );
  };

  // values Claude worked out: the first open, the rest folded; then decisions, open as the CLI says (at most 3)
  const inferred = report.inferred.map((inf, i) => {
    const v = inf.row.verdict;
    const why = v?.verdict === "wrong" && !v.expected?.text
      ? `${v.author} marked ${inf.course} wrong without selecting the right text. Claude worked out the value below from the notes and the page.`
      : "Claude worked out the value below from the notes and the page.";
    const lead = (inf.evidence ?? []).filter((e) => e.source?.kind === "page").map((e) => ({ cls: "muted" as const, text: `On the page: “${e.quote}”` }));
    const body = <><p>{why}</p>{card(inf.row, lead)}</>;
    return i === 0
      ? <div key={`inf${i}`}>{body}</div>
      : <details key={`inf${i}`} className="run-fold"><summary>{inf.course}: {inf.rule_name ?? inf.rule}</summary>{body}</details>;
  });
  let opened = 0;
  const toDos = report.to_do.map((t, i) => {
    const open = (t.open ?? i === 0) && opened < 3;
    if (open) opened++;
    const body = <ToDoBody t={t} card={card} catalog={catalog} ext={ext} />;
    return open
      ? <section key={`td${i}`} className="runs-sec" data-testid="to-do"><h3>{t.ask}</h3>{body}</section>
      : <details key={`td${i}`} className="runs-sec run-fold" data-testid="to-do"><summary>{t.ask}</summary>{body}</details>;
  });

  const pub = published(run);
  // the report's own pair (the CLI read this run's publishes), else the run record's
  const cmp = !pub ? null : report.ruleset?.compare ? { a: report.ruleset.compare.a, b: report.ruleset.compare.b } : compareOf(run);
  const newFeedback = data?.new_feedback ?? 0;
  const changed = [...report.rules, ...report.also_changed].map((r) => r.name);
  const revertV = revertedIn != null || report.reverted_in != null ? null : report.revert?.version ?? (pub ? run.ruleset_after : null);
  const revertText = revertV == null ? "" : report.revert?.text ?? `Revert v${revertV}? This publishes v${revertV + 1} with `
    + `${andList(changed)} back to how ${changed.length === 1 ? "it was" : "they were"} in v${run.ruleset_before}.`;
  // the confirm is the app's own dialog (the run button's `.ac.run-ask`), not the browser's
  const revert = async () => {
    if (revertV == null) return;
    setAskRevert(false);
    try {
      const r = await agentApi2.revert(catalog, revertV, me);
      toast(`Reverted: ruleset v${r.version} is published`);
      setRevertedIn(r.version);
      window.dispatchEvent(new Event(CATALOG_CHANGED));
    } catch (e) { toast(`Not reverted: ${String(e instanceof Error ? e.message : e)}`); }
  };
  const viewPrompt = () => {
    setShowPrompt(true);
    if (prompt === null) agentApi.prompt(catalog, run.run_id).then((p) => setPrompt(p.text), () => setPrompt("(the prompt wasn't kept)"));
    setTimeout(() => promptRef.current?.scrollIntoView?.({ block: "start" }), 0);
  };
  const facts = [...report.facts ?? [
    ...(report.rules.length ? [{ label: "Rules to improve", text: andList(report.rules.map((r) => r.name)) }] : []),
    ...(report.also_changed.length ? [{ label: "Also changed", text: andList(report.also_changed.map((r) => r.name)) }] : []),
  ]];
  if (!pub && run.ruleset_before != null && !facts.some((f) => f.label === "Ruleset")) {
    facts.push({ label: "Ruleset", text: `v${run.ruleset_before}, unchanged` });
  }
  const isRuleset = (f: { label: string }) => f.label === "Ruleset";

  const ruleSection = (r: ReportRule, also: boolean) => {
    const vc = r.values_changed;
    const compare = vc?.compare_url ?? (vc?.base != null && vc.published != null
      ? href(catalog, "compare", null, { a: vc.base, b: vc.published, rule: r.rule }) : null);
    const prose = also ? r.why : [r.now && `Now ${r.now}.`, r.why].filter(Boolean).join(" ");
    return (
      <section key={`${also ? "a" : "g"}-${r.rule}`} className="runs-sec" data-testid="rule-section">
        <h3>{also ? `Also changed: ${r.name}` : r.name}</h3>
        {vc && <dl className="run-facts"><dt>Values changed</dt><dd data-testid="values-changed">
          {vc.text ?? `${fmt(vc.count)} of ${fmt(vc.of)} courses`}.{compare && vc.base != null && vc.published != null && <>{" "}
            <a href={compare}>Compare v{vc.base} and v{vc.published}</a></>}</dd></dl>}
        {prose && <p>{prose}</p>}
        {r.rows.map((rr) => card(rr))}
      </section>
    );
  };

  return (
    <>
      <div className="runs-detail" data-testid="run-report">
        <div className={`run-done is-${run.state}`}>
          <Ico name={endedIcon(run)} />
          <span className="run-done-t">{report.outcome || endedLine(run)}</span>
          {cmp && <a className={`btn${newFeedback ? "" : " primary"}`} href={href(catalog, "compare", null, cmp)}
            title="What changed between the two rulesets, rule by rule">Compare v{cmp.a} → v{cmp.b}</a>}
        </div>
        <dl className="run-facts" data-testid="report-facts">
          {facts.filter((f) => !isRuleset(f)).map((f) => <Fact key={f.label} label={f.label} text={f.text} />)}
          <dt>Started</dt><dd>{when(run.created_at)} by {run.started_by}</dd>
          {run.ended_at && <><dt>Ran</dt><dd>{elapsed(run.sent_at ?? run.created_at, run.ended_at)}</dd></>}
          {facts.filter(isRuleset).map((f) => <Fact key={f.label} label={f.label} text={f.text} />)}
          {report.ending === "failed" && report.reason && <Fact label="Why" text={report.reason} />}
        </dl>
        {inferred.length > 0 && <section className="runs-sec" data-testid="inferred">
          <h3>{inferred.length === 1 ? "A value Claude worked out" : "Values Claude worked out"}</h3>{inferred}</section>}
        {toDos.length > 0 && (inferred.length > 0 || toDos.length > 1) && <section className="runs-sec"><h3>What you need to decide</h3></section>}
        {toDos}
        {report.rules.map((r) => ruleSection(r, false))}
        {report.also_changed.map((r) => ruleSection(r, true))}
        {report.notes && <details className="runs-sec run-fold"><summary>Claude's notes</summary>
          <p className="report-notes">{report.notes}</p></details>}
        <details className="runs-sec run-fold">
          <summary>Progress notes ({notes.length})</summary>
          <ol className="run-notes">
            {notes.length === 0 && <li className="faint">No notes.</li>}
            {notes.map((n, i) => <li key={i} className={`rn-${n.kind}`}><time dateTime={n.at}>{clock(n.at)}</time><span>{n.text}</span></li>)}
          </ol>
        </details>
        {showPrompt && <section className="runs-sec" ref={promptRef}><h3>The prompt Claude was given</h3>
          <pre className="prompt-pre runs-prompt">{prompt ?? "Loading…"}</pre></section>}
      </div>
      <div className="ac-foot" data-testid="report-foot">
        {pastRuns ? <button className="linkish" onClick={pastRuns}>Past AI runs</button> : <span />}
        <span className="report-foot-r">
          {newFeedback > 0 && <span className="faint" data-testid="new-feedback">{newFeedback === 1 ? "1 row has" : `${fmt(newFeedback)} rows have`} new
            feedback since this run.</span>}
          {revertedIn != null && <span className="faint" data-testid="reverted-in">Reverted in v{revertedIn}.</span>}
          {revertV != null && <button className="btn" onClick={() => setAskRevert(true)}
            title={`Publishes a new ruleset with every rule v${revertV} changed back to how it was`}>Revert v{revertV}</button>}
          <button className="btn" onClick={viewPrompt}>View the prompt</button>
          {newFeedback > 0 && <button className="btn primary" onClick={() => openRunDialog(run.scope.rules ?? report.rules.map((r) => r.rule))}>
            <Ico name="spark" />Run again</button>}
        </span>
      </div>
      {askRevert && revertV != null && (
        <div className="ac-back" onClick={() => setAskRevert(false)}>
          <div className="ac run-ask" role="dialog" aria-modal="true" aria-labelledby="revert-ask-h" data-testid="revert-ask"
            onClick={(e) => e.stopPropagation()}>
            <div className="ac-head"><h2 id="revert-ask-h">Revert v{revertV}?</h2>
              <button className="ac-x" aria-label="Close" onClick={() => setAskRevert(false)}>×</button></div>
            <div className="ac-body"><p>{revertText.replace(/^Revert v\d+\? /, "")}</p></div>
            <div className="ac-foot">
              <button className="btn" onClick={() => setAskRevert(false)}>Cancel</button>
              <button className="btn primary" onClick={() => void revert()} autoFocus>Revert v{revertV}</button>
            </div>
          </div>
        </div>
      )}
    </>
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

/** A decision: the rows it is about (each with who said what), the evidence (a quote, or a set of courses: the first
 * as a row card, the others as codes whose hover is the app's Tip), and the options as sentences. */
function ToDoBody({ t, card, catalog, ext }: { t: ReportToDo; card: (r: ReportRow) => ReactNode; catalog: string; ext: string | null }) {
  const shown = new Set(t.about.map((r) => rowKey(r.rule, r.course)));
  const said = (r: ReportRow) => {
    const v = r.verdict;
    if (!v || (v.verdict !== "correct" && v.verdict !== "wrong")) return null;
    return `${v.author} marked ${r.course} ${v.verdict}${v.note ? " and said why" : ""}:`;
  };
  return <>
    {t.about.map((r) => <div key={rowKey(r.rule, r.course)}>{said(r) && <p>{said(r)}</p>}{card(r)}</div>)}
    {t.evidence.map((e, i) => {
      if (e.kind === "quote") {
        const src = e.source;
        if (src?.kind === "note" && src.course && src.rule && shown.has(rowKey(src.rule, src.course))) return null;  // on the card
        const who = src?.kind === "page" ? `On ${src.course}'s page:` : src?.author ? `${src.author}${src.course ? `, on ${src.course}` : ""}:` : null;
        return <div key={i} className="report-quote">{who && <div className="faint">{who}</div>}
          <blockquote className="sel-quote">{e.quote}</blockquote></div>;
      }
      const first = e.rows[0];
      return (
        <div key={i}>
          <p>{fmt(e.count)} courses {e.label}{first ? `, like ${first.course}:` : "."}</p>
          {e.rows.map((r) => card(r))}
          {e.courses.length > 0 && (
            <p className="report-others">The other {fmt(e.courses.length)}:{" "}
              {e.courses.map((c, j) => (
                <span key={c.course}>{j > 0 && ", "}
                  <Tip width={320} tip={<><span className="hd">{c.course}{c.title ? `: ${c.title}` : ""}</span>{c.value || "Not on the page"}
                    <span className="ft">{verdictWord(c.verdict)}</span></>}>
                    <button className="linkish" onClick={() => window.open(rulesHref(catalog, e.rule, c.course, ext), "_blank", "noopener")}>{c.course}</button>
                  </Tip>
                </span>))}.
            </p>)}
        </div>);
    })}
    {t.options.map((o, i) => <p key={i} className="report-option">{optionText(o.text)}</p>)}
  </>;
}
