import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { RulesResponse } from "../api/types";
import { setIdentity } from "../shell/reviewer";
import type { AgentConfig, AgentRun, CurrentRun } from "./api";
import { FixBar, fixCounts } from "./FixBar";
import { RunBar } from "./RunBar";
import { RunButton } from "./RunButton";
import { OPEN_PROMPT } from "../prompt/PromptModal";
import { RunsPanel } from "./RunsPanel";
import { AgentProvider, resetAgentConfig } from "./state";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const CONFIG: AgentConfig = { enabled: true, off_reason: null, agent_name: "Remote AI rule generator",
  k2_url: "https://k2.example", agent: "golden-rules", minutes: 90, prompt_users: ["Eric Riddoch", "Seth Alt"] };
const RUN: AgentRun = {
  run_id: "20261028T031209Z-a1b2", catalog: "avc", scope: { kind: "needs_work", rules: ["course-description", "course-code"] },
  started_by: "Jared Diener", created_at: "2026-10-28T03:12:09Z", updated_at: "2026-10-28T03:12:10Z",
  deadline: "2026-10-28T04:42:09Z", state: "running", sent_at: "2026-10-28T03:12:10Z", next_try_at: null,
  k2: { url: "https://k2.example", agent: "golden-rules", delivery_id: "m_1" }, ruleset_before: 6, ruleset_after: null,
  outcome: null, ended_at: null, ended_by: null, fallback_reason: null,
};
const NOW = "2026-10-28T03:24:09Z";
const ENDED: AgentRun = { ...RUN, state: "failed", outcome: "Couldn't publish: BIOL110 needs an expected value",
  ended_at: "2026-10-28T03:20:00Z" };

let config: AgentConfig = CONFIG;
let current: CurrentRun = { run: null, last: null, notes: [], since: 0, now: NOW };
let startAnswer: { status: number; body: unknown } = { status: 201, body: { run: RUN } };
const posts: { url: string; body: unknown }[] = [];

function respond(status: number, body: unknown) {
  return Promise.resolve(new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } }));
}
beforeEach(() => {
  resetAgentConfig();
  config = CONFIG;
  current = { run: null, last: null, notes: [], since: 0, now: NOW };
  startAnswer = { status: 201, body: { run: RUN } };
  posts.length = 0;
  vi.stubGlobal("fetch", (url: string, init?: RequestInit) => {
    if (url === "/api/agent-runs/config") return respond(200, config);
    if (url.includes("/agent-runs/current")) return respond(200, current);
    if (url.endsWith("/agent-runs?limit=50")) return respond(200, [ENDED, { ...RUN, run_id: "20261027T200000Z-0000", state: "timed_out",
      outcome: null, ended_at: "2026-10-27T21:30:00Z" }]);
    if (url.endsWith(`/agent-runs/${ENDED.run_id}`)) return respond(200, { run: ENDED, summary: "## Decisions for Eric\n\n1. Advisory text\n",
      notes: [{ at: "2026-10-28T03:13:00Z", kind: "note", text: "Drafted course-description v3", by: "golden-rules agent" }] });
    if (url.endsWith(`/agent-runs/${ENDED.run_id}/prompt`)) return respond(200, { text: "# Improve 2 rules — AVC catalog" });
    if (init?.method === "POST") {
      posts.push({ url, body: JSON.parse(String(init.body)) });
      if (url.endsWith("/agent-runs")) return respond(startAnswer.status, startAnswer.body);
      return respond(200, { run: { ...RUN, state: "cancelled" } });
    }
    return respond(404, { detail: "no" });
  });
  setIdentity("Jared Diener", "sme");
  location.hash = "#/c/avc/rules";
});

let host: HTMLDivElement, root: Root;
beforeEach(() => { host = document.createElement("div"); document.body.appendChild(host); root = createRoot(host); });
afterEach(() => { act(() => root.unmount()); host.remove(); vi.unstubAllGlobals(); });

const flush = () => act(async () => { for (let i = 0; i < 5; i++) await Promise.resolve(); });
const buttons = () => [...document.querySelectorAll("button")];
const byText = (t: string) => buttons().find((b) => b.textContent?.includes(t));

// what the prompt modal was asked to show: the warning (null = none), in order
let prompts: (string | null)[] = [];
const onPrompt = (e: Event) => prompts.push((e as CustomEvent<{ warning: string | null }>).detail.warning);
beforeEach(() => { prompts = []; window.addEventListener(OPEN_PROMPT, onPrompt); });
afterEach(() => window.removeEventListener(OPEN_PROMPT, onPrompt));

function button() {
  return (
    <AgentProvider catalog="avc">
      <RunButton catalog="avc" scope={{ kind: "needs_work" }} label="Improve all 2 rules with Claude"
        confirm="Improve 2 rules on AVC with Claude?" />
    </AgentProvider>
  );
}

describe("RunButton", () => {
  it("asks once, then starts a run for the person who pressed it", async () => {
    await act(async () => root.render(button()));
    await flush();
    await act(async () => byText("Improve all 2 rules")!.click());
    expect(document.querySelector("#run-ask-h")?.textContent).toBe("Run with Claude?");
    await act(async () => byText("Run")!.click());
    await flush();
    expect(posts[0]).toEqual({ url: "/api/catalogs/avc/agent-runs", body: { scope: { kind: "needs_work" }, author: "Jared Diener" } });
    expect(host.querySelector(".run-caret")).toBeNull();  // Jared isn't a prompt user: no split button
  });

  it("falls back to the prompt with a warning when the generator can't be reached", async () => {
    startAnswer = { status: 502, body: { fallback: "prompt", reason: "K2 didn't answer in 15 s" } };
    await act(async () => root.render(button()));
    await flush();
    await act(async () => byText("Improve all 2 rules")!.click());
    await act(async () => byText("Run")!.click());
    await flush();
    expect(prompts).toEqual(["K2 didn't answer in 15 s"]);
  });

  it("opens the prompt directly when runs are off", async () => {
    config = { ...CONFIG, enabled: false, off_reason: "no K2 server configured" };
    await act(async () => root.render(button()));
    await flush();
    await act(async () => byText("Improve all 2 rules")!.click());
    expect(document.querySelector("#run-ask-h")).toBeNull();
    expect(prompts).toEqual([null]);
  });

  it("gives prompt users a split button with Open the prompt", async () => {
    setIdentity("Eric Riddoch", "engineer");
    await act(async () => root.render(button()));
    await flush();
    await act(async () => host.querySelector<HTMLButtonElement>(".run-caret")!.click());
    const items = [...host.querySelectorAll("[role=menuitem]")].map((b) => b.textContent);
    expect(items).toEqual(["Run on the Remote AI rule generator", "Open the prompt"]);
    await act(async () => byText("Open the prompt")!.click());
    expect(prompts).toEqual([null]);
  });

  it("is disabled while the catalog has a live run, saying what runs", async () => {
    current = { ...current, run: RUN };
    await act(async () => root.render(button()));
    await flush();
    const b = byText("Improve all 2 rules")!;
    expect(b.disabled).toBe(true);
    expect(b.title).toBe("Claude is improving 2 rules · started by Jared Diener · 12 min");
  });
});

describe("RunBar", () => {
  it("shows the live run to everyone, with Watch and Cancel", async () => {
    current = { run: RUN, last: null, since: 0, now: NOW, notes: [
      { at: "2026-10-28T03:12:09Z", kind: "studio", text: "Started by Jared Diener", by: "Golden Dataset Studio" },
      { at: "2026-10-28T03:23:29Z", kind: "note", text: "Course description: changing the locator", by: "golden-rules agent" }] };
    await act(async () => root.render(<AgentProvider catalog="avc"><RunBar catalog="avc" /></AgentProvider>));
    await flush();
    const bar = host.querySelector("[data-testid=run-bar]")!;
    expect(bar.querySelector(".run-text")!.textContent).toBe(
      "Claude is improving 2 rules · started by Jared Diener · 12 min · last update 40 s ago");
    await act(async () => byText("Watch")!.click());
    const notes = [...document.querySelectorAll(".run-notes li span")].map((s) => s.textContent);
    expect(notes).toEqual(["Started by Jared Diener", "Course description: changing the locator"]);
    expect(byText("Cancel")).toBeTruthy();
  });

  it("shows how the last run ended, with Compare, until dismissed", async () => {
    current = { run: null, since: 0, now: NOW, notes: [], last: { ...RUN, state: "finished", outcome: "Published ruleset v7",
      ended_at: "2026-10-28T03:20:00Z", ruleset_after: 7 } };
    await act(async () => root.render(<AgentProvider catalog="avc"><RunBar catalog="avc" /></AgentProvider>));
    await flush();
    expect(host.querySelector(".run-text")!.textContent).toContain("Claude finished: Published ruleset v7");
    expect(host.querySelector<HTMLAnchorElement>("a.btn")!.getAttribute("href")).toBe("#/c/avc/compare?a=6&b=7");
    await act(async () => host.querySelector<HTMLButtonElement>(".run-x")!.click());
    expect(host.querySelector("[data-testid=run-bar]")).toBeNull();
  });
});

describe("FixBar", () => {
  const rule = (id: string, status: "needs work" | "approved" | "in review", w: number, m: number, q = 0) => ({
    rule_id: id, kind: "field" as const, version: 1, title: id, subtitle: "", ctdl_property: null, property_label: null,
    locator: null, status, reviewed: 1, total: 1, open_wrong: w, open_missing: m, questions: q, approved_by: null,
    approved_at: null, comments: 0 });
  const rules: RulesResponse = { extraction: "e", ruleset_version: 6, groups: [{ kind: "field", label: "Fields", approved: 1,
    rules: [rule("a", "needs work", 3, 1), rule("b", "needs work", 0, 2, 1), rule("c", "approved", 0, 0), rule("d", "in review", 0, 0)] }] };

  it("counts what needs work and leads with improving all of it", async () => {
    expect(fixCounts(rules)).toEqual({ rules: 2, wrong: 3, missing: 3, questions: 1 });
    await act(async () => root.render(<AgentProvider catalog="avc"><FixBar catalog="avc" name="AVC" rules={rules} /></AgentProvider>));
    await flush();
    expect(host.querySelector(".fb-t")!.textContent).toBe("2 rules need work · 3 wrong · 3 missing · 1 question for the institution");
    expect(byText("Improve all 2 rules with Claude")).toBeTruthy();
  });

  it("says when nothing needs work", async () => {
    const clear = { ...rules, groups: [{ ...rules.groups[0], rules: [rule("c", "approved", 0, 0)] }] };
    await act(async () => root.render(<AgentProvider catalog="avc"><FixBar catalog="avc" name="AVC" rules={clear} /></AgentProvider>));
    expect(host.querySelector(".fb-t")!.textContent).toBe("Nothing to fix: no rule has open wrong or missing verdicts.");
    expect(byText("Past AI runs")).toBeTruthy();
  });
});

describe("RunsPanel", () => {
  it("lists past runs and opens one with Claude's report, its notes and its prompt", async () => {
    await act(async () => root.render(<RunsPanel catalog="avc" initial={null} onClose={() => {}} />));
    await flush();
    const items = [...host.querySelectorAll(".runs-item")];
    expect(items.map((b) => b.querySelector(".runs-state")!.textContent)).toEqual(["Didn't finish", "Timed out"]);
    expect(items[0].querySelector(".runs-what")!.textContent).toBe("Couldn't publish: BIOL110 needs an expected value");
    expect(items[1].querySelector(".runs-what")!.textContent).toBe("improving 2 rules");
    await act(async () => (items[0] as HTMLButtonElement).click());
    await flush();
    const d = host.querySelector("[data-testid=run-detail]")!;
    expect(d.querySelector(".runs-report h2")!.textContent).toBe("Decisions for Eric");
    expect([...d.querySelectorAll(".run-notes li span")].map((x) => x.textContent)).toEqual(["Drafted course-description v3"]);
    await act(async () => byText("Show the prompt")!.click());
    await flush();
    expect(d.querySelector(".runs-prompt")!.textContent).toBe("# Improve 2 rules — AVC catalog");
    await act(async () => byText("← Past AI runs")!.click());
    expect(host.querySelectorAll(".runs-item").length).toBe(2);
  });
});
