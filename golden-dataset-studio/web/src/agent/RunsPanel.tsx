// AI runs: the queue (the runs working now and the runs in line, on every catalog: one-rule-runs §1.7), then every
// run of Claude on this catalog, newest first; one run's report (rendered from `report.resolved.json`, or an older run's
// Markdown `summary.md`), its progress notes, and the exact prompt it was given. Read-only. Opened from the footer, the
// bottom of the rule list, the run bar (See the queue, Read the report), and a rule's AI status (`rule`: that rule's
// runs, spec §1.5).
import { useEffect, useRef, useState } from "react";
import { Markdown } from "../prompt/markdown";
import "../prompt/prompt.css";
import { Ico } from "../shell/icons";
import { useReviewer } from "../shell/reviewer";
import { CLASS_NAME, href, parseRoute, type ClassSlug } from "../shell/router";
import { compareOf, agentApi, agentApi2, andNames, elapsed, LIVE, ordinal, scopeWords, type AgentRun, type Queue, type QueueRun, type RunDetail,
} from "./api";
import { apiClass, classOfRule, inClass, noteRunClass } from "../shell/klass";
import { Report } from "./Report";
import { classPrefix, useAgent } from "./state";
import { openRunDialog } from "./RunDialog";
import "./agent.css";

interface RunsPanelProps { catalog: string; initial: string | null; rule?: string | null; ruleName?: string | null; onClose: () => void }
interface RunsData { runs: AgentRun[] | null; error: string | null; queue: Queue | null; busy: boolean }

export function RunsPanel({ catalog, initial, rule = null, ruleName = null, onClose }: RunsPanelProps) {
  const [open, setOpen] = useState<string | null>(initial);
  const [only, setOnly] = useState<string | null>(rule);
  const data = useRunsData(catalog, only);
  useCloseTriggers(onClose);
  return (
    <div className="ac-back" onClick={onClose}>
      <aside className="run-watch runs-panel" role="dialog" aria-modal="true" aria-labelledby="runs-h" onClick={(e) => e.stopPropagation()}>
        <RunsHead title={panelTitle(only, ruleName, data.busy)} open={open} onBack={() => setOpen(null)} onClose={onClose} />
        {open ? <RunDetailView catalog={catalog} runId={open} />
          : <RunsBody only={only} ruleName={ruleName} data={data} onOpen={setOpen} onEvery={() => setOnly(null)} onClose={onClose} />}
      </aside>
    </div>
  );
}

function panelTitle(only: string | null, ruleName: string | null, busy: boolean): string {
  return only ? `AI runs on ${ruleName ?? only}` : busy ? "AI runs" : "Past AI runs";
}

function useRunsData(catalog: string, only: string | null): RunsData {
  const { runs, error } = useRunHistory(catalog, only);
  const queue = useQueue(only);
  const busy = !!queue && (queue.working.length > 0 || queue.waiting.length > 0);
  return { runs, error, queue, busy };
}

function useRunHistory(catalog: string, only: string | null): { runs: AgentRun[] | null; error: string | null } {
  const { classes } = useAgent();
  const [runs, setRuns] = useState<AgentRun[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    let live = true;
    setRuns(null);
    fetchHistory(catalog, only, classes).then((r) => { if (live) setRuns(r); }, (e) => { if (live) setError(String(e.message ?? e)); });
    return () => { live = false; };
  }, [catalog, only, classes.join(",")]);  // eslint-disable-line react-hooks/exhaustive-deps
  return { runs, error };
}

/** With All classes: every class's runs, each tagged with its class, newest first. */
function fetchHistory(catalog: string, only: string | null, classes: ClassSlug[]): Promise<AgentRun[]> {
  const each = classes.length > 1 && !only ? classes : [only ? classOfRule(only) ?? apiClass() : apiClass()];
  return Promise.all(each.map((cls) => inClass(cls, () => (only ? agentApi2.ofRule(catalog, only) : agentApi.history(catalog)))
    .then((rs) => (each.length > 1 ? rs.map((r) => { noteRunClass(r.run_id, cls); return { ...r, cls }; }) : rs))))
    .then((xs) => xs.flat().sort((a, b) => b.created_at.localeCompare(a.created_at)));
}

function useQueue(only: string | null): Queue | null {
  const [queue, setQueue] = useState<Queue | null>(null);
  useEffect(() => {
    let live = true;
    if (!only) agentApi2.queue().then((q) => { if (live) setQueue(q); }, () => {});
    return () => { live = false; };
  }, [only]);
  return queue;
}

function useCloseTriggers(onClose: () => void): void {
  useCloseOnEscape(onClose);
  useCloseOnTabChange(onClose);
}

function useCloseOnEscape(onClose: () => void): void {
  useEffect(() => {
    const on = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", on);
    return () => window.removeEventListener("keydown", on);
  }, [onClose]);
}

/** A link in a report to another tab (Compare vN → vM, Values changed's Compare): show that tab, not this drawer.
 * Subscribed once: App re-renders on the same hashchange (a discrete event, flushed during the dispatch), and a
 * listener re-subscribed for a new onClose would be removed before the browser calls it. */
function useCloseOnTabChange(onClose: () => void): void {
  const openedOn = useRef(parseRoute(location.hash).tab);
  const close = useRef(onClose);
  close.current = onClose;
  useEffect(() => {
    const on = () => { if (parseRoute(location.hash).tab !== openedOn.current) close.current(); };
    window.addEventListener("hashchange", on);
    return () => window.removeEventListener("hashchange", on);
  }, []);
}

function RunsHead({ title, open, onBack, onClose }: { title: string; open: string | null; onBack: () => void; onClose: () => void }) {
  return (
    <div className="ac-head">
      <h2 id="runs-h">{open ? <button className="linkish runs-back" onClick={onBack}>← {title}</button> : title}</h2>
      <button className="ac-x" aria-label="Close" onClick={onClose}>×</button>
    </div>
  );
}

function RunsBody({ only, ruleName, data: { runs, error, queue, busy }, onOpen, onEvery, onClose }: {
  only: string | null; ruleName: string | null; data: RunsData; onOpen: (id: string) => void; onEvery: () => void; onClose: () => void;
}) {
  const me = useReviewer();
  if (error) return <p className="prompt-error runs-pad">{error}</p>;
  return <>
    <div className="runs-detail" data-testid="runs-list">
      {only && <ImproveRule only={only} ruleName={ruleName} onClose={onClose} />}
      {busy && <QueueSections q={queue!} me={me} />}
      <PastRuns runs={runs} busy={busy} only={only} onOpen={onOpen} />
    </div>
    {only && <div className="ac-foot"><button className="linkish" onClick={onEvery}>Every AI run on this catalog</button></div>}
  </>;
}

function ImproveRule({ only, ruleName, onClose }: { only: string; ruleName: string | null; onClose: () => void }) {
  return (
    <section className="runs-sec runs-head-acts">
      <button className="btn" onClick={() => { onClose(); openRunDialog([only]); }}><Ico name="spark" />Improve {ruleName ?? only}</button>
    </section>
  );
}

function PastRuns({ runs, busy, only, onOpen }: { runs: AgentRun[] | null; busy: boolean; only: string | null; onOpen: (id: string) => void }) {
  const { classes } = useAgent();
  const shown = (runs ?? []).filter((r) => !busy || !LIVE.includes(r.state));
  return (
    <section className={busy ? "runs-sec" : "runs-sec runs-plain"}>
      {busy && <h3>Past AI runs</h3>}
      {!runs ? <p className="faint">Loading…</p>
        : shown.length === 0
          ? <p className="faint">{only ? "No AI run has worked on this rule yet." : "No runs yet on this catalog."}</p>
        : <ol className="runs-list">{shown.map((r) => <RunItem key={r.run_id} run={r} classes={classes} onOpen={onOpen} />)}</ol>}
    </section>
  );
}

function RunItem({ run: r, classes, onOpen }: { run: AgentRun; classes: ClassSlug[]; onOpen: (id: string) => void }) {
  return (
    <li>
      <button className="runs-item" onClick={() => onOpen(r.run_id)} data-run={r.run_id}>
        <span className={`runs-state s-${r.state}`}>{STATE[r.state] ?? r.state}</span>
        <span className="runs-what">{classPrefix(r, classes)}{r.outcome ?? (r.scope.kind === "rules" && r.rule_names
          ? `Improving ${andNames((r.scope.rules ?? []).map((id) => r.rule_names?.[id] ?? id))}` : scopeWords(r.scope))}</span>
        <span className="runs-meta faint">{runMeta(r)}</span>
      </button>
    </li>
  );
}

/** "Working now: 2 of 2 places", "Waiting", and where the estimates come from (spec §1.7). */
export function QueueSections({ q, me }: { q: Queue; me: string }) {
  return <>
    <WorkingSection q={q} me={me} />
    {q.waiting.length > 0 && <WaitingSection q={q} me={me} />}
  </>;
}

function WorkingSection({ q, me }: { q: Queue; me: string }) {
  return (
    <section className="runs-sec" data-testid="queue-working">
      <h3>Working now: {q.working.length} of {q.cap} place{q.cap === 1 ? "" : "s"}</h3>
      {q.working.length === 0 ? <p className="faint">No run is working.</p> : (
        <ol className="runs-list">{q.working.map((w) => (
          <li key={w.run}><div className="runs-item">
            <span className="runs-state s-running">Working</span>
            <span className="runs-what">{queueWhat(w, me)}</span>
            <span className="runs-meta faint">{w.started_by}. Started {w.minutes_so_far ?? 0} min ago{w.left_min != null ? `, about ${w.left_min} min left` : ""}</span>
          </div></li>))}
        </ol>)}
    </section>
  );
}

function WaitingSection({ q, me }: { q: Queue; me: string }) {
  return (
    <section className="runs-sec" data-testid="queue-waiting">
      <h3>Waiting</h3>
      <ol className="runs-list">{q.waiting.map((w) => (
        <li key={w.run}><div className="runs-item">
          <span className="runs-state s-waiting">{ordinal(w.place ?? 1)} in line</span>
          <span className="runs-what">{queueWhat(w, me)}</span>
          <span className="runs-meta faint">{w.started_by}. Starts in about {Math.max(1, w.start_in_min ?? 1)} min</span>
        </div></li>))}
      </ol>
      {q.note && <p className="faint">{q.note}</p>}
    </section>
  );
}

function RunDetailView({ catalog, runId }: { catalog: string; runId: string }) {
  const { d, error } = useRunDetail(catalog, runId);
  if (error) return <p className="prompt-error runs-pad">{error}</p>;
  if (!d) return <p className="faint runs-pad">Loading…</p>;
  if (d.report) return <Report catalog={catalog} run={d.run} report={d.report} notes={d.notes} />;
  return (
    <div className="runs-detail" data-testid="run-detail">
      <DetailFacts catalog={catalog} run={d.run} />
      <DetailSummary run={d.run} summary={d.summary} />
      <DetailNotes notes={d.notes} />
      <PromptToggle catalog={catalog} runId={runId} />
    </div>
  );
}

function useRunDetail(catalog: string, runId: string): { d: RunDetail | null; error: string | null } {
  const [d, setD] = useState<RunDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    let live = true;
    agentApi2.detail(catalog, runId).then((x) => { if (live) setD(x); }, (e) => { if (live) setError(String(e.message ?? e)); });
    return () => { live = false; };
  }, [catalog, runId]);
  return { d, error };
}

function DetailFacts({ catalog, run }: { catalog: string; run: AgentRun }) {
  const grew = compareOf(run);
  return (
    <dl className="run-facts">
      <dt>Outcome</dt><dd><b>{STATE[run.state] ?? run.state}</b>{run.outcome ? `: ${run.outcome}` : ""}</dd>
      <dt>Asked to</dt><dd>{scopeWords(run.scope)}{run.scope.rules?.length ? <span className="mono faint"> ({run.scope.rules.join(", ")})</span> : null}</dd>
      <dt>Started</dt><dd>{runMeta(run)}</dd>
      {grew && <><dt>Published</dt><dd>ruleset v{run.ruleset_after}.{" "}
        <a href={href(catalog, "compare", null, grew)}>Compare v{grew.a} → v{grew.b}</a></dd></>}
      <dt>Run id</dt><dd className="mono faint">{run.run_id}</dd>
    </dl>
  );
}

function DetailSummary({ run, summary }: { run: AgentRun; summary: string | null }) {
  return (
    <section className="runs-sec">
      <h3>Claude's report</h3>
      {summary ? <div className="prompt-md runs-report"><Markdown text={summary} /></div>
        : <p className="faint">No report was saved with this run{LIVE.includes(run.state) ? " yet" : ""}. Runs started before
          reports were kept have theirs only in the golden-rules chat on the Remote AI rule generator.</p>}
    </section>
  );
}

function DetailNotes({ notes }: { notes: RunDetail["notes"] }) {
  return (
    <section className="runs-sec">
      <h3>Progress notes</h3>
      <ol className="run-notes">
        {notes.length === 0 && <li className="faint">No notes.</li>}
        {notes.map((n, i) => <li key={i} className={`rn-${n.kind}`}><time dateTime={n.at}>{clock(n.at)}</time><span>{n.text}</span></li>)}
      </ol>
    </section>
  );
}

function PromptToggle({ catalog, runId }: { catalog: string; runId: string }) {
  const [prompt, setPrompt] = useState<string | null>(null);
  const [showPrompt, setShowPrompt] = useState(false);
  useEffect(() => {
    if (!showPrompt || prompt !== null) return;
    agentApi.prompt(catalog, runId).then((p) => setPrompt(p.text), () => setPrompt("(the prompt wasn't kept)"));
  }, [catalog, runId, showPrompt, prompt]);
  return (
    <section className="runs-sec">
      <button className="linkish" onClick={() => setShowPrompt((v) => !v)}>{showPrompt ? "Hide" : "Show"} the prompt Claude was given</button>
      {showPrompt && <pre className="prompt-pre runs-prompt">{prompt ?? "Loading…"}</pre>}
    </section>
  );
}

/** "Nov 5, 2:35 PM by Jared Diener, ran 4 min" (no " · ", one-rule-runs §1.5). */
export function runMeta(r: AgentRun): string {
  return `${when(r.created_at)} by ${r.started_by}${r.ended_at ? `, ran ${elapsed(r.created_at, r.ended_at)}` : LIVE.includes(r.state) ? ", still going" : ""}`;
}

/** "AVC: Credit Value, Description (yours)"; a run outside Course names its class: "WVU LearningProgram: Name". */
const queueWhat = (q: QueueRun, me: string) =>
  `${q.catalog_name ?? q.catalog}${q.class && q.class !== "course" ? ` ${CLASS_NAME[q.class]}` : ""}: `
  + `${(q.rule_names?.length ? q.rule_names : q.rules).join(", ")}${q.started_by === me ? " (yours)" : ""}`;

const STATE: Record<string, string> = {
  sending: "Starting", waiting: "In line", running: "Working", finished: "Finished", needs_you: "Things to fix", failed: "Didn't finish",
  cancelled: "Cancelled", timed_out: "Timed out", ended: "Marked as ended",
};
const when = (iso: string) => new Date(iso).toLocaleString("en-US", { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
const clock = (iso: string) => new Date(iso).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
