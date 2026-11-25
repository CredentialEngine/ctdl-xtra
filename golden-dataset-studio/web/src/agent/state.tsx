// One poll of the catalog's run for the whole page (run bar, run buttons, Watch panel): every 3 s while the tab is
// visible. Each poll also moves the run forward on the server (a waiting run is sent when the agent is free).
// Notes accumulate: only lines after the last one seen are fetched.
import { createContext, useCallback, useContext, useEffect, useRef, useState, type MutableRefObject, type ReactNode } from "react";
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

type PolledState = Omit<AgentState, "config" | "refresh">;
type Seen = { runId: string | null; notes: RunNote[] };
type SeenByClass = { key: string; by: Partial<Record<ClassSlug, Seen>> };
type ClassPoll = { cls: ClassSlug; d: CurrentRun; seen: Seen };

const EMPTY: AgentState = { config: null, run: null, last: null, notes: [], runs: [], recent: {}, slots: null,
  now: new Date().toISOString(), classes: [], refresh: () => {} };
const Ctx = createContext<AgentState>(EMPTY);
export const useAgent = () => useContext(Ctx);

export const POLL_MS = 3000;

export function AgentProvider({ catalog, classes = ["course"], children }: {
  catalog: string | null; classes?: ClassSlug[]; children: ReactNode;
}) {
  const config = useAgentConfig();
  const { state, refresh } = useRunPoll(catalog, classes);
  return <Ctx.Provider value={{ ...state, config, refresh }}>{children}</Ctx.Provider>;
}

function useRunPoll(catalog: string | null, classes: ClassSlug[]): { state: PolledState; refresh: () => void } {
  const [state, setState] = useState<PolledState>(EMPTY);
  const key = `${catalog}|${classes.join(",")}`;
  const seen = useRef<SeenByClass>({ key: "", by: {} });
  const poll = useCallback(async () => {
    if (!catalog) return;
    setState(await pollCatalog(catalog, classes, key, seen));
  }, [catalog, key]);  // eslint-disable-line react-hooks/exhaustive-deps
  usePollLoop(catalog, key, poll, () => { seen.current = { key, by: {} }; setState(EMPTY); });
  const refresh = useCallback(() => { poll().catch(() => {}); }, [poll]);
  return { state, refresh };
}

/** Restarts on a new catalog or class set: forgets what was seen, then polls now and every POLL_MS while visible. */
function usePollLoop(catalog: string | null, key: string, poll: () => Promise<void>, reset: () => void): void {
  useEffect(() => {
    reset();
    if (!catalog) return;
    return startPolling(poll);
  }, [key, poll]);  // eslint-disable-line react-hooks/exhaustive-deps
}

function startPolling(poll: () => Promise<void>): () => void {
  let stop = false;
  const tick = () => { if (!stop && document.visibilityState !== "hidden") poll().catch(() => {}); };
  tick();
  const id = window.setInterval(tick, POLL_MS);
  const onVis = () => { if (document.visibilityState === "visible") tick(); };
  document.addEventListener("visibilitychange", onVis);
  return () => { stop = true; window.clearInterval(id); document.removeEventListener("visibilitychange", onVis); };
}

async function pollCatalog(catalog: string, classes: ClassSlug[], key: string, seen: MutableRefObject<SeenByClass>): Promise<PolledState> {
  if (seen.current.key !== key) seen.current = { key, by: {} };
  const polls = await Promise.all(classes.map((cls) =>
    pollOne(catalog, cls, seen.current.by[cls] ?? { runId: null, notes: [] }).then((x) => ({ cls, ...x }))));
  for (const p of polls) seen.current.by[p.cls] = p.seen;
  return mergePolls(polls, classes);
}

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

function mergePolls(polls: ClassPoll[], classes: ClassSlug[]): PolledState {
  const merged: PolledState = { run: null, last: null, notes: [], runs: [], recent: {}, slots: null,
    now: new Date().toISOString(), classes };
  for (const p of polls) mergePoll(merged, p, classes);
  merged.runs.sort((a, b) => a.created_at.localeCompare(b.created_at));
  return merged;
}

function mergePoll(merged: PolledState, { cls, d, seen }: ClassPoll, classes: ClassSlug[]): void {
  merged.runs = [...merged.runs, ...liveRunsOf(d, seen).map((r) => tagRun(r, cls, classes))];
  if (d.run && !merged.run) { merged.run = tagRun(d.run, cls, classes); merged.notes = seen.notes; }
  if (d.last && (!merged.last || (d.last.ended_at ?? "") > (merged.last.ended_at ?? ""))) {
    merged.last = tagRun(d.last, cls, classes);
    if (!merged.run) merged.notes = seen.notes;
  }
  merged.recent = { ...merged.recent, ...(d.recent ?? {}) };
  merged.slots = merged.slots ?? d.slots ?? null;
  merged.now = d.now;
}

/** An older server has only `run`: it is the one live run. */
function liveRunsOf(d: CurrentRun, seen: Seen): LiveRun[] {
  return d.runs ?? (d.run ? [{ ...d.run, notes: seen.notes, queue: { place: null, start_in_min: null, left_min: null, minutes_so_far: null } }] : []);
}

/** With several classes polled, a run carries its class (and the class is remembered for its links). */
function tagRun<T extends AgentRun | null>(r: T, cls: ClassSlug, classes: ClassSlug[]): T {
  if (!r || classes.length < 2) return r;
  noteRunClass(r.run_id, cls);
  return { ...r, cls };
}

/** When the config can't be read (an older server, a network error), runs are off and buttons open the prompt. */
export const OFF: AgentConfig = { enabled: false, off_reason: "the Studio's server doesn't offer runs", agent_name: "Remote AI rule generator",
  k2_url: null, agent: null, minutes: 90, prompt_users: [] };
let configOnce: Promise<AgentConfig> | null = null;

export function useAgentConfig(): AgentConfig | null {
  const [config, setConfig] = useState<AgentConfig | null>(null);
  useEffect(() => { let live = true; void loadAgentConfig().then((c) => { if (live) setConfig(c); }); return () => { live = false; }; }, []);
  return config;
}

export function loadAgentConfig(): Promise<AgentConfig> {
  configOnce ??= agentApi.config().then((c) => (c && typeof c.enabled === "boolean" ? c : OFF), () => OFF);
  return configOnce;
}
/** Tests: forget the cached config. */
export function resetAgentConfig(): void { configOnce = null; }

/** A run's class before its words when several classes are shown ("LearningProgram: Claude is working on Name"). */
export function classPrefix(r: AgentRun | null | undefined, classes: ClassSlug[]): string {
  return r?.cls && classes.length > 1 ? `${CLASS_NAME[r.cls]}: ` : "";
}

export const isLive = (run: AgentRun | null): boolean => !!run && LIVE.includes(run.state);
