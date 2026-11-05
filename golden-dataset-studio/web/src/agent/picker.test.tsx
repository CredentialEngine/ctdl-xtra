// One-rule runs (docs/qrspi/one-rule-runs/03-spec.md §1.1, §1.2, §1.7): the "Run with Claude?" picker, ✦ Improve on a
// sidebar row, the queue in the run bar, the sidebar and the AI runs panel, and the UI never saying "goal".
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { RulesResponse, RuleSummary } from "../api/types";
import { RuleList } from "../rules/RuleList";
import { setIdentity } from "../shell/reviewer";
import { useAiStat } from "./AiStat";
import { ordinal, waitingWords, type AgentRun, type CurrentRun, type LiveRun, type Picker, type Queue } from "./api";
import { RunBar } from "./RunBar";
import { OPEN_RUN_DIALOG, RunDialog, RunDialogHost, openRunDialog } from "./RunDialog";
import { RunsPanel } from "./RunsPanel";
import { AgentProvider, resetAgentConfig } from "./state";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const PICKER: Picker = {
  total_rules: 44, ticked: 2, note: "1 of 2 AI runs is working, so this one starts now.",
  rules: [
    { rule: "course-description", name: "Description", status: "needs work", reviewed: 20, total: 1062, ticked: true, why: "3 open, 4 comments" },
    { rule: "course-credit-value", name: "Credit Value", status: "needs work", reviewed: 1, total: 1062, ticked: true, why: "1 open" },
    { rule: "course-subject-webpage", name: "Subject Webpage", status: "needs work", reviewed: 14, total: 1062, ticked: false,
      why: "Being improved in Seth Alt's run, 4 min", held_by: { run_id: "r-seth", started_by: "Seth Alt", since: "2026-11-06T15:35:00Z", minutes: 4 } },
    { rule: "course-code", name: "Coded Notation", status: "in review", reviewed: 40, total: 1062, ticked: false, why: "nothing open" },
  ],
};
const RUN: AgentRun = {
  run_id: "r-1", catalog: "avc-x", catalog_short: "avc", scope: { kind: "rules", rules: ["course-description"] },
  rule_names: { "course-description": "Description" }, started_by: "Eric Riddoch", created_at: "2026-11-06T15:39:00Z",
  updated_at: "2026-11-06T15:39:00Z", deadline: "", state: "waiting", sent_at: null, next_try_at: null,
  k2: { url: "", agent: "", delivery_id: null }, ruleset_before: 9, ruleset_after: null, outcome: null, ended_at: null, ended_by: null,
  fallback_reason: null,
};
const WAITING: LiveRun = { ...RUN, notes: [], queue: { place: 2, start_in_min: 6, left_min: null, minutes_so_far: null } };
const WORKING: LiveRun = { ...RUN, run_id: "r-0", started_by: "Jared Diener", state: "running", sent_at: "2026-11-06T15:36:00Z",
  scope: { kind: "rules", rules: ["course-credit-value"] }, rule_names: { "course-credit-value": "Credit Value" },
  notes: [{ at: "2026-11-06T15:37:00Z", kind: "note", text: "Reading", by: "agent" }],
  queue: { place: null, start_in_min: null, left_min: 2, minutes_so_far: 4 } };
const QUEUE: Queue = {
  cap: 2, median_min: 6, from_runs: 10, note: "Estimates use the last 10 runs, which took 6 min each (median). Two runs work at a time.",
  working: [{ run: "r-0", catalog: "avc", catalog_name: "AVC", rules: ["course-credit-value"], rule_names: ["Credit Value"], started_by: "Jared Diener",
              since: "2026-11-06T15:36:00Z", minutes_so_far: 4, left_min: 2 },
            { run: "r-m", catalog: "marshall", catalog_name: "Marshall", rules: ["a", "b"], rule_names: ["Credit Value", "Description"],
              started_by: "Seth Alt", since: "2026-11-06T15:38:00Z", minutes_so_far: 1, left_min: 5 }],
  waiting: [{ run: "r-w", catalog: "avc", catalog_name: "AVC", rules: ["s"], rule_names: ["Subject Webpage"], started_by: "Eric Riddoch",
              since: "2026-11-06T15:39:00Z", place: 1, start_in_min: 2 },
            { run: "r-1", catalog: "avc", catalog_name: "AVC", rules: ["course-description"], rule_names: ["Description"], started_by: "Eric Riddoch",
              since: "2026-11-06T15:40:00Z", place: 2, start_in_min: 6 }],
};
const NOW = "2026-11-06T15:40:00Z";

let current: CurrentRun;
let picker: Picker | null;
let startAnswer: { status: number; body: unknown };
const posts: { url: string; body: unknown }[] = [];
const respond = (status: number, body: unknown) =>
  Promise.resolve(new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } }));

beforeEach(() => {
  resetAgentConfig();
  posts.length = 0;
  picker = PICKER;
  startAnswer = { status: 201, body: { run: RUN, queue: { place: 1, start_in_min: 0 } } };
  current = { run: null, last: null, notes: [], since: 0, now: NOW, runs: [], recent: {}, slots: undefined };
  vi.stubGlobal("fetch", (url: string, init?: RequestInit) => {
    if (init?.method === "POST") { posts.push({ url, body: JSON.parse(String(init.body)) }); return respond(startAnswer.status, startAnswer.body); }
    if (url === "/api/agent-runs/config") return respond(200, { enabled: true, off_reason: null, agent_name: "Remote AI rule generator",
      k2_url: null, agent: null, minutes: 90, prompt_users: [], cap: 2 });
    if (url.includes("/agent-runs/current")) return respond(200, current);
    if (url.endsWith("/rules/picker")) return picker ? respond(200, picker) : respond(404, { detail: "Not Found" });
    if (url.endsWith("/rules")) return respond(200, RULES);
    if (url === "/api/agent-runs/queue") return respond(200, QUEUE);
    if (url.includes("/agent-runs?")) return respond(200, []);
    return respond(404, { detail: "no" });
  });
  setIdentity("Eric Riddoch", "engineer");
});

let host: HTMLDivElement, root: Root;
beforeEach(() => { host = document.createElement("div"); document.body.appendChild(host); root = createRoot(host); });
afterEach(() => { act(() => root.unmount()); host.remove(); vi.unstubAllGlobals(); vi.restoreAllMocks(); });
const flush = () => act(async () => { for (let i = 0; i < 6; i++) await Promise.resolve(); });
const boxes = () => [...document.querySelectorAll<HTMLInputElement>("[data-testid=run-picker] input[type=checkbox]")];
const runBtn = () => [...document.querySelectorAll<HTMLButtonElement>(".ac-foot button")].find((b) => b.textContent?.startsWith("Run on"))!;

const summary = (o: Partial<RuleSummary>): RuleSummary => ({
  rule_id: "course-description", kind: "property", version: 2, title: "Description", subtitle: "ceterms:description",
  ctdl_property: "ceterms:description", property_label: "Description", locator: null, status: "needs work",
  reviewed: 20, total: 1062, open_wrong: 3, open_missing: 0, questions: 0, approved_by: null, approved_at: null, comments: 4, ...o });
const RULES: RulesResponse = { extraction: "rs-0009", ruleset_version: 9, groups: [{ id: "req", kind: "property", label: "Required",
  collapsed: false, approved: 0, rules: [summary({}), summary({ rule_id: "course-code", title: "Coded Notation", status: "in review",
    open_wrong: 0, comments: 0 })] }] };

async function dialog(initial: string[] | null = null) {
  await act(async () => root.render(<AgentProvider catalog="avc"><RunDialog catalog="avc" initial={initial} onClose={() => {}} /></AgentProvider>));
  await flush();
}

describe("Run with Claude? (the rule picker)", () => {
  it("ticks the rules that need work, lists the rest unticked, and says where the run will stand", async () => {
    await dialog();
    expect(document.querySelector(".run-ask p")!.textContent).toBe(
      "Tick the rules you want improved. Claude may also make small changes to other rules when that helps, and every check covers all 44 rules.");
    expect([...document.querySelectorAll(".run-pick-list .panel-title")].map((t) => t.textContent)).toEqual(["Need work", "Nothing open"]);
    expect(boxes().map((b) => [b.getAttribute("aria-label"), b.checked])).toEqual([
      ["Description", true], ["Credit Value", true], ["Subject Webpage", false], ["Coded Notation", false]]);
    expect([...document.querySelectorAll(".run-pick .id")].map((d) => d.textContent)).toEqual([
      "3 open, 4 comments", "1 open", "Being improved in Seth Alt's run, 4 min", "nothing open"]);
    expect(document.querySelector(".run-note")!.textContent).toBe("1 of 2 AI runs is working, so this one starts now.");
    expect(runBtn().textContent).toBe("Run on 2 rules");
  });

  it("can't tick a rule another live run is improving", async () => {
    await dialog(["course-subject-webpage", "course-code"]);
    const held = boxes()[2];
    expect(held.disabled).toBe(true);
    expect(held.checked).toBe(false);
    expect(held.closest(".run-pick")!.className).toContain("held");
    expect(boxes().filter((b) => b.checked).map((b) => b.getAttribute("aria-label"))).toEqual(["Coded Notation"]);
  });

  it("starts a run on the ticked rules", async () => {
    await dialog();
    await act(async () => boxes()[3].click());  // tick Coded Notation too
    await act(async () => boxes()[0].click());  // untick Description
    expect(runBtn().textContent).toBe("Run on 2 rules");
    await act(async () => runBtn().click());
    await flush();
    expect(posts).toEqual([{ url: "/api/catalogs/avc/agent-runs", body: { scope: { kind: "rules", rules: ["course-credit-value", "course-code"] },
      author: "Eric Riddoch", studio_url: location.origin + location.pathname } }]);
  });

  it("opens with only the asked-for rule ticked (✦ Improve on a row, Run again)", async () => {
    await dialog(["course-credit-value"]);
    expect(boxes().filter((b) => b.checked).map((b) => b.getAttribute("aria-label"))).toEqual(["Credit Value"]);
    expect(runBtn().textContent).toBe("Run on 1 rule");
  });

  it("falls back to the rules list when the server has no picker", async () => {
    picker = null;
    await dialog();
    expect(boxes().map((b) => [b.getAttribute("aria-label"), b.checked])).toEqual([["Description", true], ["Coded Notation", false]]);
    expect([...document.querySelectorAll(".run-pick .id")].map((d) => d.textContent)).toEqual(["3 open, 4 comments", "Nothing open"]);
  });

  it("is opened from anywhere by openRunDialog", async () => {
    await act(async () => root.render(<AgentProvider catalog="avc"><RunDialogHost catalog="avc" /></AgentProvider>));
    await flush();
    expect(document.querySelector("#run-ask-h")).toBeNull();
    await act(async () => openRunDialog(["course-code"]));
    await flush();
    expect(document.querySelector("#run-ask-h")!.textContent).toBe("Run with Claude?");
    expect(boxes().filter((b) => b.checked).map((b) => b.getAttribute("aria-label"))).toEqual(["Coded Notation"]);
  });
});

describe("✦ Improve and the AI status on a sidebar row", () => {
  function List({ onImprove }: { onImprove: (id: string) => void }) {
    const aiStat = useAiStat();
    return <RuleList rules={RULES} active="course-code" onPick={() => {}} aiStat={aiStat} onImprove={(r) => onImprove(r.rule_id)} />;
  }
  it("is the Discuss button with the spark, its tooltip the app's Tip, and opens the picker on that rule", async () => {
    const asked: unknown[] = [];
    await act(async () => root.render(<AgentProvider catalog="avc"><List onImprove={(id) => openRunDialog([id])} /></AgentProvider>));
    await flush();
    const btn = host.querySelector<HTMLButtonElement>("[data-rule=course-description] .rule-improve .rule-talk-btn")!;
    expect(btn.textContent).toBe("Improve");
    expect(btn.querySelector(".ico")).toBeTruthy();
    await act(async () => btn.parentElement!.dispatchEvent(new MouseEvent("mouseover", { bubbles: true })));
    expect(document.querySelector(".evx-tip")!.textContent).toBe(
      "Improve Description with AIClaude may make small changes to other rules if this one needs it. Every check covers all 2 rules.");
    const on = (e: Event) => asked.push((e as CustomEvent).detail);
    window.addEventListener(OPEN_RUN_DIALOG, on);
    await act(async () => btn.click());
    window.removeEventListener(OPEN_RUN_DIALOG, on);
    expect(asked).toEqual([{ rules: ["course-description"] }]);
  });

  it("shows a working run's minutes, a waiting run's place, and decisions waiting", async () => {
    current = { ...current, runs: [{ ...WORKING, scope: { kind: "rules", rules: ["course-description"] } }] };
    await act(async () => root.render(<AgentProvider catalog="avc"><List onImprove={() => {}} /></AgentProvider>));
    await flush();
    const stat = () => host.querySelector("[data-rule=course-description] [data-testid=ai-stat]")!;
    expect(stat().textContent).toBe("4 min");
    expect(stat().querySelector(".run-pulse")).toBeTruthy();
    act(() => root.unmount());
    root = createRoot(host);
    current = { ...current, runs: [WAITING] };
    await act(async () => root.render(<AgentProvider catalog="avc"><List onImprove={() => {}} /></AgentProvider>));
    await flush();
    expect(stat().textContent).toBe("◷2nd");
    expect(stat().getAttribute("title")).toBe("Waiting for a free place: 2nd in line, about 6 min");
    act(() => root.unmount());
    root = createRoot(host);
    current = { ...current, runs: [], recent: { "course-code": { run_id: "r-old", state: "needs_you", outcome: null, started_by: "Jared Diener",
      created_at: NOW, ended_at: NOW, to_do_count: 1 } } };
    await act(async () => root.render(<AgentProvider catalog="avc"><List onImprove={() => {}} /></AgentProvider>));
    await flush();
    const sig = host.querySelector("[data-rule=course-code] [data-testid=ai-stat]")!;
    expect(sig.className).toBe("stat sig");
    expect(sig.textContent).toBe("?\u00a01");
  });
});

describe("The queue", () => {
  it("words a place in line", () => {
    expect([1, 2, 3, 4, 11, 12, 13, 21, 22].map(ordinal)).toEqual(["1st", "2nd", "3rd", "4th", "11th", "12th", "13th", "21st", "22nd"]);
    expect(waitingWords(WAITING, "Eric Riddoch")).toBe("Your run on Description is 2nd in line. It should start in about 6 min.");
    expect(waitingWords(WAITING, "Jared Diener")).toBe("Eric Riddoch's run on Description is 2nd in line. It should start in about 6 min.");
  });

  it("shows in the run bar in sentences, with See the queue and Cancel", async () => {
    current = { ...current, runs: [WORKING, WAITING] };
    await act(async () => root.render(<AgentProvider catalog="avc"><RunBar catalog="avc" /></AgentProvider>));
    await flush();
    const bar = host.querySelector("[data-testid=run-bar]")!;
    expect(bar.querySelector(".run-text")!.textContent).toBe(
      "Claude is working on Credit Value. Your run on Description is 2nd in line. It should start in about 6 min.");
    expect(bar.textContent).not.toContain("·");
    expect([...bar.querySelectorAll(".run-actions button")].map((b) => b.textContent)).toEqual(["Watch", "See the queue", "Cancel"]);
    vi.spyOn(window, "confirm").mockReturnValue(true);
    await act(async () => [...bar.querySelectorAll<HTMLButtonElement>("button")].find((b) => b.textContent === "Cancel")!.click());
    await flush();
    expect(posts[0].url).toBe("/api/catalogs/avc/agent-runs/r-1/cancel");  // yours in line, not Jared's working run
  });

  it("shows in the AI runs panel: working now, waiting, and where the estimate comes from", async () => {
    await act(async () => root.render(<RunsPanel catalog="avc" initial={null} onClose={() => {}} />));
    await flush();
    expect(host.querySelector("#runs-h")!.textContent).toBe("AI runs");
    const working = host.querySelector("[data-testid=queue-working]")!;
    expect(working.querySelector("h3")!.textContent).toBe("Working now: 2 of 2 places");
    expect([...working.querySelectorAll(".runs-item")].map((i) => i.textContent)).toEqual([
      "WorkingAVC: Credit ValueJared Diener. Started 4 min ago, about 2 min left",
      "WorkingMarshall: Credit Value, DescriptionSeth Alt. Started 1 min ago, about 5 min left"]);
    const waiting = host.querySelector("[data-testid=queue-waiting]")!;
    expect([...waiting.querySelectorAll(".runs-item")].map((i) => i.textContent)).toEqual([
      "1st in lineAVC: Subject Webpage (yours)Eric Riddoch. Starts in about 2 min",
      "2nd in lineAVC: Description (yours)Eric Riddoch. Starts in about 6 min"]);
    expect(waiting.querySelector("p.faint")!.textContent).toBe(QUEUE.note);
    expect(host.textContent).not.toContain("·");
  });
});

describe("Wording", () => {
  // Eric didn't know the word (answers-pass5 #4): the UI says "rules to improve". Strings and JSX text only; the
  // contract's field names (`goal`) and comments may use it.
  // every source file of the app, as text (Vite's glob; tests excluded below)
  const files = (import.meta as unknown as { glob: (p: string, o: object) => Record<string, string> })
    .glob("../**/*.{ts,tsx}", { query: "?raw", import: "default", eager: true });
  /** The code without comments: strings and template literals kept, so their words are checked. */
  function uiText(code: string): string[] {
    const out: string[] = [];
    let i = 0;
    while (i < code.length) {
      const c = code[i];
      if (c === "/" && code[i + 1] === "/") { i = code.indexOf("\n", i); if (i < 0) break; continue; }
      if (c === "/" && code[i + 1] === "*") { i = code.indexOf("*/", i) + 2; continue; }
      if (c === '"' || c === "'" || c === "`") {
        let j = i + 1;
        while (j < code.length && code[j] !== c) j += code[j] === "\\" ? 2 : 1;
        out.push(code.slice(i + 1, j));
        i = j + 1;
        continue;
      }
      if (c === ">") {  // JSX text: between > and the next < or {
        const m = /^>([^<>{}=;()]*)[<{]/.exec(code.slice(i, i + 400));
        if (m && m[1].trim()) out.push(m[1]);
      }
      i++;
    }
    return out;
  }
  it("never says goal", () => {
    const names = Object.keys(files).filter((f) => !/\.test\.tsx?$/.test(f));
    expect(names.length).toBeGreaterThan(50);
    const hits = names.flatMap((f) => uiText(files[f]).filter((t) => /\bgoals?\b/i.test(t)).map((t) => `${f}: ${t}`));
    expect(hits).toEqual([]);
    // the scan does see UI text
    expect(uiText(files["./RunDialog.tsx"]).some((t) => t.includes("Tick the rules you want improved"))).toBe(true);
  });
});
