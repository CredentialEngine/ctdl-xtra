import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { api } from "../api/client";
import type { CatalogDetail, RulesResponse, RuleSummary } from "../api/types";
import { Tour, useTour } from ".";
import {
  clip, makeCtx, markSeen, placeCard, SEEN_KEY, shouldAutoOpen, TourSession, union, type KeyStore, type Nav, type SessionStep,
  type TourCtx, type Waiter,
} from "./model";
import { STEPS } from "./steps";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const catalog = { catalog: "avc-x", short: "avc", name: "AVC", institution: "AVC", logo: null, crawl: "2026-10-12T20-59-13Z",
  crawl_started: "", pages: 1467, extraction: "rs-0002", ruleset_version: 2, extractions: [], rulesets: [], authors: [],
  pane_css: "", root: "" } as CatalogDetail;

const rule = (o: Partial<RuleSummary>): RuleSummary => ({
  rule_id: "course-description", kind: "field", version: 2, title: "Description", subtitle: "ceterms:description",
  ctdl_property: "ceterms:description", property_label: "Description", locator: "locator-course-page", status: "in review",
  reviewed: 14, total: 1062, open_wrong: 0, open_missing: 0, questions: 0, approved_by: null, approved_at: null, comments: 0, ...o,
});
const rules: RulesResponse = { extraction: "rs-0002", ruleset_version: 2, groups: [
  { kind: "page", label: "Page rules", approved: 0, rules: [rule({ rule_id: "course-page", kind: "page", title: "Course pages", status: "needs work", open_wrong: 2 })] },
  { kind: "locator", label: "Record locators", approved: 0, rules: [
    rule({ rule_id: "locator-course-page", kind: "locator", title: "One course per course page" }),
    rule({ rule_id: "locator-program-requirement", kind: "locator", title: "One course per requirement line" })] },
  { kind: "field", label: "Field rules", approved: 0, rules: [rule({}), rule({ rule_id: "stub-name", title: "Name", ctdl_property: "ceterms:name" })] },
] };

function memStore(): KeyStore & { data: Map<string, string> } {
  const data = new Map<string, string>();
  return { data, getItem: (k) => data.get(k) ?? null, setItem: (k, v) => void data.set(k, v) };
}

describe("opens once per browser", () => {
  it("opens the first time, not after", () => {
    const s = memStore();
    expect(shouldAutoOpen(s)).toBe(true);
    markSeen(s);
    expect(s.data.get(SEEN_KEY)).toBe("1");
    expect(shouldAutoOpen(s)).toBe(false);
  });
  it("never opens by itself without working storage, and never throws", () => {
    const broken: KeyStore = { getItem: () => { throw new Error("denied"); }, setItem: () => { throw new Error("denied"); } };
    expect(shouldAutoOpen(broken)).toBe(false);
    expect(shouldAutoOpen(null)).toBe(false);
    expect(() => markSeen(broken)).not.toThrow();
  });
});

describe("where the tour works", () => {
  it("keeps the reader's field rule and row", () => {
    const c = makeCtx(catalog, "#/c/avc/rules/stub-name?row=CFE101", rules);
    expect(c.base).toBe("#/c/avc/rules/stub-name?row=CFE101");
    expect(c.ruleId).toBe("stub-name");
    expect(c.headText["stub-name"]).toBe("ceterms:name");
  });
  it("uses the default rule from another tab or a non-field rule", () => {
    for (const o of ["#/c/avc/compare", "#/c/avc/rules/course-page", "#/"]) {
      const c = makeCtx(catalog, o, rules);
      expect(c.base).toBe("#/c/avc/rules/course-description");
      expect(c.ruleId).toBe("course-description");
    }
  });
  it("prefers the program-requirement locator, and has Compare only with two versions", () => {
    const c = makeCtx(catalog, "#/", rules);
    expect(c.locator).toBe("#/c/avc/rules/locator-program-requirement");
    expect(c.compare).toBe("#/c/avc/compare");
    const one = makeCtx({ ...catalog, ruleset_version: 1 }, "#/", { ...rules, groups: rules.groups.filter((g) => g.kind !== "locator") });
    expect(one.locator).toBeNull();
    expect(one.compare).toBeNull();
  });
});

describe("the Approve step", () => {
  it("goes to a rule Approve is greyed out on, keeping the reader's own if it is one", () => {
    const c = makeCtx(catalog, "#/", rules);
    expect(c.blocked).toBe("#/c/avc/rules/course-page");
    expect(c.blockedId).toBe("course-page");
    const blockedGroups = rules.groups.map((g) => g.kind !== "field" ? g
      : { ...g, rules: g.rules.map((r) => r.rule_id === "stub-name" ? { ...r, open_wrong: 1, status: "needs work" as const } : r) });
    const own = makeCtx(catalog, "#/c/avc/rules/stub-name", { ...rules, groups: blockedGroups });
    expect(own.blocked).toBe(own.base);
    const none = makeCtx(catalog, "#/", { ...rules, groups: rules.groups.filter((g) => g.kind === "field") });
    expect(none.blocked).toBe(none.base);
  });
});

describe("the steps", () => {
  it("light the prompt's feedback: the lines from '### Open annotations' to the next heading", () => {
    const by = (id: string) => STEPS.find((s) => s.id === id)!;
    document.body.innerHTML = `<pre class="prompt-pre">${["## Rule `x` v2", "| What | a |", "### Open annotations (1)",
      "| # | Verdict |", "| 1 | WRONG |", "### Marked correct", "| A | b |"].map((l) => `<span class="ln">${l}\n</span>`).join("")}</pre>`;
    const feedback = by("prompt").targets[0] as () => Element[];
    expect(feedback().map((e) => e.textContent?.trim())).toEqual(["### Open annotations (1)", "| # | Verdict |", "| 1 | WRONG |"]);
    document.body.innerHTML = "";
  });
  it("are the eleven of spec §7.8, in order: the Prompt before Compare", () => {
    expect(STEPS.map((s) => s.id)).toEqual(["rules", "kinds", "rows", "verdict", "comment", "page", "locator", "improve",
                                            "prompt", "compare", "approve"]);
    for (const s of STEPS) { expect(s.title).toBeTruthy(); expect(s.targets.length).toBeGreaterThan(0); }
  });
  it("go to the locator view and to Compare, and say so when the catalog has neither", () => {
    const ctx = makeCtx(catalog, "#/", rules);
    const by = (id: string) => STEPS.find((s) => s.id === id)!;
    expect(by("locator").route(ctx)).toBe(ctx.locator);
    expect(by("compare").route(ctx)).toBe("#/c/avc/compare");
    expect(by("prompt").route(ctx)).toBe(`#/c/avc/prompt?rule=${ctx.ruleId}`);
    const bare = { ...ctx, locator: null, compare: null };
    expect(by("locator").route(bare)).toBeNull();
    expect(by("compare").route(bare)).toBeNull();
    expect(by("compare").absent(bare)).toBeTruthy();
  });
});

// --- undo bookkeeping ---------------------------------------------------------------------------------------------
function fakeNav(start: string): Nav & { log: string[] } {
  let h = start;
  const log: string[] = [];
  return { log, get: () => h, set: (x) => { h = x; log.push(x); } };
}
/** A waiter the test releases by hand. */
function manualWait() {
  const pending: { ready: () => boolean; then: () => void; live: boolean }[] = [];
  const wait: Waiter = (ready, then) => { const p = { ready, then, live: true }; pending.push(p); return () => { p.live = false; }; };
  const flush = () => { for (const p of pending.splice(0)) if (p.live && p.ready()) p.then(); };
  return { wait, flush, pending };
}
const ctx0 = { catalog: "avc", base: "#/c/avc/rules/x" } as TourCtx;

describe("TourSession", () => {
  it("goes where each step needs, undoes the step it leaves, and goes back on close", () => {
    const nav = fakeNav("#/c/avc/golden");
    const w = manualWait();
    const s = new TourSession(nav, w.wait);
    const did: string[] = [];
    const a: SessionStep = { route: (c) => c.base, arrive: () => { did.push("a+"); return () => did.push("a-"); } };
    const b: SessionStep = { route: () => "#/c/avc/compare", arrive: () => { did.push("b+"); return () => did.push("b-"); } };
    s.enter(a, ctx0);
    expect(nav.get()).toBe("#/c/avc/rules/x");
    expect(did).toEqual([]);
    w.flush();
    expect(did).toEqual(["a+"]);
    s.enter(b, ctx0);
    expect(did).toEqual(["a+", "a-"]);
    w.flush();
    s.enter(a, ctx0);
    w.flush();
    expect(did).toEqual(["a+", "a-", "b+", "b-", "a+"]);
    s.close();
    expect(did[did.length - 1]).toBe("a-");
    expect(nav.get()).toBe("#/c/avc/golden");
    expect(nav.log).toEqual(["#/c/avc/rules/x", "#/c/avc/compare", "#/c/avc/rules/x", "#/c/avc/golden"]);
  });
  it("doesn't act for a step left before the screen was ready", () => {
    const nav = fakeNav("#/c/avc/rules/x");
    const w = manualWait();
    const s = new TourSession(nav, w.wait);
    const did: string[] = [];
    s.enter({ route: (c) => c.base, arrive: () => { did.push("late"); } }, ctx0);
    s.close();
    w.flush();
    expect(did).toEqual([]);
    expect(nav.log).toEqual([]); // already there: never navigated
  });
  it("stays put for a step with nowhere to go, and survives an undo that throws", () => {
    const nav = fakeNav("#/c/avc/rules/x");
    const w = manualWait();
    const s = new TourSession(nav, w.wait);
    s.enter({ route: () => "#/c/avc/prompt", arrive: () => () => { throw new Error("gone"); } }, ctx0);
    w.flush();
    s.enter({ route: () => null }, ctx0);
    expect(nav.get()).toBe("#/c/avc/prompt");
    s.close();
    expect(nav.get()).toBe("#/c/avc/rules/x");
  });
});

describe("placing the card", () => {
  const vp = { width: 1440, height: 900 };
  const card = { width: 372, height: 300 };
  it("goes beside the area on the first side with room", () => {
    expect(placeCard({ left: 0, top: 48, width: 292, height: 820 }, card, vp)).toMatchObject({ side: "right", left: 306 });
    expect(placeCard({ left: 820, top: 48, width: 620, height: 820 }, card, vp)).toMatchObject({ side: "left", left: 820 - 14 - 372 });
    expect(placeCard({ left: 292, top: 120, width: 600, height: 60 }, card, vp, ["below"])).toMatchObject({ side: "below", top: 194, left: 292 });
  });
  it("sits inside an area that fills the screen, and stays on screen", () => {
    const p = placeCard({ left: 0, top: 0, width: 1440, height: 900 }, card, vp);
    expect(p.side).toBe("inside");
    expect(p.left + card.width).toBeLessThanOrEqual(vp.width - 12);
    expect(p.top + card.height).toBeLessThanOrEqual(vp.height - 12);
  });
  it("clips to the viewport and joins areas", () => {
    expect(clip({ left: -10, top: 800, width: 100, height: 400 }, vp)).toEqual({ left: 0, top: 800, width: 90, height: 100 });
    expect(clip({ left: 0, top: 950, width: 100, height: 10 }, vp)).toBeNull();
    expect(union([{ left: 10, top: 10, width: 10, height: 10 }, { left: 30, top: 0, width: 5, height: 5 }]))
      .toEqual({ left: 10, top: 0, width: 25, height: 20 });
  });
});

// --- step actions on a stand-in screen ---------------------------------------------------------------------------------
describe("each action is undone when the step is left", () => {
  const by = (id: string) => STEPS.find((s) => s.id === id)!;
  afterEach(() => { document.body.innerHTML = ""; });

  it("✗ opens the row and Cancel closes it; the comment the same", () => {
    const clicks: string[] = [];
    document.body.innerHTML = `<div class="rows"><div class="row on"><div class="ctl3"><button class="cb no"></button>
      <button class="cb talk" data-tour="comment-button"></button></div></div></div>`;
    const row = document.querySelector(".row.on")!;
    const open = (cls: string) => () => { clicks.push(cls); row.insertAdjacentHTML("beforeend", `<div class="expand ${cls}"><button class="btn cancel"></button></div>`);
      row.querySelector(".btn.cancel")!.addEventListener("click", () => { clicks.push("cancel"); row.querySelector(".expand")!.remove(); }); };
    row.querySelector(".cb.no")!.addEventListener("click", open("wrong"));
    row.querySelector(".cb.talk")!.addEventListener("click", open("comment"));
    const undo1 = by("verdict").arrive!(ctx0);
    expect(row.querySelector(".expand.wrong")).not.toBeNull();
    (undo1 as () => void)();
    expect(row.querySelector(".expand")).toBeNull();
    const undo2 = by("comment").arrive!(ctx0);
    expect(row.querySelector(".expand.comment")).not.toBeNull();
    (undo2 as () => void)();
    expect(clicks).toEqual(["wrong", "cancel", "comment", "cancel"]);
  });

  it("switches the page pane to HTML and back; opens How this rule works and closes it; shows Approve's reason and hides it", () => {
    document.body.innerHTML = `<div data-tour="page-html-switch"><button class="on">Page</button><button>HTML</button></div>
      <details data-tour="how-it-works"><summary>How</summary></details>
      <span class="tipwrap" data-tour="approve" data-tip="Can't approve yet"><button class="btn approve" disabled></button></span>`;
    const [page, html] = document.querySelectorAll("button");
    const seen: string[] = [];
    page.addEventListener("click", () => seen.push("page"));
    html.addEventListener("click", () => seen.push("html"));
    (by("page").arrive!(ctx0) as () => void)();
    expect(seen).toEqual(["html", "page"]);
    const d = document.querySelector("details")!;
    const u = by("improve").arrive!(ctx0) as () => void;
    expect(d.open).toBe(true);
    u();
    expect(d.open).toBe(false);
    const tip = document.querySelector(".tipwrap")!;
    const u2 = by("approve").arrive!(ctx0) as () => void;
    expect(tip.classList.contains("show")).toBe(true);
    u2();
    expect(tip.classList.contains("show")).toBe(false);
  });

  it("leaves alone what the reader had open already", () => {
    document.body.innerHTML = `<details data-tour="how-it-works" open><summary>How</summary></details>`;
    expect(by("improve").arrive!(ctx0)).toBeUndefined();
    expect((document.querySelector("details") as HTMLDetailsElement).open).toBe(true);
  });
});

// --- the component ---------------------------------------------------------------------------------------------------------
describe("Tour", () => {
  let root: Root, host: HTMLDivElement;
  beforeEach(() => {
    host = document.createElement("div");
    document.body.appendChild(host);
    root = createRoot(host);
    vi.spyOn(api, "rules").mockResolvedValue(rules);
    vi.spyOn(Element.prototype, "getBoundingClientRect").mockReturnValue({ left: 10, top: 60, width: 280, height: 700, right: 290, bottom: 760, x: 10, y: 60, toJSON: () => ({}) } as DOMRect);
    vi.stubGlobal("localStorage", memStore()); // Node's own localStorage stub shadows jsdom's
  });
  afterEach(() => { act(() => root.unmount()); host.remove(); vi.restoreAllMocks(); vi.unstubAllGlobals(); document.body.innerHTML = ""; history.replaceState(null, "", "#/"); });

  function Harness() {
    const t = useTour(catalog);
    return <><button id="again" onClick={t.open}>Show the tour</button><Tour {...t} catalog={catalog} /></>;
  }
  const flush = async () => { await act(async () => { await new Promise((r) => setTimeout(r, 30)); }); };
  const key = (k: string) => act(() => { window.dispatchEvent(new KeyboardEvent("keydown", { key: k, bubbles: true })); });

  it("opens by itself the first time, starts on the Rules tab, moves with the keys, and goes back on Esc", async () => {
    history.replaceState(null, "", "#/c/avc/golden");
    document.body.insertAdjacentHTML("beforeend", `<div data-tour="rule-list"></div>`);
    act(() => root.render(<Harness />));
    await flush();
    expect(localStorage.getItem(SEEN_KEY)).toBe("1");
    expect(location.hash).toBe("#/c/avc/rules/course-description");
    expect(document.querySelector(".tour-count")?.textContent).toBe("Step 1 of 11");
    key("ArrowRight");
    expect(document.querySelector(".tour-count")?.textContent).toBe("Step 2 of 11");
    key("ArrowLeft");
    expect(document.querySelector(".tour-count")?.textContent).toBe("Step 1 of 11");
    const seen = vi.fn();
    window.addEventListener("keydown", seen);
    key("a"); // a verdict key never reaches the screen underneath
    window.removeEventListener("keydown", seen);
    expect(seen).not.toHaveBeenCalled();
    key("Escape");
    expect(document.querySelector(".tour")).toBeNull();
    expect(location.hash).toBe("#/c/avc/golden");
  });

  it("doesn't open by itself the second time; the button opens it", async () => {
    localStorage.setItem(SEEN_KEY, "1");
    act(() => root.render(<Harness />));
    await flush();
    expect(document.querySelector(".tour")).toBeNull();
    act(() => (document.getElementById("again") as HTMLButtonElement).click());
    await flush();
    expect(document.querySelector(".tour")).not.toBeNull();
  });
});
