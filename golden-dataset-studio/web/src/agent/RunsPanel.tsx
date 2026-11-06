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
import { href, parseRoute } from "../shell/router";
import { compareOf, agentApi, agentApi2, andNames, elapsed, LIVE, ordinal, scopeWords, type AgentRun, type Queue, type QueueRun, type RunDetail,
} from "./api";
import { Report } from "./Report";
import { openRunDialog } from "./RunDialog";
import "./agent.css";

const STATE: Record<string, string> = {
  sending: "Starting", waiting: "In line", running: "Working", finished: "Finished", needs_you: "Things to fix", failed: "Didn't finish",
  cancelled: "Cancelled", timed_out: "Timed out", ended: "Marked as ended",
};
const when = (iso: string) => new Date(iso).toLocaleString("en-US", { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
const clock = (iso: string) => new Date(iso).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });

/** "Nov 5, 2:35 PM by Jared Diener, ran 4 min" (no " · ", one-rule-runs §1.5). */
export function runMeta(r: AgentRun): string {
  return `${when(r.created_at)} by ${r.started_by}${r.ended_at ? `, ran ${elapsed(r.created_at, r.ended_at)}` : LIVE.includes(r.state) ? ", still going" : ""}`;
}

/** "AVC: Credit Value, Description (yours)". */
const queueWhat = (q: QueueRun, me: string) =>
  `${q.catalog_name ?? q.catalog}: ${(q.rule_names?.length ? q.rule_names : q.rules).join(", ")}${q.started_by === me ? " (yours)" : ""}`;

export function RunsPanel({ catalog, initial, rule = null, ruleName = null, onClose }: {
  catalog: string; initial: string | null; rule?: string | null; ruleName?: string | null; onClose: () => void;
}) {
  const me = useReviewer();
  const [runs, setRuns] = useState<AgentRun[] | null>(null);
  const [queue, setQueue] = useState<Queue | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [open, setOpen] = useState<string | null>(initial);
  const [only, setOnly] = useState<string | null>(rule);
  useEffect(() => {
    let live = true;
    setRuns(null);
    (only ? agentApi2.ofRule(catalog, only) : agentApi.history(catalog))
      .then((r) => { if (live) setRuns(r); }, (e) => { if (live) setError(String(e.message ?? e)); });
    return () => { live = false; };
  }, [catalog, only]);
  useEffect(() => {
    let live = true;
    if (!only) agentApi2.queue().then((q) => { if (live) setQueue(q); }, () => {});
    return () => { live = false; };
  }, [only]);
  useEffect(() => {
    const on = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", on);
    return () => window.removeEventListener("keydown", on);
  }, [onClose]);
  // a link in a report to another tab (Compare vN → vM, Values changed's Compare): show that tab, not this drawer
  const openedOn = useRef(parseRoute(location.hash).tab);
  useEffect(() => {
    const on = () => { if (parseRoute(location.hash).tab !== openedOn.current) onClose(); };
    window.addEventListener("hashchange", on);
    return () => window.removeEventListener("hashchange", on);
  }, [onClose]);
  const busy = !!queue && (queue.working.length > 0 || queue.waiting.length > 0);
  const title = only ? `AI runs on ${ruleName ?? only}` : busy ? "AI runs" : "Past AI runs";
  const item = (r: AgentRun) => (
    <li key={r.run_id}>
      <button className="runs-item" onClick={() => setOpen(r.run_id)} data-run={r.run_id}>
        <span className={`runs-state s-${r.state}`}>{STATE[r.state] ?? r.state}</span>
        <span className="runs-what">{r.outcome ?? (r.scope.kind === "rules" && r.rule_names
          ? `Improving ${andNames((r.scope.rules ?? []).map((id) => r.rule_names?.[id] ?? id))}` : scopeWords(r.scope))}</span>
        <span className="runs-meta faint">{runMeta(r)}</span>
      </button>
    </li>
  );
  return (
    <div className="ac-back" onClick={onClose}>
      <aside className="run-watch runs-panel" role="dialog" aria-modal="true" aria-labelledby="runs-h" onClick={(e) => e.stopPropagation()}>
        <div className="ac-head">
          <h2 id="runs-h">{open ? <button className="linkish runs-back" onClick={() => setOpen(null)}>← {title}</button> : title}</h2>
          <button className="ac-x" aria-label="Close" onClick={onClose}>×</button>
        </div>
        {open ? <RunDetailView catalog={catalog} runId={open} />
          : error ? <p className="prompt-error runs-pad">{error}</p>
          : <>
            <div className="runs-detail" data-testid="runs-list">
              {only && <section className="runs-sec runs-head-acts">
                <button className="btn" onClick={() => { onClose(); openRunDialog([only]); }}><Ico name="spark" />Improve {ruleName ?? only}</button>
              </section>}
              {busy && <QueueSections q={queue!} me={me} />}
              <section className={busy ? "runs-sec" : "runs-sec runs-plain"}>
                {busy && <h3>Past AI runs</h3>}
                {!runs ? <p className="faint">Loading…</p>
                  : runs.filter((r) => !busy || !LIVE.includes(r.state)).length === 0
                    ? <p className="faint">{only ? "No AI run has worked on this rule yet." : "No runs yet on this catalog."}</p>
                  : <ol className="runs-list">{runs.filter((r) => !busy || !LIVE.includes(r.state)).map(item)}</ol>}
              </section>
            </div>
            {only && <div className="ac-foot"><button className="linkish" onClick={() => setOnly(null)}>Every AI run on this catalog</button></div>}
          </>}
      </aside>
    </div>
  );
}

/** "Working now: 2 of 2 places", "Waiting", and where the estimates come from (spec §1.7). */
export function QueueSections({ q, me }: { q: Queue; me: string }) {
  return <>
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
    {q.waiting.length > 0 && <section className="runs-sec" data-testid="queue-waiting">
      <h3>Waiting</h3>
      <ol className="runs-list">{q.waiting.map((w) => (
        <li key={w.run}><div className="runs-item">
          <span className="runs-state s-waiting">{ordinal(w.place ?? 1)} in line</span>
          <span className="runs-what">{queueWhat(w, me)}</span>
          <span className="runs-meta faint">{w.started_by}. Starts in about {Math.max(1, w.start_in_min ?? 1)} min</span>
        </div></li>))}
      </ol>
      {q.note && <p className="faint">{q.note}</p>}
    </section>}
  </>;
}

function RunDetailView({ catalog, runId }: { catalog: string; runId: string }) {
  const [d, setD] = useState<RunDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [prompt, setPrompt] = useState<string | null>(null);
  const [showPrompt, setShowPrompt] = useState(false);
  useEffect(() => {
    let live = true;
    agentApi2.detail(catalog, runId).then((x) => { if (live) setD(x); }, (e) => { if (live) setError(String(e.message ?? e)); });
    return () => { live = false; };
  }, [catalog, runId]);
  useEffect(() => {
    if (!showPrompt || prompt !== null) return;
    agentApi.prompt(catalog, runId).then((p) => setPrompt(p.text), () => setPrompt("(the prompt wasn't kept)"));
  }, [catalog, runId, showPrompt, prompt]);
  if (error) return <p className="prompt-error runs-pad">{error}</p>;
  if (!d) return <p className="faint runs-pad">Loading…</p>;
  const { run, notes, summary } = d;
  if (d.report) return <Report catalog={catalog} run={run} report={d.report} notes={notes} />;
  const grew = compareOf(run);
  return (
    <div className="runs-detail" data-testid="run-detail">
      <dl className="run-facts">
        <dt>Outcome</dt><dd><b>{STATE[run.state] ?? run.state}</b>{run.outcome ? `: ${run.outcome}` : ""}</dd>
        <dt>Asked to</dt><dd>{scopeWords(run.scope)}{run.scope.rules?.length ? <span className="mono faint"> ({run.scope.rules.join(", ")})</span> : null}</dd>
        <dt>Started</dt><dd>{runMeta(run)}</dd>
        {grew && <><dt>Published</dt><dd>ruleset v{run.ruleset_after}.{" "}
          <a href={href(catalog, "compare", null, grew)}>Compare v{grew.a} → v{grew.b}</a></dd></>}
        <dt>Run id</dt><dd className="mono faint">{run.run_id}</dd>
      </dl>
      <section className="runs-sec">
        <h3>Claude's report</h3>
        {summary ? <div className="prompt-md runs-report"><Markdown text={summary} /></div>
          : <p className="faint">No report was saved with this run{LIVE.includes(run.state) ? " yet" : ""}. Runs started before
            reports were kept have theirs only in the golden-rules chat on the Remote AI rule generator.</p>}
      </section>
      <section className="runs-sec">
        <h3>Progress notes</h3>
        <ol className="run-notes">
          {notes.length === 0 && <li className="faint">No notes.</li>}
          {notes.map((n, i) => <li key={i} className={`rn-${n.kind}`}><time dateTime={n.at}>{clock(n.at)}</time><span>{n.text}</span></li>)}
        </ol>
      </section>
      <section className="runs-sec">
        <button className="linkish" onClick={() => setShowPrompt((v) => !v)}>{showPrompt ? "Hide" : "Show"} the prompt Claude was given</button>
        {showPrompt && <pre className="prompt-pre runs-prompt">{prompt ?? "Loading…"}</pre>}
      </section>
    </div>
  );
}
