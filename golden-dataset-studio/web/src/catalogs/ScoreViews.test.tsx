// The xtra score view's four scopes (LearningProgram spec §2), on a small history: two catalogs, two Course
// properties scored over time (a new output, then a golden publish of one property), and LearningProgram with one
// catalog and one score.
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { CatalogCard, PropertyReview, ScoreHistory, ScoreLine, ScoreNumbers } from "../api/types";
import { setIdentity } from "../shell/reviewer";
import { parseRoute } from "../shell/router";
import { readHome } from "./homeState";
import { latest, series } from "./scoreLogic";

const n = (match: number, partial: number, wrong: number, missing = 0): ScoreNumbers => {
  const values = match + partial + wrong + missing;
  return { values, match, partial, unsure: 0, wrong, missing, exact: match / values, partial_share: partial / values };
};
const line = (at: string, score: string, trigger: string, run: string, golden: ScoreNumbers, silver: ScoreNumbers, gv = "ruleset-v3"): ScoreLine =>
  ({ at, extract_run: run, golden_version: gv, trigger, score, golden, silver,
     scored_with: { xtra_cli_version: "0.14.2", xtra_cli_commit: "4f2a1c9aa" } });
const COURSE: ScoreHistory = {
  cls: "course", target: 0.9, catalogs: ["avc-x", "wvu-x"],
  properties: [{ column: "name", label: "name", term: "ceterms:name", tier: "required" },
               { column: "codedNotation", label: "codedNotation", term: "ceterms:codedNotation", tier: "required" },
               { column: "creditValue>minValue", label: "creditValue → minValue", term: "ceterms:creditValue>schema:minValue", tier: "phase1" }],
  history: {
    "avc-x": {
      name: [line("2026-11-20T10:00:00Z", "sc-1", "new-output", "o1", n(8, 1, 1), n(80, 10, 10)),
             line("2026-11-23T10:00:00Z", "sc-2", "new-output", "o2", n(9, 1, 0), n(85, 10, 5)),
             line("2026-11-24T09:02:00Z", "sc-3", "golden-published", "o2", n(10, 0, 0), n(88, 6, 6), "ruleset-v4")],
      codedNotation: [line("2026-11-20T10:00:00Z", "sc-1", "new-output", "o1", n(10, 0, 0), n(100, 0, 0)),
                      line("2026-11-23T10:00:00Z", "sc-2", "new-output", "o2", n(10, 0, 0), n(99, 0, 1))],
    },
    "wvu-x": { name: [line("2026-11-23T11:00:00Z", "sc-9", "new-output", "w1", n(5, 3, 2), n(50, 30, 20))] },
  },
};
const LP: ScoreHistory = { cls: "learningprogram", target: 0.9, catalogs: ["wvu-x"],
  properties: [{ column: "name", label: "name", term: "ceterms:name", tier: "required" }],
  history: { "wvu-x": { name: [line("2026-11-24T08:00:00Z", "sc-1", "new-output", "w1", n(3, 3, 4), n(30, 30, 40))] } } };
const REVIEW: PropertyReview = { cls: "course", column: "name", threads: {},
  status: { status: "needs review", by: "Jared Diener", role: "sme", at: "2026-11-18T10:00:00Z", history: [] },
  findings: [
    { id: "fd-1", code: "N2", title: "The name is read from the card, not the h1", kind: "mismatch", whose: "extractor", state: "open",
      links: [], counts: { partial: [5, 6], wrong: [0, 1], missing: null }, catalogs: "UARK", at: "", author: "Seth Alt",
      created: { at: "2026-11-18T10:00:00Z", by: "Seth Alt" }, live: null, comments: 2 },
    { id: "fd-2", code: "N1", title: "Double spaces", kind: "mismatch", whose: "baseline", state: "fixed", links: [{ catalog: "avc", outcome: "partial",
      field: null, by: "word diff", key: "spaces", group_by: "auto" }], at: "", author: "Seth Alt", created: { at: "2026-11-18T10:00:00Z", by: "Seth Alt" },
      live: { counts: { partial: [0, 7], wrong: null, missing: null }, rows: [{ catalog: "avc", outcome: "partial", by: "word diff", key: "spaces", golden: 0, silver: 7 }] },
      comments: 0 }] };
const setStatus = vi.fn(() => Promise.resolve({}));
const saveFinding = vi.fn(() => Promise.resolve({}));
vi.mock("../api/client", () => ({ api: {
  scoreHistory: (cls: string) => Promise.resolve(cls === "course" ? COURSE : LP),
  propertyStatuses: (cls: string) => Promise.resolve(cls === "course" ? { name: { status: "done", by: "Jared Diener", at: "" },
    codedNotation: { status: "needs review", by: "Eric Riddoch", at: "" } } : {}),
  propertyReview: () => Promise.resolve(REVIEW), catalogs: () => Promise.resolve([{ short: "avc", name: "AVC" }]),
  propertyThread: () => Promise.resolve([]),
  setPropertyStatus: (...a: unknown[]) => (setStatus as (...x: unknown[]) => Promise<unknown>)(...a),
  saveFinding: (...a: unknown[]) => (saveFinding as (...x: unknown[]) => Promise<unknown>)(...a),
} }));
import { ScoreViews } from "./ScoreViews";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
const card = (catalog: string, short: string, name: string): CatalogCard => ({ catalog, short, name, institution: name, platform: "",
  logo: null, pages: 1, crawl: null, ruleset_version: 3, rules_total: 1, rules_approved: 0, status: "ready" });
const CATS = [card("avc-x", "avc", "AVC"), card("wvu-x", "wvu", "WVU")];
let host: HTMLDivElement, root: Root;
beforeEach(() => { host = document.createElement("div"); document.body.appendChild(host); root = createRoot(host); });
afterEach(() => { act(() => root.unmount()); host.remove(); });
const show = async (hash: string) => {
  history.replaceState(null, "", hash);
  await act(async () => root.render(<ScoreViews cats={CATS} state={readHome(parseRoute(hash).params)} />));
  await act(async () => { await new Promise((r) => setTimeout(r, 0)); });
};
const heads = (cls: string) => [...host.querySelectorAll(`[data-class=${cls}] tbody td.sv-hd`)].map((t) => t.textContent);
const cells = (cls: string, row: string, sel: string) =>
  [...host.querySelectorAll(`[data-class=${cls}] tbody[data-row="${row}"] ${sel}`)].map((t) => t.textContent);

describe("the score history, summed", () => {
  it("sums the pairs' latest scores, and keeps each pair's latest at every point of the history", () => {
    const pairs: [string, string][] = [["avc-x", "name"], ["avc-x", "codedNotation"]];
    expect(latest(COURSE, pairs, "golden")).toEqual({ values: 20, match: 20, partial: 0, unsure: 0, wrong: 0, missing: 0 });
    const pts = series(COURSE, pairs, "golden");
    expect(pts.map((p) => [p.kind, p.c.match, p.c.values])).toEqual([["output", 18, 20], ["output", 19, 20], ["golden", 20, 20]]);
    // over several catalogs, a day is one point
    const all = series(COURSE, [...pairs, ["wvu-x", "name"]], "golden");
    expect(all.map((p) => [p.at.slice(0, 10), p.c.match, p.c.values])).toEqual(
      [["2026-11-20", 18, 20], ["2026-11-23", 24, 30], ["2026-11-24", 25, 30]]);
  });
});

describe("the xtra score view", () => {
  it("all catalogs, all properties: a table per class, a row per catalog and All, Golden and Silver lines", async () => {
    await show("#/?v=score");
    expect(host.querySelector(".sv")!.getAttribute("data-scope")).toBe("all");
    expect([...host.querySelectorAll(".sv-h h2")].map((h) => h.textContent)).toEqual(["Course", "LearningProgram"]);
    expect(heads("course")).toEqual(["AVC", "WVU", "All"]);
    expect(cells("course", "avc-x", "td.sv-tr")).toEqual(["Golden", "Silver"]);
    expect(cells("course", "avc-x", "td.sv-ex")).toEqual(["100.0%", "93.5%"]);      // 20 of 20; 187 of 200
    expect(cells("course", "wvu-x", "td.sv-ex")).toEqual(["50.0%", "50.0%"]);
    expect(host.querySelector("[data-class=course] tbody[data-row=wvu-x] td.sv-ex")!.classList.contains("under")).toBe(true);
    expect(host.querySelector("[data-class=course] tbody[data-row=all] td.sv-ex")!.classList.contains("under")).toBe(true);  // 83.3%
    expect(host.querySelector("[data-class=learningprogram] .sv-h .muted")!.textContent).toBe(
      "1 catalog, over its scored properties. The catalog opens its properties.");
    expect(cells("course", "all", "td.sv-ex")).toEqual(["83.3%", "79.0%"]);         // 25 of 30; 237 of 300
    expect(host.querySelectorAll("[data-class=course] tbody[data-row=avc-x] [data-testid=history]")).toHaveLength(2);
    expect(host.querySelector("[data-class=course] tbody[data-row=avc-x] a")!.getAttribute("href")).toBe("#/?v=score&c=avc");
    expect(host.querySelector(".sv-legend")!.textContent).toContain("Dotted line: the 90% target.");
    expect(host.textContent).not.toContain("Score now");
  });

  it("Rows: Properties lists each property over every catalog; unscored ones are counted, not listed", async () => {
    await show("#/?v=score&rows=props");
    expect(heads("course")).toEqual(["ceterms:name✓ Donerequired", "ceterms:codedNotationNeeds reviewrequired"]);
    expect(host.querySelector("[data-class=course] .sv-left")!.textContent).toBe("1 property not scored yet.");
    expect(host.querySelector("[data-class=course] tbody a")!.getAttribute("href")).toBe("#/?v=score&cls=course&p=course%3Aname&rows=props");
  });

  it("Numbers: a column per outcome, its heading in the outcome's colour", async () => {
    await show("#/?v=score&n=1");
    expect([...host.querySelectorAll("[data-class=course] thead th")].map((t) => t.textContent)).toEqual(
      ["Catalog", "", "exact", "partial", "unsure", "wrong", "missing", "exact %", "Last 7 outputs"]);
    expect(cells("course", "avc-x", "td.sv-n")).toEqual(["20", "0", "0", "0", "0", "100.0%", "187", "6", "0", "7", "0", "93.5%"]);
    expect(host.querySelector("[data-class=course] th.c-missing")).not.toBeNull();
  });

  it("one catalog: its properties, each with Evals →", async () => {
    await show("#/?v=score&c=wvu");
    expect(host.querySelector(".sv")!.getAttribute("data-scope")).toBe("catalog");
    expect(heads("course")).toEqual(["ceterms:name✓ Donerequired"]);
    expect(host.querySelector("[data-class=course] td.sv-ev a")!.getAttribute("href")).toBe("#/c/wvu/course/evals?col=name");
    expect(host.querySelector("[data-class=learningprogram] td.sv-ev a")!.getAttribute("href")).toBe("#/c/wvu/learningprogram/evals?col=name");
  });

  it("one property: each catalog's, then All; a catalog opens its history", async () => {
    await show("#/?v=score&p=course:name");
    expect(host.querySelector(".sv")!.getAttribute("data-scope")).toBe("property");
    expect(host.querySelector("[data-class=learningprogram]")).toBeNull();   // a property list never mixes classes
    expect(host.querySelector("[data-testid=classes-menu]")!.textContent).toContain("Course");  // narrowed to its class
    expect(host.querySelector("[data-testid=classes-menu]")!.textContent).not.toContain("LearningProgram");
    expect(heads("course")).toEqual(["AVC", "WVU", "All"]);
    expect(host.querySelector("[data-class=course] .sv-h .muted")!.textContent).toBe("ceterms:name in 2 catalogs. A catalog opens its history.");
    expect(host.querySelector("[data-class=course] tbody a")!.getAttribute("href")).toBe("#/?v=score&c=avc&p=course%3Aname");
  });

  it("one catalog, one property: its scores over time, what scored each, and a link into Evals", async () => {
    await show("#/?v=score&c=avc&p=course:name");
    expect(host.querySelector(".sv")!.getAttribute("data-scope")).toBe("one");
    expect(host.querySelectorAll(".sv-charts svg")).toHaveLength(2);
    expect([...host.querySelectorAll(".sv-charts svg .kind")].map((k) => k.textContent)).toEqual(
      ["output", "output", "golden", "output", "output", "golden"]);
    const scores = [...host.querySelectorAll("tbody[data-score]")];
    expect(scores.map((s) => s.getAttribute("data-score"))).toEqual(["sc-3", "sc-2", "sc-1"]);  // newest first
    expect(scores[0].querySelector("td.sv-hd")!.textContent).toContain("Golden published");
    expect(scores[0].querySelector("td.sv-sw")!.textContent).toBe("golden ruleset-v4xtra-cli 0.14.2 (4f2a1c9)");
    expect(host.querySelector("a.sv-evals")!.textContent).toBe("Open AVC's Evals tab at ceterms:name →");
    expect(host.querySelector("a.sv-evals")!.getAttribute("href")).toBe("#/c/avc/course/evals?col=name");
    expect(host.querySelector("[aria-label='Bars or numbers']")).toBeNull();
  });

  it("the Properties menu: properties under their class, a search, and a class ticks all of its own", async () => {
    await show("#/?v=score");
    await act(async () => host.querySelector<HTMLButtonElement>("[data-testid=properties-menu]")!.click());
    expect([...host.querySelectorAll(".hm-group")].map((g) => g.querySelector(".head")!.textContent)).toEqual(
      ["Course3 properties", "LearningProgram1 properties"]);
    expect([...host.querySelectorAll("[data-class=course] .hm-opt.sub")].map((o) => o.textContent)).toEqual(
      ["ceterms:name", "ceterms:codedNotation", "ceterms:creditValue → schema:minValue"]);
    // unticking LearningProgram leaves Course's properties
    await act(async () => host.querySelector<HTMLInputElement>(".hm-group[data-class=learningprogram] .head input")!.click());
    expect(new URLSearchParams(location.hash.split("?")[1]).get("p")).toBe("course:name,course:codedNotation,course:creditValue>minValue");
    // a search narrows the list
    const find = host.querySelector<HTMLInputElement>(".hm-find")!;
    const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")!.set!;
    await act(async () => { setter.call(find, "coded"); find.dispatchEvent(new Event("input", { bubbles: true })); });
    expect([...host.querySelectorAll(".hm-opt.sub")].map((o) => o.textContent)).toEqual(["ceterms:codedNotation"]);
  });

  it("one property: its status at the top (Done only for an expert), and its findings below the scores", async () => {
    setIdentity("Eric Riddoch", "engineer");
    await show("#/?v=score&p=course:name");
    const bar = host.querySelector("[data-testid=property-status]")!;
    expect(bar.textContent).toBe("Course › ceterms:nameNeeds reviewDoneset by Jared, 18 Nov1 open finding, 1 fixed");
    expect(bar.querySelector<HTMLButtonElement>("[aria-label=Status] button:last-child")!.disabled).toBe(true);
    const rows = [...host.querySelectorAll("[data-testid=findings] tbody tr")].map((r) => [...r.querySelectorAll("td")].map((t) => t.textContent));
    expect(rows).toEqual([
      ["N2", "mismatch", "The name is read from the card, not the h1", "5 / 6", "0 / 1", "–", "UARK", "extractor", "open", "2"],
      ["N1", "mismatch", "Double spaces", "0 / 7", "–", "–", "AVC", "baseline", "fixed", "0"]]);
    setIdentity("Jared Diener", "sme");
    await show("#/?v=score&p=course:name");
    const done = host.querySelector<HTMLButtonElement>("[data-testid=property-status] [aria-label=Status] button:last-child")!;
    expect(done.disabled).toBe(false);
    await act(async () => done.click());
    expect(setStatus).toHaveBeenCalledWith("course", "name", "done", "Jared Diener");
    // a finding opens its editor, with the running notes' counts until it's linked
    await act(async () => host.querySelector<HTMLElement>("[data-finding=N2]")!.click());
    const panel = host.querySelector("[data-testid=finding-panel]")!;
    expect(panel.querySelector("h2")!.textContent).toBe("N2The name is read from the card, not the h1");
    expect(panel.textContent).toContain("Opened by Seth, 18 Nov. Open.");
    expect(panel.querySelector(".fd-units")!.textContent).toContain("UARK. From the running notes");
    expect(panel.querySelector("[aria-label='Whose error'] .on")!.textContent).toBe("extractor");
  });

  it("+ Add finding writes a new one: code and title, whose error, cause, fix and assessment", async () => {
    setIdentity("Eric Riddoch", "engineer");
    await show("#/?v=score&p=course:name");
    await act(async () => [...host.querySelectorAll<HTMLButtonElement>("[data-testid=findings] button")].find((b) => b.textContent === "+ Add finding")!.click());
    const panel = host.querySelector("[data-testid=finding-panel]")!;
    const type = async (el: HTMLInputElement | HTMLTextAreaElement, v: string) => {
      const proto = el instanceof HTMLTextAreaElement ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
      Object.getOwnPropertyDescriptor(proto, "value")!.set!.call(el, v);
      await act(async () => { el.dispatchEvent(new Event("input", { bubbles: true })); });
    };
    await type(panel.querySelector<HTMLInputElement>("[aria-label=Code]")!, "N5");
    await type(panel.querySelector<HTMLInputElement>("[aria-label=Title]")!, "Trailing full stop");
    await act(async () => [...panel.querySelectorAll<HTMLButtonElement>("[aria-label='Whose error'] button")].find((b) => b.textContent === "baseline")!.click());
    await type(panel.querySelector<HTMLTextAreaElement>("textarea[aria-label=cause]")!, "The baseline keeps the dot.");
    await act(async () => [...panel.querySelectorAll<HTMLButtonElement>("button")].find((b) => b.textContent === "Save finding")!.click());
    expect(saveFinding).toHaveBeenCalledWith("course", "name", expect.objectContaining({
      author: "Eric Riddoch", code: "N5", title: "Trailing full stop", whose: "baseline", cause: "The baseline keeps the dot.", state: "open" }), undefined);
  });
});

