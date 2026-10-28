// Past AI runs: every run of Claude on this catalog, newest first; one run's outcome, the agent's final report
// (Markdown, from `run done --summary-file`), its progress notes, and the exact prompt it was given. Read-only.
// Opened from the footer, the bottom of the rule list, and an ended run in the run bar (openRuns in api.ts).
import { useEffect, useState } from "react";
import { Markdown } from "../prompt/markdown";
import "../prompt/prompt.css";
import { href } from "../shell/router";
import { agentApi, elapsed, LIVE, scopeWords, type AgentRun, type RunNote } from "./api";
import "./agent.css";

const STATE: Record<string, string> = {
  sending: "Sending", waiting: "Waiting for the agent", running: "Working", finished: "Finished", failed: "Didn't finish",
  cancelled: "Cancelled", timed_out: "Timed out", ended: "Marked as ended",
};
const when = (iso: string) => new Date(iso).toLocaleString([], { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
const clock = (iso: string) => new Date(iso).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });

export function RunsPanel({ catalog, initial, onClose }: { catalog: string; initial: string | null; onClose: () => void }) {
  const [runs, setRuns] = useState<AgentRun[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [open, setOpen] = useState<string | null>(initial);
  useEffect(() => {
    let live = true;
    agentApi.history(catalog).then((r) => { if (live) setRuns(r); }, (e) => { if (live) setError(String(e.message ?? e)); });
    return () => { live = false; };
  }, [catalog]);
  useEffect(() => {
    const on = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", on);
    return () => window.removeEventListener("keydown", on);
  }, [onClose]);
  return (
    <div className="ac-back" onClick={onClose}>
      <aside className="run-watch runs-panel" role="dialog" aria-modal="true" aria-labelledby="runs-h" onClick={(e) => e.stopPropagation()}>
        <div className="ac-head">
          <h2 id="runs-h">{open ? <button className="linkish runs-back" onClick={() => setOpen(null)}>← Past AI runs</button> : "Past AI runs"}</h2>
          <button className="ac-x" aria-label="Close" onClick={onClose}>×</button>
        </div>
        {open ? <RunDetail catalog={catalog} runId={open} />
          : error ? <p className="prompt-error runs-pad">{error}</p>
          : !runs ? <p className="faint runs-pad">Loading…</p>
          : runs.length === 0 ? <p className="faint runs-pad">No runs yet on this catalog.</p>
          : (
            <ol className="runs-list">
              {runs.map((r) => (
                <li key={r.run_id}>
                  <button className="runs-item" onClick={() => setOpen(r.run_id)} data-run={r.run_id}>
                    <span className={`runs-state s-${r.state}`}>{STATE[r.state] ?? r.state}</span>
                    <span className="runs-what">{r.outcome ?? scopeWords(r.scope)}</span>
                    <span className="runs-meta faint">{when(r.created_at)} · {r.started_by}
                      {r.ended_at ? ` · ${elapsed(r.created_at, r.ended_at)}` : ""}</span>
                  </button>
                </li>
              ))}
            </ol>
          )}
      </aside>
    </div>
  );
}

function RunDetail({ catalog, runId }: { catalog: string; runId: string }) {
  const [d, setD] = useState<{ run: AgentRun; notes: RunNote[]; summary: string | null } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [prompt, setPrompt] = useState<string | null>(null);
  const [showPrompt, setShowPrompt] = useState(false);
  useEffect(() => {
    let live = true;
    agentApi.detail(catalog, runId).then((x) => { if (live) setD(x); }, (e) => { if (live) setError(String(e.message ?? e)); });
    return () => { live = false; };
  }, [catalog, runId]);
  useEffect(() => {
    if (!showPrompt || prompt !== null) return;
    agentApi.prompt(catalog, runId).then((p) => setPrompt(p.text), () => setPrompt("(the prompt wasn't kept)"));
  }, [catalog, runId, showPrompt, prompt]);
  if (error) return <p className="prompt-error runs-pad">{error}</p>;
  if (!d) return <p className="faint runs-pad">Loading…</p>;
  const { run, notes, summary } = d;
  const grew = run.ruleset_after != null && run.ruleset_before != null && run.ruleset_after > run.ruleset_before;
  return (
    <div className="runs-detail" data-testid="run-detail">
      <dl className="run-facts">
        <dt>Outcome</dt><dd><b>{STATE[run.state] ?? run.state}</b>{run.outcome ? `: ${run.outcome}` : ""}</dd>
        <dt>Asked to</dt><dd>{scopeWords(run.scope)}{run.scope.rules?.length ? <span className="mono faint"> ({run.scope.rules.join(", ")})</span> : null}</dd>
        <dt>Started</dt><dd>{when(run.created_at)} by {run.started_by}
          {run.ended_at ? ` · ran ${elapsed(run.created_at, run.ended_at)}` : LIVE.includes(run.state) ? " · still going" : ""}</dd>
        {grew && <><dt>Published</dt><dd>ruleset v{run.ruleset_after} ·{" "}
          <a href={href(catalog, "compare", null, { a: run.ruleset_before, b: run.ruleset_after })}>Compare v{run.ruleset_before} → v{run.ruleset_after}</a></dd></>}
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
