// A run button (spec §1): starts a run of Claude on the remote agent after one confirm. While the catalog has a
// live run it is disabled with what's running as the reason. Profiles in `prompt_users` (Eric, Seth) get a split
// button whose menu also offers Open the prompt (a modal). When runs are off, or the remote agent can't be reached,
// the button opens the prompt instead (with a warning in the second case).
import { useEffect, useRef, useState, type ReactNode } from "react";
import { Ico } from "../shell/icons";
import { useReviewer } from "../shell/reviewer";
import { toast } from "../shell/ui";
import { agentApi, elapsed, scopeWords, type RunScope } from "./api";
import { openPrompt } from "../prompt/PromptModal";
import { isLive, useAgent } from "./state";
import "./agent.css";

export function RunButton({ catalog, scope, label, confirm, onPrompt, variant = "primary", disabledReason, tour,
  split = true }: {
  catalog: string; scope: RunScope; label: ReactNode; confirm: string;
  /** show the prompt (default: the prompt modal); `warning` set when the agent couldn't be reached */
  onPrompt?: (warning?: string) => void;
  variant?: "primary" | "plain" | "link"; disabledReason?: string | null; tour?: string;
  /** false: never offer Open the prompt (the Prompt tab itself) */ split?: boolean;
}) {
  const me = useReviewer();
  const { config, run, now, refresh } = useAgent();
  const [asking, setAsking] = useState(false);
  const [menu, setMenu] = useState(false);
  const [busy, setBusy] = useState(false);
  const box = useRef<HTMLSpanElement>(null);
  useEffect(() => {
    if (!menu) return;
    const off = (e: MouseEvent) => { if (!box.current?.contains(e.target as Node)) setMenu(false); };
    window.addEventListener("mousedown", off);
    return () => window.removeEventListener("mousedown", off);
  }, [menu]);

  const showPrompt = (warning?: string) => (onPrompt ?? openPrompt)(warning);
  const enabled = !!config?.enabled;
  const promptUser = split && enabled && !!config?.prompt_users.includes(me);
  const live = isLive(run) ? run : null;
  const blocked = live ? `Claude is ${scopeWords(live.scope)} · started by ${live.started_by} · ${elapsed(live.created_at, now)}`
    : disabledReason ?? null;

  const start = async () => {
    setAsking(false);
    setBusy(true);
    const r = await agentApi.start(catalog, scope, me);
    setBusy(false);
    refresh();
    if (r.ok) toast(r.run.state === "waiting" ? "Queued: the agent is busy; your run starts when it's free" : "Started: watch it in the bar above");
    else if (r.kind === "fallback") showPrompt(r.reason || "no answer");
    else if (r.kind === "busy") toast(r.run ? `A run is already going: started by ${r.run.started_by}` : r.detail);
    else toast(r.detail);
  };
  const onMain = () => (enabled ? setAsking(true) : showPrompt());
  const cls = variant === "link" ? "linkish run-link" : `btn ${variant === "primary" ? "primary" : ""} run-btn`;
  const main = (
    <button className={cls} onClick={onMain} disabled={busy || (enabled && !!blocked)} data-tour={tour}
      title={enabled ? blocked ?? `Runs on the ${config?.agent_name}` : "Opens the prompt to run in Claude Code"}>
      {variant !== "link" && <Ico name="spark" />}{label}
    </button>
  );
  return (
    <span className={"run-wrap" + (promptUser ? " split" : "")} ref={box}>
      {main}
      {promptUser && (
        <button className={`btn ${variant === "primary" ? "primary" : ""} run-caret`} aria-label="More ways to run"
          aria-haspopup="menu" aria-expanded={menu} onClick={() => setMenu((m) => !m)}>▾</button>
      )}
      {menu && (
        <span className="run-menu" role="menu">
          <button role="menuitem" disabled={!!blocked} onClick={() => { setMenu(false); setAsking(true); }}>
            <Ico name="spark" />Run on the {config?.agent_name}</button>
          <button role="menuitem" onClick={() => { setMenu(false); showPrompt(); }}><Ico name="copy" />Open the prompt</button>
        </span>
      )}
      {asking && (
        <div className="ac-back" onClick={() => setAsking(false)}>
          <div className="ac run-ask" role="dialog" aria-modal="true" aria-labelledby="run-ask-h" onClick={(e) => e.stopPropagation()}>
            <div className="ac-head"><h2 id="run-ask-h">Run with Claude?</h2>
              <button className="ac-x" aria-label="Close" onClick={() => setAsking(false)}>×</button></div>
            <div className="ac-body">
              <p>{confirm}</p>
              <p className="run-note">Note: generating updated rules based on your feedback takes a few minutes to run, so we
                recommend making a batch of several annotations before doing generation.</p>
              <p className="muted">Claude works unattended on the {config?.agent_name} and publishes a new ruleset version.
                You can watch its progress here, and close this page meanwhile: the run keeps going.</p>
            </div>
            <div className="ac-foot">
              <button className="btn" onClick={() => setAsking(false)}>Cancel</button>
              <button className="btn primary" onClick={start} autoFocus><Ico name="spark" />Run</button>
            </div>
          </div>
        </div>
      )}
    </span>
  );
}
