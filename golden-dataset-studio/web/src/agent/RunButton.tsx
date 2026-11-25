// A run button (spec §1): starts a run of Claude on the remote agent after one confirm. While the catalog has a
// live run it is disabled with what's running as the reason. Profiles in `prompt_users` (Eric, Seth) get a split
// button whose menu also offers Open the prompt (a modal). When runs are off, or the remote agent can't be reached,
// the button opens the prompt instead (with a warning in the second case).
import { useEffect, useRef, useState, type Dispatch, type ReactNode, type RefObject, type SetStateAction } from "react";
import { Ico } from "../shell/icons";
import { useReviewer } from "../shell/reviewer";
import { toast } from "../shell/ui";
import { agentApi, elapsed, scopeWords, type AgentRun, type RunScope, type StartResult } from "./api";
import { openPrompt } from "../prompt/PromptModal";
import { isLive, useAgent } from "./state";
import "./agent.css";

type Variant = "primary" | "plain" | "link";

interface RunButtonProps {
  catalog: string; scope: RunScope; label: ReactNode; confirm: string;
  /** show the prompt (default: the prompt modal); `warning` set when the agent couldn't be reached */
  onPrompt?: (warning?: string) => void;
  variant?: Variant; disabledReason?: string | null; tour?: string;
  /** false: never offer Open the prompt (the Prompt tab itself) */ split?: boolean;
  /** ask with another dialog (the rule picker, one-rule-runs §1.2) instead of the confirm below; runs then queue, so a
   * live run doesn't disable the button */
  onAsk?: () => void;
}

export function RunButton(props: RunButtonProps) {
  const { label, confirm, variant = "primary", tour } = props;
  const b = useRunButton(props);
  return (
    <span className={"run-wrap" + (b.promptUser ? " split" : "")} ref={b.menu.box}>
      <MainButton variant={variant} label={label} tour={tour} onClick={b.onMain} disabled={b.busy || (b.enabled && !!b.blocked)}
        title={b.enabled ? b.blocked ?? `Runs on the ${b.agentName}` : "Opens the prompt to run in Claude Code"} />
      {b.promptUser && <MenuCaret variant={variant} open={b.menu.open} onToggle={() => b.menu.setOpen((m) => !m)} />}
      {b.menu.open && <RunMenu agentName={b.agentName} blocked={b.blocked}
        onRun={() => { b.menu.setOpen(false); b.ask(); }} onPrompt={() => { b.menu.setOpen(false); b.showPrompt(); }} />}
      {b.asking && <AskDialog confirm={confirm} agentName={b.agentName} onClose={() => b.setAsking(false)} onRun={b.start} />}
    </span>
  );
}

function useRunButton({ catalog, scope, onPrompt, disabledReason, split = true, onAsk }: RunButtonProps) {
  const me = useReviewer();
  const { config, run, now, refresh } = useAgent();
  const [asking, setAsking] = useState(false);
  const menu = useMenu();
  const enabled = !!config?.enabled;
  const showPrompt = (warning?: string) => (onPrompt ?? openPrompt)(warning);
  const { busy, start } = useStart(() => agentApi.start(catalog, scope, me), () => setAsking(false), refresh, showPrompt);
  const ask = () => (onAsk ? onAsk() : setAsking(true));
  return { enabled, busy, asking, setAsking, menu, showPrompt, start, ask, onMain: () => (enabled ? ask() : showPrompt()),
    agentName: config?.agent_name, promptUser: split && enabled && !!config?.prompt_users.includes(me),
    blocked: blockedReason(run, now, onAsk, disabledReason) };
}

function useStart(post: () => Promise<StartResult>, closeAsk: () => void, refresh: () => void, showPrompt: (warning?: string) => void) {
  const [busy, setBusy] = useState(false);
  const start = async () => {
    closeAsk();
    setBusy(true);
    const r = await post();
    setBusy(false);
    refresh();
    announceStart(r, showPrompt);
  };
  return { busy, start };
}

function useMenu(): { open: boolean; setOpen: Dispatch<SetStateAction<boolean>>; box: RefObject<HTMLSpanElement> } {
  const [open, setOpen] = useState(false);
  const box = useRef<HTMLSpanElement>(null);
  useEffect(() => {
    if (!open) return;
    const off = (e: MouseEvent) => { if (!box.current?.contains(e.target as Node)) setOpen(false); };
    window.addEventListener("mousedown", off);
    return () => window.removeEventListener("mousedown", off);
  }, [open]);
  return { open, setOpen, box };
}

function blockedReason(run: AgentRun | null, now: string, onAsk: (() => void) | undefined, disabledReason?: string | null): string | null {
  const live = isLive(run) ? run : null;
  return live && !onAsk ? `Claude is ${scopeWords(live.scope)} · started by ${live.started_by} · ${elapsed(live.created_at, now)}`
    : disabledReason ?? null;
}

function announceStart(r: StartResult, showPrompt: (warning?: string) => void): void {
  if (r.ok) toast(r.run.state === "waiting" ? "Queued: the agent is busy; your run starts when it's free" : "Started: watch it in the bar above");
  else if (r.kind === "fallback") showPrompt(r.reason || "no answer");
  else if (r.kind === "busy") toast(r.run ? `A run is already going: started by ${r.run.started_by}` : r.detail);
  else toast(r.detail);
}

function MainButton({ variant, label, tour, onClick, disabled, title }: {
  variant: Variant; label: ReactNode; tour?: string; onClick: () => void; disabled: boolean; title: string;
}) {
  const cls = variant === "link" ? "linkish run-link" : `btn ${variant === "primary" ? "primary" : ""} run-btn`;
  return (
    <button className={cls} onClick={onClick} disabled={disabled} data-tour={tour} title={title}>
      {variant !== "link" && <Ico name="spark" />}{label}
    </button>
  );
}

function MenuCaret({ variant, open, onToggle }: { variant: Variant; open: boolean; onToggle: () => void }) {
  return (
    <button className={`btn ${variant === "primary" ? "primary" : ""} run-caret`} aria-label="More ways to run"
      aria-haspopup="menu" aria-expanded={open} onClick={onToggle}><Ico name="chevron" /></button>
  );
}

function RunMenu({ agentName, blocked, onRun, onPrompt }: {
  agentName?: string; blocked: string | null; onRun: () => void; onPrompt: () => void;
}) {
  return (
    <span className="run-menu" role="menu">
      <button role="menuitem" disabled={!!blocked} onClick={onRun}>
        <Ico name="spark" />Run on the {agentName}</button>
      <button role="menuitem" onClick={onPrompt}><Ico name="copy" />Open the prompt</button>
    </span>
  );
}

function AskDialog({ confirm, agentName, onClose, onRun }: { confirm: string; agentName?: string; onClose: () => void; onRun: () => void }) {
  return (
    <div className="ac-back" onClick={onClose}>
      <div className="ac run-ask" role="dialog" aria-modal="true" aria-labelledby="run-ask-h" onClick={(e) => e.stopPropagation()}>
        <div className="ac-head"><h2 id="run-ask-h">Run with Claude?</h2>
          <button className="ac-x" aria-label="Close" onClick={onClose}>×</button></div>
        <AskBody confirm={confirm} agentName={agentName} />
        <div className="ac-foot">
          <button className="btn" onClick={onClose}>Cancel</button>
          <button className="btn primary" onClick={onRun} autoFocus><Ico name="spark" />Run</button>
        </div>
      </div>
    </div>
  );
}

function AskBody({ confirm, agentName }: { confirm: string; agentName?: string }) {
  return (
    <div className="ac-body">
      <p>{confirm}</p>
      <p className="run-note">Note: generating updated rules based on your feedback takes a few minutes to run, so we
        recommend making a batch of several annotations before doing generation.</p>
      <p className="muted">Claude works unattended on the {agentName} and publishes a new ruleset version.
        You can watch its progress here, and close this page meanwhile: the run keeps going.</p>
    </div>
  );
}
