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
import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
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
  type ReportInferred, type ReportRow, type ReportRowState, type ReportRows, type ReportRule, type ReportToDo, type ResolvedReport, type RunNote, type ToDoOption,
} from "./api";
import { openRunDialog } from "./RunDialog";
import "../rules/rules.css";
import "./agent.css";

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

/** "If yes, mark …": the answer in bold (a report resolved before pass 7, whose answers are sentences). */
function optionText(text: string): ReactNode {
  const m = /^(If [^,]+,)(.*)$/s.exec(text);
  return m ? <><b>{m[1]}</b>{m[2]}</> : text;
}

/** Does a row's verdict already say what an answer marks? (Then the answer is done.) */
function hasMark(v: { verdict?: string | null; reasons?: string[] } | null | undefined, mark: string): boolean {
  if (!v?.verdict) return false;
  const nop = !!v.reasons?.includes("not_on_page");
  if (mark === "correct") return v.verdict === "correct";
  if (mark === "not_on_page") return v.verdict === "wrong" && nop;
  if (mark === "wrong") return v.verdict === "wrong" && !nop;
  return false;
}

/** A verdict posted from the report, and the one it replaced: Undo posts the replaced one again, superseding it. */
interface Posted { rule: string; course: string; target: NewEvent["target"]; id: string; prev: EventBrief | null }

/** The event that undoes a verdict posted from the report: the log is append-only (no retract), so it is a new
 * verdict that supersedes the mistaken one and restores the earlier verdict's verdict, expected value and note. */
export function undoEvent(author: string, p: Posted): NewEvent | null {
  if (!p.prev?.verdict) return null;
  return { type: "verdict", author, target: p.target, verdict: p.prev.verdict, supersedes: p.id,
           note: p.prev.note ?? null, expected: p.prev.expected ?? null, ...(p.prev.reasons?.length ? { reasons: p.prev.reasons } : {}) };
}

const valueText = (value: string | null | undefined, status?: string | null) =>
  value ? value : status === "absent" ? "Not on the page (rule's claim)" : "empty";
const domId = (run: string, rule: string, course: string) => `rc-${run}-${rule}-${course}`.replace(/[^A-Za-z0-9_-]/g, "_");

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
  const ruleMeta = useRuleMeta(catalog);
  const [drafts, setDrafts] = useState<Record<string, Draft>>({});
  const [showPrompt, setShowPrompt] = useState(false);
  const [askRevert, setAskRevert] = useState(false);
  const [revertedIn, setRevertedIn] = useState<number | null>(report.reverted_in ?? null);
  const [prompt, setPrompt] = useState<string | null>(null);
  // a decision's answer: the one waiting for its confirm, the one being posted, and what each posted (for Undo)
  const [asking, setAsking] = useState<{ t: number; o: number } | null>(null);
  const [busy, setBusy] = useState(false);
  const [posted, setPosted] = useState<Record<string, Posted[]>>({});
  const promptRef = useRef<HTMLElement>(null);
  const states = useMemo(() => new Map((data?.rows ?? []).map((s) => [rowKey(s.rule, s.course), s])), [data]);

  // saving from the report: the event the Rules tab would post; the row shows it at once, then the rows refetch
  const post = async (base: ReportRowState, ev: NewEvent, refetch = true): Promise<HistEvent | null> => {
    const key = rowKey(base.rule, base.course);
    try {
      const r = await api.annotate(catalog, ev);
      const stored = r.event as Parameters<typeof briefOf>[0] & { reasons?: string[] };
      const b: HistEvent = { ...briefOf(stored), ...(stored.reasons?.length ? { reasons: stored.reasons } : {}), after_run: true };
      const add = (s: ReportRowState): ReportRowState =>
        ({ ...s, history: [...s.history, b], ...(b.type === "verdict" && b.verdict ? { verdict: b, state: b.verdict } : {}) });
      setData((d) => {
        const all = d?.rows ?? [];
        const has = all.some((s) => rowKey(s.rule, s.course) === key);
        const rows = has ? all.map((s) => (rowKey(s.rule, s.course) === key ? add(s) : s)) : [...all, add(base)];
        return { annotations_as_of: null, new_feedback: 0, ...d, rows };
      });
      if (refetch) reload();
      return b;
    } catch (e) {
      toast(`Not saved: ${String(e instanceof Error ? e.message : e)}`);
      return null;
    }
  };

  /** Undo verdicts posted from the report: one superseding verdict per course, restoring what was there before. */
  const undo = async (done: Posted[], what: string) => {
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

  // every row card once per report (pass 7): a later mention links back to the card above
  const seen = new Set<string>();
  const shownAbove = (rr: ReportRow, sentence?: boolean) => {
    const go = () => document.getElementById(domId(run.run_id, rr.rule, rr.course))?.scrollIntoView?.({ block: "start", behavior: "smooth" });
    const link = <button className="linkish" onClick={go}>shown above</button>;
    return (
      <p key={`above-${rowKey(rr.rule, rr.course)}-${sentence ? "c" : "r"}`} className="report-above" data-testid="shown-above">
        {sentence && rr.comment ? <>Claude's comment is on {rr.course}'s row, {link}.</> : <>{rr.course}'s row is {link}.</>}
      </p>);
  };

  const card = (rr: ReportRow, o: { hist?: HistItem[]; intro?: string | null } = {}): ReactNode => {
    const key = rowKey(rr.rule, rr.course);
    if (seen.has(key)) return shownAbove(rr, true);
    seen.add(key);
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
    const saves = inf?.saves === "expected";
    const pick = async (v: "correct" | "wrong" | "comment") => {
      if (v === "wrong") { window.open(wrongHref, "_blank", "noopener"); return; }
      if (v === "comment") { setDraft(draft?.mode === "comment" ? null : newDraft("comment", row.verdict, row.state)); return; }
      if (!saves && row.verdict?.verdict === "correct" && row.state === "correct") {
        toast(`${rr.course}'s ${lab} is already marked correct`);  // a second ✓ would only repeat it
        return;
      }
      // ✓ (spec §2.4): an inferred value the run didn't publish is saved as the expected value of the open ✕
      const prev = row.verdict ?? null;
      const ev: NewEvent = saves
        ? { type: "verdict", author: me, target, verdict: "wrong", supersedes: inf!.annotation,
            expected: { text: inf!.value, css_path: null, char_start: null, char_end: null } }
        : verdictEvent(me, target, prev, { verdict: "correct" });
      const b = await post(base, ev);
      if (!b) return;
      const what = saves ? `Saved the value Claude worked out as ${rr.course}'s expected ${lab}` : `Marked ${rr.course}'s ${lab} correct`;
      const p: Posted = { rule: rr.rule, course: rr.course, target, id: b.annotation_id, prev: prev?.type === "verdict" ? prev : null };
      if (undoEvent(me, p)) toastAction(what, "Undo", () => void undo([p], `${rr.course}'s ${lab} is back to ${markWord(prev).toLowerCase()}`));
      else toast(what);
    };
    const saveComment = async () => {
      if (!draft) return;
      const b = await post(base, verdictEvent(me, target, row.verdict, { draft }));
      if (b) { setDraft(null); toast(`Comment saved on ${rr.course}'s ${lab}`); }
    };
    const before = rr.value_before ? [{ cls: "muted" as const, text: `In v${rr.value_before.version}: ${rr.value_before.value || "empty"}` }] : [];
    return (
      <div key={key} id={domId(run.run_id, rr.rule, rr.course)}>
        {o.intro && <p className="report-lead" data-testid="row-lead">{o.intro}</p>}
        <div className="rows"><RowCard row={row} kind="property" label={lab} on stacked review={false} lead={[...before, ...(o.hist ?? [])]}
          history={reportHistory(history)} draft={draft} onPick={(v) => void pick(v)}
          okTitle={saves ? `Mark ${rr.course}'s ${lab} correct: saves the value Claude worked out as its expected ${lab}`
            : `Mark ${rr.course}'s ${lab} correct`}
          wrongTitle={`Mark ${rr.course}'s ${lab} wrong: opens the row in the Rules tab, in a new browser tab, to select the right text`}
          talkTitle={`Comment on ${rr.course}'s ${lab}`}
          links={<>
            <a className="xbtn" href={href(catalog, "records", rr.course, { prop: lab, occ: row.occurrence_key })}
              title="Open this course in the Records tab">Open in Records →</a>{" "}
            <a className="xbtn" href={rr.links?.rules ?? rulesHref(catalog, rr.rule, rr.course, ext)} target="_blank" rel="noopener"
              title="Opens this row in the Rules tab in a new browser tab, at the ruleset the run published, with its page beside it">Open in Rules →</a>
          </>}
          below={rr.left_out?.length ? <LeftOut passages={rr.left_out} /> : null}
          expansion={draft ? <Expansion draft={draft} propertyRule onChange={setDraft} onSave={() => void saveComment()}
            onCancel={() => setDraft(null)} /> : null} /></div>
      </div>
    );
  };

  // --- a decision's answers --------------------------------------------------------------------------------------
  /** A course's verdict now: from the refetched rows, else as the run ended. */
  const nowOf = (c: ReportCourse, rule: string): { verdict: EventBrief | null; occurrence_key: string | null } => {
    const st = states.get(rowKey(rule, c.course));
    return { verdict: st ? st.verdict : c.current ?? null, occurrence_key: st?.occurrence_key ?? c.occurrence_key ?? null };
  };
  const isDone = (o: ToDoOption) => !!o.do?.event && o.do.courses.length > 0
    && o.do.courses.every((c) => hasMark(nowOf(c, o.do!.rule).verdict, o.do!.mark));
  const doWords = (o: ToDoOption) => {
    const d = o.do!;
    return `Mark ${d.count === 1 ? d.courses[0]?.course : `${fmt(d.count)} courses`} ${d.words}`;
  };
  const answer = async (ti: number, oi: number) => {
    const o = report.to_do[ti].options[oi];
    const d = o.do;
    setAsking(null);
    if (!d?.event) return;
    setBusy(true);
    const done: Posted[] = [];
    for (const c of d.courses) {
      const now = nowOf(c, d.rule);
      const target = rowTarget("property", d.rule, { occurrence_key: now.occurrence_key, page_stem: c.page_stem ?? "" });
      const prev = now.verdict?.type === "verdict" ? now.verdict : null;
      if (hasMark(prev, d.mark)) continue;  // already so: nothing to post
      const ev: NewEvent = { type: "verdict", author: me, target, verdict: d.event.verdict, supersedes: prev?.annotation_id ?? null,
                             ...(d.event.reasons ? { reasons: d.event.reasons } : {}) };
      const st = states.get(rowKey(d.rule, c.course));
      const b = await post(st ?? { rule: d.rule, course: c.course, state: c.state ?? null, verdict: prev, history: [] }, ev, false);
      if (!b) break;
      done.push({ rule: d.rule, course: c.course, target, id: b.annotation_id, prev });
    }
    setBusy(false);
    reload();
    if (!done.length) return;
    const key = `${ti}:${oi}`;
    setPosted((x) => ({ ...x, [key]: done }));
    const what = done.length === 1 ? `${done[0].course} marked ${d.words}` : `${fmt(done.length)} courses marked ${d.words}`;
    toastAction(`Done: ${what}`, "Undo", () => { setPosted((x) => { const y = { ...x }; delete y[key]; return y; });
      void undo(done, `${done.length === 1 ? done[0].course : `${fmt(done.length)} courses`} back to their earlier marks`); });
  };

  const options = (t: ReportToDo, ti: number): ReactNode => {
    if (!t.options.length) return null;
    if (!t.options.some((o) => o.do?.event || o.button)) {  // a report resolved before pass 7: the answers as sentences
      return t.options.map((o, i) => <p key={i} className="report-option">{optionText(o.text)}</p>);
    }
    const doneAt = t.options.findIndex(isDone);
    if (doneAt >= 0) {
      const o = t.options[doneAt];
      const mine = posted[`${ti}:${doneAt}`];
      const again = o.then?.run_again?.map((r) => r.rule) ?? [];
      return (
        <div className="report-options" data-testid="answer-done">
          <p className="report-option"><b>Done:</b> {o.done ?? doWords(o)}.{mine && <>{" "}
            <button className="linkish" disabled={busy} onClick={() => { setPosted((x) => { const y = { ...x }; delete y[`${ti}:${doneAt}`]; return y; });
              void undo(mine, `${mine.length === 1 ? mine[0].course : `${fmt(mine.length)} courses`} back to their earlier marks`); }}>Undo</button></>}
          </p>
          {again.length > 0 && <p className="report-option">{o.then?.text}{" "}
            <button className="btn primary" onClick={() => openRunDialog(again)}><Ico name="spark" />Run again</button></p>}
        </div>);
    }
    return (
      <div className="report-options" data-testid="answers">
        {t.options.map((o, oi) => {
          const extra = [o.effect, ...(o.no_rule_yet ?? []), o.then?.text].filter(Boolean).join(" ");
          return (
            <div key={oi} className="report-option">
              {o.do?.event
                ? <button className="btn" disabled={busy} onClick={() => setAsking({ t: ti, o: oi })}
                    title={`${doWords(o)} for ${o.do.rule_name ?? o.do.rule}. You confirm first, and can undo it.`}>{o.button ?? doWords(o)}</button>
                : o.link
                  ? <a className="btn" href={o.link} target="_blank" rel="noopener" title="Opens the rows in the Rules tab, in a new browser tab">{o.button ?? o.answer}</a>
                  : <span><b>{o.button ?? o.answer}</b></span>}
              {extra && <span className="faint">{extra}</span>}
            </div>);
        })}
      </div>);
  };

  /** The rest of a set of courses: a table, one row per course, folded when long. */
  const courseTable = (rule: string, courses: ReportCourse[], lead: string) => {
    const table = (
      <table className="evx-wrong-t report-courses" data-testid="course-table">
        <thead><tr><th>Course</th><th>Title</th><th>Value</th><th>Mark</th><th /></tr></thead>
        <tbody>{courses.map((c) => {
          const v = nowOf(c, c.rule ?? rule).verdict;
          return (
            <tr key={c.course}>
              <td>{c.course}</td><td>{c.title ?? ""}</td><td className="report-val">{valueText(c.value, c.status)}</td>
              <td>{v ? markWord(v) : c.verdict === "correct" ? "Correct" : c.verdict === "wrong" ? "Wrong" : "Not reviewed"}</td>
              <td><a className="xbtn" href={c.links?.rules ?? rulesHref(catalog, c.rule ?? rule, c.course, ext)} target="_blank" rel="noopener"
                title={`Opens ${c.course}'s row in the Rules tab, in a new browser tab`}>Open in Rules →</a></td>
            </tr>);
        })}</tbody>
      </table>);
    return courses.length > 5
      ? <details className="run-fold" key={`t-${rule}`}><summary>{lead.replace(/:$/, "")}</summary>{table}</details>
      : <div key={`t-${rule}`}><p className="report-lead">{lead}</p>{table}</div>;
  };

  /** A decision: what to decide and why, the answers, then the evidence (pass 7). */
  const toDoBody = (t: ReportToDo, ti: number): ReactNode => {
    const shown = new Set(t.about.map((r) => rowKey(r.rule, r.course)));
    const intro = (r: ReportRow & { lead?: string | null }) => {
      if (r.lead) return r.lead;
      const v = states.get(rowKey(r.rule, r.course))?.verdict ?? r.verdict;
      return v && (v.verdict === "correct" || v.verdict === "wrong") ? `Here is the row ${v.author} marked ${v.verdict}:` : "Here is the row this question is about:";
    };
    const optionEffects = t.options.some((o) => o.effect);
    return <>
      {t.why && <p className="report-why" data-testid="to-do-why">{t.why}</p>}
      {options(t, ti)}
      {!optionEffects && (t.effect ?? []).length > 0 && <p className="faint">{(t.effect ?? []).map((e) => e.text).join(" ")}</p>}
      {t.about.map((r) => <div key={`ab-${rowKey(r.rule, r.course)}`}>{card(r, { intro: intro(r) })}</div>)}
      {t.evidence.map((e, i) => {
        if (e.kind === "quote") {
          const src = e.source;
          if (src?.kind === "note" && src.course && src.rule && shown.has(rowKey(src.rule, src.course))) return null;  // on the card
          const who = src?.kind === "page" ? `On ${src.course}'s page:` : src?.author ? `${src.author}'s note${src.course ? ` on ${src.course}` : ""}:` : null;
          return <div key={i} className="report-quote">{who && <div className="faint">{who}</div>}
            <blockquote className="sel-quote">{e.quote}</blockquote></div>;
        }
        const first = e.rows[0];
        return (
          <div key={i}>
            {first && card(first, { intro: first.lead ?? (e.count > 1 ? `Here is one of the ${fmt(e.count)} courses ${e.label}:` : `Here is the course ${e.label}:`) })}
            {e.courses.length > 0 && courseTable(e.rule, e.courses, e.others_lead
              ?? `The other ${fmt(e.courses.length)} ${e.courses.length === 1 ? "course" : "courses"} ${e.label}:`)}
          </div>);
      })}
    </>;
  };

  // values Claude worked out and decisions, each kept with its rule: the first open, the rest folded; decisions open as
  // the CLI says (at most 3)
  const inferredEl = (inf: ReportInferred, first: boolean, other = false) => {
    const v = inf.row.verdict;
    const why = v?.verdict === "wrong" && !v.expected?.text
      ? `${v.author} marked ${inf.course} wrong without selecting the right text. Claude worked out the value below from the notes and the page.`
      : "Claude worked out the value below from the notes and the page.";
    const hist = (inf.evidence ?? []).filter((e) => e.source?.kind === "page").map((e) => ({ cls: "muted" as const, text: `On the page: “${e.quote}”` }));
    const body = <><p>{why}</p>{card(inf.row, { hist })}</>;
    const key = `inf-${inf.rule}-${inf.course}`;
    const label = `${other ? `${inf.rule_name ?? inf.rule}: a` : "A"} value Claude worked out for ${inf.row.title ?? inf.course}`;
    return first
      ? <div key={key} className="report-sub" data-testid="inferred"><h3>{label}</h3>{body}</div>
      : <details key={key} className="report-sub run-fold" data-testid="inferred"><summary>{label}</summary>{body}</details>;
  };
  let opened = 0;
  const toDoOpen = report.to_do.map((t, i) => {
    const open = (t.open ?? i === 0) && opened < 3;
    if (open) opened++;
    return open;
  });
  const toDoEl = (t: ReportToDo, i: number) => {
    const body = toDoBody(t, i);
    return toDoOpen[i]
      ? <div key={`td${i}`} className="report-sub" data-testid="to-do"><h3>{t.ask}</h3>{body}</div>
      : <details key={`td${i}`} className="report-sub run-fold" data-testid="to-do"><summary>{t.ask}</summary>{body}</details>;
  };

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

  const version = run.ruleset_after;
  const ruleIds = new Set([...report.rules, ...report.also_changed].map((r) => r.rule));
  const toDoRule = (t: ReportToDo) => t.rule ?? t.options.find((o) => o.do)?.do?.rule ?? null;
  const ruleSection = (r: ReportRule, also: boolean) => {
    const vc = r.values_changed;
    const compare = vc?.compare_url ?? (vc?.base != null && vc.published != null
      ? href(catalog, "compare", null, { a: vc.base, b: vc.published, rule: r.rule }) : null);
    const prose = also ? r.why : [r.now && `Now ${r.now}.`, r.why].filter(Boolean).join(" ");
    const [ico, cls, words] = resultOf(r, also, version);
    const tds = report.to_do.map((t, i) => [t, i] as const).filter(([t]) => toDoRule(t) === r.rule);
    const infs = report.inferred.filter((x) => x.rule === r.rule);
    return (
      <section key={`${also ? "a" : "g"}-${r.rule}`} id={sectionId(r.rule)} className="runs-sec report-rule" data-testid="rule-section">
        <ReportRuleHead name={r.name} meta={ruleMeta.get(r.rule)} />
        <p className={`report-rule-status ${cls}`} data-testid="rule-status"><Ico name={ico} />{words}</p>
        {tds.map(([t, i]) => toDoEl(t, i))}
        {infs.map((x, i) => inferredEl(x, i === 0))}
        {vc && <dl className="run-facts"><dt>Values changed</dt><dd data-testid="values-changed">
          {vc.text ?? `${fmt(vc.count)} of ${fmt(vc.of)} courses`}.{compare && vc.base != null && vc.published != null && <>{" "}
            <a href={compare}>Compare v{vc.base} and v{vc.published}</a></>}</dd></dl>}
        {prose && <p>{prose}</p>}
        {r.rows.map((rr) => card(rr))}
      </section>
    );
  };
  // decisions and values on no rule of the report keep a section of their own
  const otherToDos = report.to_do.map((t, i) => [t, i] as const).filter(([t]) => !ruleIds.has(toDoRule(t) ?? ""));
  const otherInf = report.inferred.filter((x) => !ruleIds.has(x.rule));
  const order = (r: ReportRule) => ({ held: 0, failed: 1, published: 2 } as Record<string, number>)[r.outcome ?? ""] ?? 3;
  const goals = [...report.rules].sort((a, b) => order(a) - order(b));
  const toc = [...goals.map((r) => [r, false] as const), ...report.also_changed.map((r) => [r, true] as const)];

  const ask = asking ? report.to_do[asking.t]?.options[asking.o] : null;
  const askD = ask?.do ?? null;
  const toPost = askD ? askD.courses.filter((c) => !hasMark(nowOf(c, askD.rule).verdict, askD.mark)) : [];

  return (
    <>
      <div className="runs-detail" data-testid="run-report">
        <div className={`run-done is-${partialReport(report) ? "partial" : run.state}`}>
          <Ico name={partialReport(report) ? "question" : endedIcon(run)} />
          <span className="run-done-t">{bandLine(report) || endedLine(run)}</span>
          {cmp && <a className={`btn${newFeedback ? "" : " primary"}`} href={href(catalog, "compare", null, cmp)}
            title="What changed between the two rulesets, rule by rule">Compare v{cmp.a} → v{cmp.b}</a>}
        </div>
        {toc.length > 1 && <nav className="report-toc" data-testid="report-toc" aria-label="Rules in this report">
          <ul>{toc.map(([r, also]) => {
            const [ico, cls, words] = resultOf(r, also, version);
            return (
              <li key={`${also ? "a" : "g"}-${r.rule}`} className={cls}>
                <button className="linkish" onClick={() => scrollToSection(r.rule)} title={`Scroll to ${r.name}`}>
                  <Ico name={ico} /><b>{r.name}</b> <span>{words}</span></button>
              </li>);
          })}</ul></nav>}
        <dl className="run-facts" data-testid="report-facts">
          {facts.filter((f) => !isRuleset(f) && !(toc.length > 1 && (f.label === "Rules to improve" || f.label === "Also changed")))
            .map((f) => <Fact key={f.label} label={f.label} text={f.text} />)}
          <dt>Started</dt><dd><When at={run.created_at} /> by {run.started_by}</dd>
          {run.ended_at && <><dt>Ran</dt><dd>{elapsed(run.sent_at ?? run.created_at, run.ended_at)}</dd></>}
          {facts.filter(isRuleset).map((f) => <Fact key={f.label} label={f.label} text={f.text} />)}
          {report.ending === "failed" && report.reason && <Fact label="Why" text={report.reason} />}
        </dl>
        {(otherToDos.length > 0 || otherInf.length > 0) && <section className="runs-sec">
          {otherToDos.map(([t, i]) => toDoEl(t, i))}
          {otherInf.map((x, i) => inferredEl(x, i === 0, true))}</section>}
        {goals.map((r) => ruleSection(r, false))}
        {report.also_changed.map((r) => ruleSection(r, true))}
        {report.notes && <details className="runs-sec run-fold"><summary>Claude's notes</summary>
          <p className="report-notes">{report.notes}</p></details>}
        <details className="runs-sec run-fold">
          <summary>Progress notes ({notes.length})</summary>
          <ol className="run-notes">
            {notes.length === 0 && <li className="faint">No notes.</li>}
            {notes.map((n, i) => <li key={i} className={`rn-${n.kind}`}>
              <time dateTime={n.at} title={fullTime(n.at)}>{elapsed(run.sent_at ?? run.created_at, n.at)} in</time><span>{n.text}</span></li>)}
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
      {ask && askD && asking && (
        <div className="ac-back" onClick={() => setAsking(null)}>
          <div className="ac run-ask" role="dialog" aria-modal="true" aria-labelledby="answer-ask-h" data-testid="answer-ask"
            onClick={(e) => e.stopPropagation()}>
            <div className="ac-head"><h2 id="answer-ask-h">{doWords(ask)}?</h2>
              <button className="ac-x" aria-label="Close" onClick={() => setAsking(null)}>×</button></div>
            <div className="ac-body">
              <p>{toPost.length === 0 ? `Every course is already marked ${askD.words}. Nothing will be posted.`
                : `This records ${toPost.length === 1 ? "one verdict" : `${fmt(toPost.length)} verdicts`} on ${askD.rule_name ?? askD.rule}, `
                  + `one per course, as ${me}. Each replaces the course's current mark. You can undo it afterwards.`}</p>
              {toPost.length > 0 && <div className="report-ask-list"><table className="evx-wrong-t" data-testid="answer-ask-courses">
                <thead><tr><th>Course</th><th>Title</th><th>Now</th><th>After</th></tr></thead>
                <tbody>{toPost.map((c) => (
                  <tr key={c.course}><td>{c.course}</td><td>{c.title ?? ""}</td><td>{markWord(nowOf(c, askD.rule).verdict)}</td>
                    <td>{markWord({ verdict: askD.event!.verdict, reasons: askD.event!.reasons })}</td></tr>))}</tbody>
              </table></div>}
              {(ask.then?.text || ask.no_rule_yet?.length) && <p className="run-note">{[...(ask.no_rule_yet ?? []), ask.then?.text].filter(Boolean).join(" ")}</p>}
            </div>
            <div className="ac-foot">
              <button className="btn" onClick={() => setAsking(null)}>Cancel</button>
              <button className="btn primary" disabled={!toPost.length} onClick={() => void answer(asking.t, asking.o)} autoFocus>{doWords(ask)}</button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}

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
const sectionId = (rule: string) => `report-rule-${rule}`;
function scrollToSection(rule: string) {
  document.getElementById(sectionId(rule))?.scrollIntoView?.({ block: "start", behavior: "smooth" });
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
