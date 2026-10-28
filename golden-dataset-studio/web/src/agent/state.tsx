// One poll of the catalog's run for the whole page (run bar, run buttons, Watch panel): every 3 s while the tab is
// visible. Each poll also moves the run forward on the server (a waiting run is sent when the agent is free).
// Notes accumulate: only lines after the last one seen are fetched.
import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from "react";
import { agentApi, LIVE, type AgentConfig, type AgentRun, type RunNote } from "./api";

export interface AgentState {
  config: AgentConfig | null;
  run: AgentRun | null;          // the live run
  last: AgentRun | null;         // when none is live: the latest that ended
  notes: RunNote[];              // of `run`, else of `last`
  now: string;
  refresh: () => void;
}

const EMPTY: AgentState = { config: null, run: null, last: null, notes: [], now: new Date().toISOString(), refresh: () => {} };
const Ctx = createContext<AgentState>(EMPTY);
export const useAgent = () => useContext(Ctx);

/** When the config can't be read (an older server, a network error), runs are off and buttons open the prompt. */
export const OFF: AgentConfig = { enabled: false, off_reason: "the Studio's server doesn't offer runs", agent_name: "Remote AI rule generator",
  k2_url: null, agent: null, minutes: 90, prompt_users: [] };
let configOnce: Promise<AgentConfig> | null = null;
export function loadAgentConfig(): Promise<AgentConfig> {
  configOnce ??= agentApi.config().then((c) => (c && typeof c.enabled === "boolean" ? c : OFF), () => OFF);
  return configOnce;
}
/** Tests: forget the cached config. */
export function resetAgentConfig(): void { configOnce = null; }

export function useAgentConfig(): AgentConfig | null {
  const [config, setConfig] = useState<AgentConfig | null>(null);
  useEffect(() => { let live = true; void loadAgentConfig().then((c) => { if (live) setConfig(c); }); return () => { live = false; }; }, []);
  return config;
}

export const POLL_MS = 3000;

export function AgentProvider({ catalog, children }: { catalog: string | null; children: ReactNode }) {
  const config = useAgentConfig();
  const [state, setState] = useState<Omit<AgentState, "config" | "refresh">>(EMPTY);
  const seen = useRef<{ catalog: string | null; runId: string | null; notes: RunNote[] }>({ catalog: null, runId: null, notes: [] });

  const poll = useCallback(async () => {
    if (!catalog) return;
    const s = seen.current.catalog === catalog ? seen.current : { catalog, runId: null, notes: [] };
    let d = await agentApi.current(catalog, s.notes.length);
    const shown = d.run ?? d.last;
    let notes: RunNote[];
    if (shown && shown.run_id === s.runId) notes = [...s.notes, ...d.notes];
    else if (!shown) notes = [];
    else {  // another run than the one we had: its notes from the start
      d = d.since === 0 ? d : await agentApi.current(catalog, 0);
      notes = d.notes;
    }
    seen.current = { catalog, runId: (d.run ?? d.last)?.run_id ?? null, notes };
    setState({ run: d.run, last: d.last, notes, now: d.now });
  }, [catalog]);

  useEffect(() => {
    seen.current = { catalog, runId: null, notes: [] };
    setState(EMPTY);
    if (!catalog) return;
    let stop = false;
    const tick = () => { if (!stop && document.visibilityState !== "hidden") poll().catch(() => {}); };
    tick();
    const id = window.setInterval(tick, POLL_MS);
    const onVis = () => { if (document.visibilityState === "visible") tick(); };
    document.addEventListener("visibilitychange", onVis);
    return () => { stop = true; window.clearInterval(id); document.removeEventListener("visibilitychange", onVis); };
  }, [catalog, poll]);

  const refresh = useCallback(() => { poll().catch(() => {}); }, [poll]);
  return <Ctx.Provider value={{ ...state, config, refresh }}>{children}</Ctx.Provider>;
}

export const isLive = (run: AgentRun | null): boolean => !!run && LIVE.includes(run.state);
