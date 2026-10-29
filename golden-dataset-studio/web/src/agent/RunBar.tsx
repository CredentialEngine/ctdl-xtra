// The run bar under the top bar (spec §1): what Claude is doing on this catalog right now, for everyone, with Watch
// and Cancel; after a run ends, its outcome until someone dismisses it. Watch opens the read-only notes panel.
import { useState } from "react";
import { Ico } from "../shell/icons";
import { useReviewer } from "../shell/reviewer";
import { href } from "../shell/router";
import { toast } from "../shell/ui";
import { agentApi, elapsed, LIVE, openRuns, scopeWords, type AgentRun, type RunNote } from "./api";
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

const ENDED_WORDS: Record<string, string> = {
  finished: "Claude finished", failed: "Claude couldn't finish", cancelled: "Run cancelled",
  timed_out: "Run timed out", ended: "Run marked as ended",
};

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
  const grew = ended && ended.ruleset_after != null && ended.ruleset_before != null && ended.ruleset_after > ended.ruleset_before;
  return (
    <>
      <div className={`run-bar ${live ? "is-live" : `is-${shown.state}`}`} role="status" data-testid="run-bar">
        {live ? <span className="run-pulse" aria-hidden="true" /> : <Ico name={shown.state === "finished" ? "approved" : "needs work"} />}
        <span className="run-text">
          {live ? headline(live, now, name, notes)
            : <>{ENDED_WORDS[shown.state] ?? shown.state}{shown.outcome ? `: ${shown.outcome}` : ""}
              <span className="faint"> · {scopeWords(shown.scope)} · started by {shown.started_by}</span></>}
        </span>
        <span className="run-actions">
          {grew && <a className="btn" href={href(catalog, "compare", null, { a: ended!.ruleset_before, b: ended!.ruleset_after })}>
            Compare v{ended!.ruleset_before} → v{ended!.ruleset_after}</a>}
          {ended?.fallback_reason && <button className="btn" onClick={() => openPrompt(ended.fallback_reason!)}>Open the prompt</button>}
          {live ? <button className="btn" onClick={() => setWatch(true)}>Watch</button>
            : <button className="btn" onClick={() => openRuns(shown.run_id)}>Details</button>}
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
  sending: "Sending", waiting: "Waiting for the agent", running: "Working", finished: "Finished", failed: "Failed",
  cancelled: "Cancelled", timed_out: "Timed out", ended: "Marked as ended",
};
const clock = (iso: string) => new Date(iso).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });

export function WatchPanel({ catalog, run, notes, now, agentName, k2Url, onClose, onChanged }: {
  catalog: string; run: AgentRun; notes: RunNote[]; now: string; agentName: string; k2Url: string | null;
  onClose: () => void; onChanged: () => void;
}) {
  const me = useReviewer();
  const live = LIVE.includes(run.state);
  const markEnded = async () => {
    const outcome = window.prompt("Mark this run as ended? Use this when Claude has clearly stopped without saying so. "
      + "A short note on what happened (optional):", "");
    if (outcome === null) return;
    try { await agentApi.end(catalog, run.run_id, me, outcome || undefined); toast("Run marked as ended"); } catch (e) { toast(String((e as Error).message)); }
    onChanged();
  };
  const browsable = k2Url?.startsWith("https://");
  return (
    <div className="ac-back" onClick={onClose}>
      <aside className="run-watch" role="dialog" aria-modal="true" aria-labelledby="run-watch-h" onClick={(e) => e.stopPropagation()}>
        <div className="ac-head">
          <h2 id="run-watch-h">{live ? "Claude is " + scopeWords(run.scope) : STATE_WORDS[run.state]}</h2>
          <button className="ac-x" aria-label="Close" onClick={onClose}>×</button>
        </div>
        <dl className="run-facts">
          <dt>State</dt><dd>{STATE_WORDS[run.state]}{run.outcome ? `: ${run.outcome}` : ""}</dd>
          <dt>Started</dt><dd>by {run.started_by}, {run.ended_at ? `ran ${elapsed(run.created_at, run.ended_at)}`
            : `${elapsed(run.created_at, now)} ago`}</dd>
          {run.scope.rules && run.scope.rules.length > 0 && <><dt>Rules</dt><dd className="mono">{run.scope.rules.join(", ")}</dd></>}
          <dt>Runs on</dt><dd>the {agentName}{browsable && <> · <a href={k2Url!} target="_blank" rel="noopener noreferrer">open K2<Ico name="ext" /></a></>}</dd>
          <dt>Run id</dt><dd className="mono faint">{run.run_id}</dd>
        </dl>
        <ol className="run-notes" aria-label="Progress">
          {notes.length === 0 && <li className="faint">No notes yet.</li>}
          {notes.map((n, i) => (
            <li key={i} className={`rn-${n.kind}`}><time dateTime={n.at}>{clock(n.at)}</time><span>{n.text}</span></li>
          ))}
          {live && <li className="faint rn-wait">{run.state === "running"
            ? "Claude reports as it goes; this updates every few seconds." : "Waiting for the agent to be free."}</li>}
        </ol>
        <div className="ac-foot">
          <button className="linkish" onClick={() => { onClose(); openRuns(); }}>Past AI runs</button>
          {live && <button className="btn" onClick={markEnded}>Mark as ended</button>}
        </div>
      </aside>
    </div>
  );
}
