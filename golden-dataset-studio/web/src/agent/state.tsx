// One poll of the catalog's run for the whole page (run bar, run buttons, Watch panel): every 3 s while the tab is
// visible. Each poll also moves the run forward on the server (a waiting run is sent when the agent is free).
// Notes accumulate: only lines after the last one seen are fetched.
import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from "react";
import { inClass, noteRunClass } from "../shell/klass";
import { CLASS_NAME, type ClassSlug } from "../shell/router";
import { agentApi, LIVE, type AgentConfig, type AgentRun, type CurrentRun, type LiveRun, type RecentRun, type RunNote, type Slots } from "./api";

export interface AgentState {
  config: AgentConfig | null;
  run: AgentRun | null;          // the live run
  last: AgentRun | null;         // when none is live: the latest that ended
  notes: RunNote[];              // of `run`, else of `last`
  /** every live run of the catalog, oldest first, each with its notes and place in the queue (one-rule-runs §1.7) */
  runs: LiveRun[];
  /** per rule, its latest ended run (the sidebar's AI status) */
  recent: Record<string, RecentRun>;
  slots: Slots | null;
  now: string;
  /** the classes polled: one, or with All classes each class with rules (each run then says its class) */
  classes: ClassSlug[];
  refresh: () => void;
}

const EMPTY: AgentState = { config: null, run: null, last: null, notes: [], runs: [], recent: {}, slots: null,
  now: new Date().toISOString(), classes: [], refresh: () => {} };
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

/** A run's class before its words when several classes are shown ("LearningProgram: Claude is working on Name"). */
export function classPrefix(r: AgentRun | null | undefined, classes: ClassSlug[]): string {
  return r?.cls && classes.length > 1 ? `${CLASS_NAME[r.cls]}: ` : "";
}

type Seen = { runId: string | null; notes: RunNote[] };

/** One class's poll: its current run with the notes after the ones already seen. */
async function pollOne(catalog: string, cls: ClassSlug, s: Seen): Promise<{ d: CurrentRun; seen: Seen }> {
  let d = await inClass(cls, () => agentApi.current(catalog, s.notes.length));
  const shown = d.run ?? d.last;
  let notes: RunNote[];
  if (shown && shown.run_id === s.runId) notes = [...s.notes, ...d.notes];
  else if (!shown) notes = [];
  else {  // another run than the one we had: its notes from the start
    d = d.since === 0 ? d : await inClass(cls, () => agentApi.current(catalog, 0));
    notes = d.notes;
  }
  return { d, seen: { runId: (d.run ?? d.last)?.run_id ?? null, notes } };
}

export function AgentProvider({ catalog, classes = ["course"], children }: {
  catalog: string | null; classes?: ClassSlug[]; children: ReactNode;
}) {
  const config = useAgentConfig();
  const [state, setState] = useState<Omit<AgentState, "config" | "refresh">>(EMPTY);
  const key = `${catalog}|${classes.join(",")}`;
  const seen = useRef<{ key: string; by: Partial<Record<ClassSlug, Seen>> }>({ key: "", by: {} });

  const poll = useCallback(async () => {
    if (!catalog) return;
    if (seen.current.key !== key) seen.current = { key, by: {} };
    const got = await Promise.all(classes.map((cls) =>
      pollOne(catalog, cls, seen.current.by[cls] ?? { runId: null, notes: [] }).then((x) => ({ cls, ...x }))));
    const tag = <T extends AgentRun | null>(r: T, cls: ClassSlug): T => {
      if (!r || classes.length < 2) return r;
      noteRunClass(r.run_id, cls);
      return { ...r, cls };
    };
    let runs: LiveRun[] = [], run: AgentRun | null = null, last: AgentRun | null = null, notes: RunNote[] = [];
    let recent: Record<string, RecentRun> = {}, slots: Slots | null = null, now = new Date().toISOString();
    for (const { cls, d, seen: s } of got) {
      seen.current.by[cls] = s;
      // an older server has only `run`: it is the one live run
      const mine = d.runs ?? (d.run ? [{ ...d.run, notes: s.notes, queue: { place: null, start_in_min: null, left_min: null, minutes_so_far: null } }] : []);
      runs = [...runs, ...mine.map((r) => tag(r, cls))];
      if (d.run && !run) { run = tag(d.run, cls); notes = s.notes; }
      if (d.last && (!last || (d.last.ended_at ?? "") > (last.ended_at ?? ""))) {
        last = tag(d.last, cls);
        if (!run) notes = s.notes;
      }
      recent = { ...recent, ...(d.recent ?? {}) };
      slots = slots ?? d.slots ?? null;
      now = d.now;
    }
    runs.sort((a, b) => a.created_at.localeCompare(b.created_at));
    setState({ run, last, notes, runs, recent, slots, now, classes });
  }, [catalog, key]);  // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    seen.current = { key, by: {} };
    setState(EMPTY);
    if (!catalog) return;
    let stop = false;
    const tick = () => { if (!stop && document.visibilityState !== "hidden") poll().catch(() => {}); };
    tick();
    const id = window.setInterval(tick, POLL_MS);
    const onVis = () => { if (document.visibilityState === "visible") tick(); };
    document.addEventListener("visibilitychange", onVis);
    return () => { stop = true; window.clearInterval(id); document.removeEventListener("visibilitychange", onVis); };
  }, [key, poll]);  // eslint-disable-line react-hooks/exhaustive-deps

  const refresh = useCallback(() => { poll().catch(() => {}); }, [poll]);
  return <Ctx.Provider value={{ ...state, config, refresh }}>{children}</Ctx.Provider>;
}

export const isLive = (run: AgentRun | null): boolean => !!run && LIVE.includes(run.state);
