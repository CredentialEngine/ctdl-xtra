// The run bar under the top bar (spec §1; one-rule-runs §1.3, §1.7): what Claude is doing on this catalog right now,
// for everyone, in sentences ("Claude is working on Description. Your run on Subject Webpage is 2nd in line. It should
// start in about 6 min."), with Watch, See the queue and Cancel; after a run ends, its outcome until someone dismisses
// it. Watch opens the read-only notes panel, which becomes the run's report when the run ends; "Read the report" opens
// the same view later. No " · " separators: who started a run is in the report's facts.
import { useEffect, useState } from "react";
import { Markdown } from "../prompt/markdown";
import "../prompt/prompt.css";
import { Ico } from "../shell/icons";
import { useReviewer } from "../shell/reviewer";
import { href } from "../shell/router";
import { toast } from "../shell/ui";
import {
  agentApi, agentApi2, andNames, elapsed, endedIcon, endedLine, endedWords, LIVE, openRuns, ruleNames, scopeWords, waitingWords,
  type AgentRun, type LiveRun, type ResolvedReport, type RunNote,
} from "./api";
import { openPrompt } from "../prompt/PromptModal";
import { Report, useReportRows } from "./Report";
import { useAgent } from "./state";
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

/** What a run works on: its rules by name, or (older runs) a few words. */
const onWhat = (r: AgentRun) => (r.scope.kind === "rules" && ruleNames(r).length ? andNames(ruleNames(r)) : null);

/** A working run's sentence: "Claude is working on Description." */
function workingWords(run: AgentRun, agentName: string): string {
  const what = onWhat(run);
  if (run.state === "sending") return what ? `Starting Claude on ${what}.` : `Sending to the ${agentName}.`;
  return what ? `Claude is working on ${what}.` : `Claude is ${scopeWords(run.scope)}.`;
}
/** The hover line of a working run: who started it, and when Claude last wrote. */
function workingTip(run: AgentRun, notes: RunNote[], now: string): string {
  const lastNote = [...notes].reverse().find((n) => n.kind === "note");
  return `Started by ${run.started_by}, ${elapsed(run.sent_at ?? run.created_at, now)} ago. `
    + (lastNote ? `Last update ${elapsed(lastNote.at, now)} ago.` : "No update from Claude yet.");
}

export function RunBar({ catalog }: { catalog: string }) {
  const me = useReviewer();
  const { config, runs, last, notes, recent, now, refresh } = useAgent();
  const [watch, setWatch] = useState<string | null>(null);  // the run whose panel is open
  const [, bump] = useState(0);
  const name = config?.agent_name ?? "Remote AI rule generator";
  const working = runs.filter((r) => r.state !== "waiting");
  const waiting = runs.filter((r) => r.state === "waiting");
  const ended = runs.length === 0 && last && !dismissed(last.run_id) && last.ended_at
    && Date.parse(now) - Date.parse(last.ended_at) < SHOW_ENDED_HOURS * 3600_000 ? last : null;
  const { data: feedback } = useReportRows(catalog, ended?.report_version ? ended.run_id : null);
  // the watched run: a live one, or the run that just ended (the Watch panel becomes its report)
  const watched: AgentRun | null = watch ? runs.find((r) => r.run_id === watch) ?? (last?.run_id === watch ? last : null) : null;
  const panel = watched && <WatchPanel catalog={catalog} run={watched} notes={(watched as LiveRun).notes ?? notes} now={now}
    agentName={name} k2Url={config?.k2_url ?? null} onClose={() => setWatch(null)} onChanged={refresh} />;
  if (!runs.length && !ended) return panel || null;

  // the run Cancel and Mark as ended act on: yours in line first, else the first working
  const primary: LiveRun | undefined = waiting.find((r) => r.started_by === me) ?? working[0] ?? waiting[0];
  const silent = working.find((r) => isSilent(r, r.notes ?? [], now));
  const cancel = async () => {
    if (!primary) return;
    const what = onWhat(primary);
    if (!window.confirm(`Cancel the run${what ? ` on ${what}` : ""}? Claude is asked to stop, and its place goes to the next run.`)) return;
    try { await agentApi.cancel(catalog, primary.run_id, me); toast("Run cancelled"); } catch (e) { toast(String((e as Error).message)); }
    refresh();
  };

  let text: string;
  let tip: string | undefined;
  let cls: string;
  if (runs.length) {
    const live = new Set(runs.flatMap((r) => r.scope.rules ?? []));
    const decisions = Object.entries(recent).filter(([rule, r]) => !live.has(rule) && r.state === "needs_you" && r.to_do_count && (r as { rule_name?: string }).rule_name)
      .map(([, r]) => `${(r as { rule_name?: string }).rule_name} needs ${r.to_do_count} decision${r.to_do_count === 1 ? "" : "s"} from you.`);
    text = [...working.map((r) => (r === silent ? SILENT_WORDS : workingWords(r, name))), ...waiting.map((r) => waitingWords(r, me)), ...decisions].join(" ");
    tip = working[0] ? workingTip(working[0], working[0].notes ?? [], now) : undefined;
    cls = silent ? "is-silent" : "is-live";
  } else {
    const e = ended!;
    const also = (e.also_changed ?? []).map((id) => e.rule_names?.[id] ?? id);
    const n = feedback?.new_feedback ?? 0;
    text = [`${endedWords(e)}.`, also.length ? `It also changed ${andNames(also)}.` : "",
            n ? `${n} row${n === 1 ? " has" : "s have"} new feedback since.` : ""].filter(Boolean).join(" ");
    cls = `is-${e.state}`;
  }
  return (
    <>
      <div className={`run-bar ${cls}`} role="status" data-testid="run-bar">
        {silent ? <Ico name="signal" /> : runs.length ? <span className="run-pulse" aria-hidden="true" /> : <Ico name={endedIcon(ended!)} />}
        <span className="run-text" title={tip}>{text}</span>
        <span className="run-actions">
          {ended && published(ended) && <CompareLink catalog={catalog} run={ended} />}
          {ended?.fallback_reason && <button className="btn" onClick={() => openPrompt(ended.fallback_reason!)}>Open the prompt</button>}
          {working[0] && <button className="btn" onClick={() => setWatch(working[0].run_id)}>Watch</button>}
          {waiting.length > 0 && <button className="btn" onClick={() => openRuns()} title="The runs working now and the runs in line, on every catalog">See the queue</button>}
          {ended && <button className="btn" onClick={() => setWatch(ended.run_id)} title="Claude's report and progress notes">Read the report</button>}
          {silent && <button className="btn" onClick={() => markEnded(catalog, silent, me, refresh)}
            title="Claude has stopped without saying so: end the run, so its place is free for the next one">Mark as ended</button>}
          {primary && <button className="btn" onClick={cancel}>Cancel</button>}
          {ended && <button className="run-x" aria-label="Dismiss" title="Dismiss" onClick={() => { dismiss(ended.run_id); bump((k) => k + 1); }}>×</button>}
        </span>
      </div>
      {panel}
    </>
  );
}

const STATE_WORDS: Record<string, string> = {
  sending: "Starting", waiting: "Waiting for a free place", running: "Working", finished: "Finished", needs_you: "Things to fix", failed: "Failed",
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
  const what = onWhat(run);
  const past = () => { onClose(); openRuns(live ? undefined : run.run_id); };
  return (
    <div className="ac-back" onClick={onClose}>
      <aside className="run-watch" role="dialog" aria-modal="true" aria-labelledby="run-watch-h" onClick={(e) => e.stopPropagation()}>
        <div className="ac-head">
          <h2 id="run-watch-h">{live ? (what ? `Claude is working on ${what}` : "Claude is " + scopeWords(run.scope)) : "Claude's report"}</h2>
          <button className="ac-x" aria-label="Close" onClick={onClose}>×</button>
        </div>
        {live ? <>
          <dl className="run-facts">
            <dt>State</dt><dd>{STATE_WORDS[run.state]}{run.outcome ? `: ${run.outcome}` : ""}</dd>
            <dt>Started</dt><dd>by {run.started_by}, {elapsed(run.created_at, now)} ago</dd>
            {run.scope.rules && run.scope.rules.length > 0 && <><dt>Rules to improve</dt><dd>{what ?? <span className="mono">{run.scope.rules.join(", ")}</span>}</dd></>}
            <dt>Runs on</dt><dd>the {agentName}{browsable && <> (<a href={k2Url!} target="_blank" rel="noopener noreferrer">open K2<Ico name="ext" /></a>)</>}</dd>
            <dt>Run id</dt><dd className="mono faint">{run.run_id}</dd>
          </dl>
          <ol className="run-notes" aria-label="Progress">
            {notes.length === 0 && <li className="faint">No notes yet.</li>}
            {notes.map((n, i) => (
              <li key={i} className={`rn-${n.kind}`}><time dateTime={n.at}>{clock(n.at)}</time><span>{n.text}</span></li>
            ))}
            <li className="faint rn-wait">{run.state === "running"
              ? "Claude reports as it goes; this updates every few seconds." : "Waiting for a free place."}</li>
          </ol>
          <div className="ac-foot">
            <button className="linkish" onClick={past}>Past AI runs</button>
            <button className="btn" onClick={() => markEnded(catalog, run, me, onChanged)}>Mark as ended</button>
          </div>
        </> : <RunReport catalog={catalog} run={run} notes={notes} pastRuns={past} />}
      </aside>
    </div>
  );
}

/** An ended run in the Watch panel: the report rendered from `report.resolved.json` (one-rule-runs §1.4), or, for an
 * older run, how it ended (with Compare when it published a ruleset), its `summary.md`, and its notes folded below. */
function RunReport({ catalog, run, notes, pastRuns }: { catalog: string; run: AgentRun; notes: RunNote[]; pastRuns: () => void }) {
  const [d, setD] = useState<{ summary: string | null; report: ResolvedReport | null; run: AgentRun } | null | undefined>(undefined);
  useEffect(() => {
    let on = true;
    agentApi2.detail(catalog, run.run_id).then((x) => { if (on) setD({ summary: x.summary, report: x.report ?? null, run: x.run ?? run }); },
      () => { if (on) setD(null); });
    return () => { on = false; };
  }, [catalog, run.run_id, run.state]);  // eslint-disable-line react-hooks/exhaustive-deps
  if (d?.report) return <Report catalog={catalog} run={d.run} report={d.report} notes={notes} pastRuns={pastRuns} />;
  const summary = d === undefined ? undefined : d?.summary ?? null;
  return (
    <>
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
      <div className="ac-foot">
        <button className="linkish" onClick={pastRuns}
          title="This run's facts and the prompt Claude was given, among every earlier run">Past AI runs</button>
      </div>
    </>
  );
}
