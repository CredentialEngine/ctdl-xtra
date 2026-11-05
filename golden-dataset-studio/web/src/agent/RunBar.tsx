// The run bar under the top bar (spec §1): what Claude is doing on this catalog right now, for everyone, with Watch
// and Cancel; after a run ends, its outcome until someone dismisses it. Watch opens the read-only notes panel, which
// becomes the run's report when the run ends; "Read the report" opens the same view later (sme-fixes spec §4).
import { useEffect, useState } from "react";
import { Markdown } from "../prompt/markdown";
import "../prompt/prompt.css";
import { Ico } from "../shell/icons";
import { useReviewer } from "../shell/reviewer";
import { href } from "../shell/router";
import { toast } from "../shell/ui";
import { agentApi, elapsed, endedIcon, endedLine, endedWords, LIVE, openRuns, scopeWords, type AgentRun, type RunNote } from "./api";
import { openPrompt } from "../prompt/PromptModal";
import { isLive, useAgent } from "./state";
import "./agent.css";

const DISMISSED = "studio.run.dismissed";
// remembered in this browser; where localStorage is unavailable (private mode, tests), until the page is reloaded
const gone = new Set<string>();
const dismissed = (id: string) => {
  if (gone.has(id)) return true;
  try { return localStorage.getItem(`${DISMISSED}.${id}`) === "1"; } catch { return false; }
};
const dismiss = (id: string) => {
  gone.add(id);
  try { localStorage.setItem(`${DISMISSED}.${id}`, "1"); } catch { /* private mode */ }
};
const SHOW_ENDED_HOURS = 24;

/** No word from Claude this long after the message was delivered: it has probably stopped (sme-fixes spec §4). The
 * prompt makes a note Claude's first action, so the silence means something. `now` is server time, from the poll. */
export const SILENT_MS = 5 * 60_000;
export function isSilent(run: AgentRun, notes: RunNote[], now: string): boolean {
  if (run.state !== "running" || notes.some((n) => n.kind !== "studio")) return false;
  return Date.parse(now) - Date.parse(run.sent_at ?? run.created_at) >= SILENT_MS;
}
const SILENT_WORDS = "Claude isn't responding. No update in 5 minutes; it may have stopped.";

async function markEnded(catalog: string, run: AgentRun, me: string, then: () => void) {
  const outcome = window.prompt("Mark this run as ended? Use this when Claude has clearly stopped without saying so. "
    + "A short note on what happened (optional):", "");
  if (outcome === null) return;
  try { await agentApi.end(catalog, run.run_id, me, outcome || undefined); toast("Run marked as ended"); } catch (e) { toast(String((e as Error).message)); }
  then();
}

const published = (r: AgentRun) => r.ruleset_after != null && r.ruleset_before != null && r.ruleset_after > r.ruleset_before;
function CompareLink({ catalog, run, className = "btn" }: { catalog: string; run: AgentRun; className?: string }) {
  return <a className={className} href={href(catalog, "compare", null, { a: run.ruleset_before, b: run.ruleset_after })}
    title="What changed between the two rulesets, rule by rule">Compare v{run.ruleset_before} → v{run.ruleset_after}</a>;
}

function headline(run: AgentRun, now: string, agentName: string, notes: RunNote[]): string {
  const who = `started by ${run.started_by}`;
  if (run.state === "waiting") return `Waiting for the ${agentName} (busy with another run) · ${who} · queued ${elapsed(run.created_at, now)}`;
  if (run.state === "sending") return `Sending to the ${agentName}… · ${who}`;
  const lastNote = [...notes].reverse().find((n) => n.kind === "note");
  const quiet = lastNote ? ` · last update ${elapsed(lastNote.at, now)} ago` : " · no update from Claude yet";
  return `Claude is ${scopeWords(run.scope)} · ${who} · ${elapsed(run.sent_at ?? run.created_at, now)}${quiet}`;
}

export function RunBar({ catalog }: { catalog: string }) {
  const me = useReviewer();
  const { config, run, last, notes, now, refresh } = useAgent();
  const [watch, setWatch] = useState(false);
  const [, bump] = useState(0);
  const name = config?.agent_name ?? "Remote AI rule generator";
  const live = isLive(run) ? run : null;
  const ended = !live && last && !dismissed(last.run_id) && last.ended_at
    && Date.parse(now) - Date.parse(last.ended_at) < SHOW_ENDED_HOURS * 3600_000 ? last : null;
  const shown = live ?? ended;
  if (!shown) return null;

  const cancel = async () => {
    if (!window.confirm("Cancel this run? Claude is asked to stop, and the catalog is free for a new run.")) return;
    try { await agentApi.cancel(catalog, shown.run_id, me); toast("Run cancelled"); } catch (e) { toast(String((e as Error).message)); }
    refresh();
  };
  const silent = !!live && isSilent(live, notes, now);
  return (
    <>
      <div className={`run-bar ${silent ? "is-silent" : live ? "is-live" : `is-${shown.state}`}`} role="status" data-testid="run-bar">
        {silent ? <Ico name="signal" /> : live ? <span className="run-pulse" aria-hidden="true" />
          : <Ico name={endedIcon(shown)} />}
        <span className="run-text" title={silent ? headline(live!, now, name, notes) : undefined}>
          {silent ? SILENT_WORDS : live ? headline(live, now, name, notes)
            : <>{endedWords(shown)}<span className="faint"> · started by {shown.started_by}</span></>}
        </span>
        <span className="run-actions">
          {ended && published(ended) && <CompareLink catalog={catalog} run={ended} />}
          {ended?.fallback_reason && <button className="btn" onClick={() => openPrompt(ended.fallback_reason!)}>Open the prompt</button>}
          {live ? <button className="btn" onClick={() => setWatch(true)}>Watch</button>
            : <button className="btn" onClick={() => setWatch(true)} title="Claude's report and progress notes">Read the report</button>}
          {silent && <button className="btn" onClick={() => markEnded(catalog, live!, me, refresh)}
            title="Claude has stopped without saying so: end the run, so the catalog is free for a new one">Mark as ended</button>}
          {live && <button className="btn" onClick={cancel}>Cancel</button>}
          {ended && <button className="run-x" aria-label="Dismiss" title="Dismiss" onClick={() => { dismiss(ended.run_id); bump((n) => n + 1); }}>×</button>}
        </span>
      </div>
      {watch && <WatchPanel catalog={catalog} run={shown} notes={notes} now={now} agentName={name}
        k2Url={config?.k2_url ?? null} onClose={() => setWatch(false)} onChanged={refresh} />}
    </>
  );
}

const STATE_WORDS: Record<string, string> = {
  sending: "Sending", waiting: "Waiting for the agent", running: "Working", finished: "Finished", needs_you: "Things to fix", failed: "Failed",
  cancelled: "Cancelled", timed_out: "Timed out", ended: "Marked as ended",
};
const clock = (iso: string) => new Date(iso).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });

/** Watching a live run: its facts and progress notes. Once it ends, the same panel is the run's report (RunReport). */
export function WatchPanel({ catalog, run, notes, now, agentName, k2Url, onClose, onChanged }: {
  catalog: string; run: AgentRun; notes: RunNote[]; now: string; agentName: string; k2Url: string | null;
  onClose: () => void; onChanged: () => void;
}) {
  const me = useReviewer();
  const live = LIVE.includes(run.state);
  const browsable = k2Url?.startsWith("https://");
  return (
    <div className="ac-back" onClick={onClose}>
      <aside className="run-watch" role="dialog" aria-modal="true" aria-labelledby="run-watch-h" onClick={(e) => e.stopPropagation()}>
        <div className="ac-head">
          <h2 id="run-watch-h">{live ? "Claude is " + scopeWords(run.scope) : "Claude's report"}</h2>
          <button className="ac-x" aria-label="Close" onClick={onClose}>×</button>
        </div>
        {live ? <>
          <dl className="run-facts">
            <dt>State</dt><dd>{STATE_WORDS[run.state]}{run.outcome ? `: ${run.outcome}` : ""}</dd>
            <dt>Started</dt><dd>by {run.started_by}, {elapsed(run.created_at, now)} ago</dd>
            {run.scope.rules && run.scope.rules.length > 0 && <><dt>Rules</dt><dd className="mono">{run.scope.rules.join(", ")}</dd></>}
            <dt>Runs on</dt><dd>the {agentName}{browsable && <> · <a href={k2Url!} target="_blank" rel="noopener noreferrer">open K2<Ico name="ext" /></a></>}</dd>
            <dt>Run id</dt><dd className="mono faint">{run.run_id}</dd>
          </dl>
          <ol className="run-notes" aria-label="Progress">
            {notes.length === 0 && <li className="faint">No notes yet.</li>}
            {notes.map((n, i) => (
              <li key={i} className={`rn-${n.kind}`}><time dateTime={n.at}>{clock(n.at)}</time><span>{n.text}</span></li>
            ))}
            <li className="faint rn-wait">{run.state === "running"
              ? "Claude reports as it goes; this updates every few seconds." : "Waiting for the agent to be free."}</li>
          </ol>
        </> : <RunReport catalog={catalog} run={run} notes={notes} />}
        <div className="ac-foot">
          <button className="linkish" onClick={() => { onClose(); openRuns(live ? undefined : run.run_id); }}
            title={live ? undefined : "This run's facts and the prompt Claude was given, among every earlier run"}>Past AI runs</button>
          {live && <button className="btn" onClick={() => markEnded(catalog, run, me, onChanged)}>Mark as ended</button>}
        </div>
      </aside>
    </div>
  );
}

/** An ended run in the Watch panel: how it ended (with Compare when it published a ruleset), Claude's report (the
 * `summary.md` it ended the run with), and its progress notes folded below. */
function RunReport({ catalog, run, notes }: { catalog: string; run: AgentRun; notes: RunNote[] }) {
  const [summary, setSummary] = useState<string | null | undefined>(undefined);  // undefined while loading
  useEffect(() => {
    let on = true;
    agentApi.detail(catalog, run.run_id).then((d) => { if (on) setSummary(d.summary); }, () => { if (on) setSummary(null); });
    return () => { on = false; };
  }, [catalog, run.run_id, run.state]);
  return (
    <div className="runs-detail" data-testid="run-report">
      <div className={`run-done is-${run.state}`}>
        <Ico name={endedIcon(run)} />
        <span className="run-done-t">{endedLine(run)}</span>
        {published(run) && <CompareLink catalog={catalog} run={run} className="btn primary" />}
      </div>
      <section className="runs-sec">
        {summary === undefined ? <p className="faint">Loading the report…</p>
          : summary ? <div className="prompt-md runs-report"><Markdown text={summary} /></div>
          : <p className="faint">No report was saved with this run.</p>}
      </section>
      <details className="runs-sec run-fold">
        <summary>Progress notes ({notes.length})</summary>
        <ol className="run-notes">
          {notes.length === 0 && <li className="faint">No notes.</li>}
          {notes.map((n, i) => <li key={i} className={`rn-${n.kind}`}><time dateTime={n.at}>{clock(n.at)}</time><span>{n.text}</span></li>)}
        </ol>
      </details>
    </div>
  );
}
