import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { CatalogCard, CatalogsSummary, ColumnStatus, ScoreBasis } from "../api/types";

const card = (o: Partial<CatalogCard>): CatalogCard => ({ catalog: "avc", short: "avc", name: "AVC",
  institution: "Antelope Valley College", platform: "", logo: null, pages: 1062, crawl: "2026-10-12T20-59-13Z", ruleset_version: 3,
  rules_total: 14, rules_approved: 1, status: "ready", ...o });
const CARDS = [card({}), card({ catalog: "ualr", short: "ualr", name: "University of Arkansas at Little Rock", ruleset_version: null,
  rules_total: 0, rules_approved: 0, status: "not imported", crawl: "2026-10-18T00-00-00Z" })];
// one column per property, in order; the Required ones first (property-rules spec §4.9)
const COLS = ["codedNotation", "identifier", "Learning Type", "name", "description", "subjectWebpage", "lifeCycleStatusType",
  "inLanguage", "creditValue", "creditValue>minValue", "prerequisite"];
const LABELS: Record<string, string> = { ...Object.fromEntries(COLS.map((c) => [c, c])), "creditValue>minValue": "creditValue → minValue" };
const REQUIRED = COLS.slice(0, 8);
const counts = (match: number, partial: number, wrong: number) => ({ values: match + partial + wrong, match, partial, wrong, missing: 0 });
const col = (status: ColumnStatus, ruleset: number | null, found = 1062) => ({ status, ruleset, human: 14, rule: 0, found });
const TIERS = Object.fromEntries(COLS.map((c, i) => [c, i < 8 ? "required" : c === "prerequisite" ? "phase2" : "phase1"])) as CatalogsSummary["tiers"];
const LP_SUM: CatalogsSummary = { basis: "human", cls: "learningprogram", columns: ["identifier", "name", "Learning Type"],
  labels: { identifier: "identifier", name: "name", "Learning Type": "Learning Type" }, required: ["identifier", "name"],
  tiers: { identifier: "required", name: "required", "Learning Type": "phase1" }, properties: 3, catalogs: {} };
const summary = (basis: ScoreBasis): CatalogsSummary => ({ basis, columns: COLS, labels: LABELS, required: REQUIRED, properties: COLS.length,
  tiers: TIERS,
  catalogs: { avc: {
    coverage: 9,
    columns: {
      codedNotation: col("in review", null), identifier: col("in review", null), "Learning Type": col("in review", null),
      name: col("in review", null), description: col("needs work", null), subjectWebpage: col("in review", null),
      lifeCycleStatusType: col("in review", null), inLanguage: { ...col("published", 3), rule: 1048 },
      creditValue: col("in review", null, 1062),
      "creditValue>minValue": { status: "in review", ruleset: null, human: 0, rule: 0, found: 0, no_rule: true },
    },
    score: basis === "human" ? { id: "sc-0006", golden: "ruleset-v3", output: "2026-10-26T20-36-03Z", output_at: null, values: 56,
      outcomes: { match: 31, partial: 21, wrong: 4, missing: 0 }, implied: ["subjectWebpage", "lifeCycleStatusType", "inLanguage"],
      by_column: { codedNotation: counts(14, 0, 0), identifier: counts(0, 14, 0), name: counts(14, 0, 0), description: counts(3, 7, 4) } } : null,
  } } });
const calls: string[] = [];
vi.mock("../api/client", () => ({ api: {
  catalogs: () => Promise.resolve(CARDS),
  catalogsSummary: (b: ScoreBasis, cls?: string) => { calls.push(`${b}:${cls}`); return Promise.resolve(cls === "learningprogram" ? LP_SUM : summary(b)); },
  scoreHistory: () => new Promise(() => {}),
} }));
import CatalogPicker from "./CatalogPicker";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
let host: HTMLDivElement, root: Root;
beforeEach(() => {
  try { localStorage.setItem("studio.loop.hidden", "1"); } catch { /* no storage */ }
  history.replaceState(null, "", "#/");
  calls.length = 0;
  host = document.createElement("div"); document.body.appendChild(host); root = createRoot(host);
});
afterEach(() => { act(() => root.unmount()); host.remove(); document.querySelectorAll("[role=tooltip]").forEach((t) => t.remove()); });

async function render() {
  await act(async () => root.render(<CatalogPicker />));
  const gotIt = [...host.querySelectorAll("button")].find((b) => b.textContent === "Got it");
  if (gotIt) await act(async () => gotIt.click());
}
const button = (t: string) => [...host.querySelectorAll("button")].find((b) => b.textContent === t)!;
const rows = () => [...host.querySelectorAll("tbody tr")];

describe("the catalogs table", () => {
  it("golden dataset: one angled column per property (the labels), Required in bold, a fraction per column, — with no rule, and Coverage", async () => {
    history.replaceState(null, "", "#/?cls=course");
    await render();
    const heads = [...host.querySelectorAll("th.rot")];
    // Required, then Phase 1, then Phase 2 folded into one column
    expect(heads.map((t) => t.textContent)).toEqual([...COLS.slice(0, 10).map((c) => LABELS[c]), "+ 1 Phase 2"]);
    expect(heads.filter((t) => t.classList.contains("req")).map((t) => t.textContent)).toEqual(REQUIRED.map((c) => LABELS[c]));
    expect(host.querySelector(".ctab i.sw")).toBeNull();     // no coloured circles
    const [avc, ualr] = rows();
    expect(avc.querySelector("td.date")!.textContent).toBe("12 Oct 2026");
    expect(avc.querySelector("td.cov")!.textContent).toBe("9 of 11 Course");
    const cellsOf = [...avc.querySelectorAll("td.c")];
    expect(cellsOf).toHaveLength(10);
    expect(cellsOf[9].textContent).toBe("—");   // creditValue → minValue: no rule in this catalog
    expect(avc.querySelector("td.p2c")!.textContent).toBe("0 of 1");  // prerequisite: Phase 2, no rule here
    expect(avc.querySelectorAll("td.c .katex")).toHaveLength(9);
    expect(avc.querySelector("td.c[aria-label='inLanguage: published'] annotation")!.textContent).toBe("\\dfrac{14}{1{,}062}");
    expect(avc.querySelector("td.c[aria-label='name: in review'] annotation")!.textContent).toBe("\\dfrac{14}{1{,}062}");
    expect(avc.querySelector("a.btn")!.textContent).toBe("Open →");
    expect(avc.querySelector("a.btn")!.getAttribute("href")).toBe("#/c/avc/course/rules");
    expect(ualr.textContent).toContain("no rules yet");
    expect(ualr.querySelector("button")!.textContent).toBe("Generate rules");
    expect(ualr.querySelector("button .ico svg")).toBeTruthy();  // the AI sparkle
    // Phase 2 opens on a click
    await act(async () => host.querySelector<HTMLElement>("th.p2")!.click());
    expect([...host.querySelectorAll("th.rot")].map((t) => t.textContent).slice(-1)).toEqual(["prerequisite"]);
    expect(rows()[0].querySelectorAll("td.c")).toHaveLength(11);
    // hovering a fraction says what it is, in words, after a second
    vi.useFakeTimers();
    const pub = rows()[0].querySelector("td.c[aria-label='inLanguage: published'] .evx-tipw")!;
    await act(async () => pub.dispatchEvent(new MouseEvent("mouseover", { bubbles: true })));
    expect(document.querySelector("[role=tooltip]")).toBeNull();
    await act(async () => { vi.advanceTimersByTime(1000); });
    vi.useRealTimers();
    expect(document.querySelector("[role=tooltip]")!.textContent).toBe(
      "14 values an expert reviewed, of 1,062 values the rule found");
  });

  it("puts the ticked classes' columns side by side under a heading each; a catalog without a class's rules says so", async () => {
    await render();
    expect([...host.querySelectorAll("tr.cls-row th[data-class]")].map((t) => t.textContent)).toEqual([
      "Course8 required, 2 more in Phase 1, 1 in Phase 2", "LearningProgram2 required, 1 more in Phase 1, 0 in Phase 2"]);
    const avc = rows()[0];
    expect(avc.querySelector("td.nosrc")!.textContent).toBe("No LearningProgram rules yet");
    expect(avc.querySelector("td.nosrc")!.getAttribute("colspan")).toBe("3");
    // the Classes menu: what each class has, and unticking one drops its columns
    await act(async () => host.querySelector<HTMLButtonElement>("[data-testid=classes-menu]")!.click());
    expect([...host.querySelectorAll(".hm-pop .hm-opt")].map((o) => o.textContent)).toEqual([
      "Course11 properties, 1 catalog", "LearningProgram3 properties, 0 catalogs"]);
    expect(host.querySelector(".hm-foot")!.textContent).toBe("Columns for each ticked class, side by side");
    await act(async () => host.querySelectorAll<HTMLInputElement>(".hm-pop input")[1].click());
    expect(location.hash).toBe("#/?cls=course");
    expect(calls.sort()).toEqual(["human:course", "human:learningprogram"]);
  });

  it("names a catalog that isn't a source of a class", async () => {
    CARDS[0] = { ...CARDS[0], not_sources: ["learningprogram"] };
    await render();
    expect(rows()[0].querySelector("td.nosrc")!.textContent).toBe("Not a LearningProgram source");
    CARDS[0] = { ...CARDS[0], not_sources: [] };
  });

  it("switches to the xtra score view, which keeps the address", async () => {
    await render();
    await act(async () => button("xtra score").click());
    expect(location.hash).toBe("#/?v=score");
    expect(host.querySelector("[data-testid=catalogs-menu]")).not.toBeNull();
  });
});
