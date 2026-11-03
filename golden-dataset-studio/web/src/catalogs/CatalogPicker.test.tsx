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
const summary = (basis: ScoreBasis): CatalogsSummary => ({ basis, columns: COLS, labels: LABELS, required: REQUIRED, properties: COLS.length,
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
  catalogsSummary: (b: ScoreBasis) => { calls.push(b); return Promise.resolve(summary(b)); },
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
    await render();
    const heads = [...host.querySelectorAll("th.rot")];
    expect(heads.map((t) => t.textContent)).toEqual(COLS.map((c) => LABELS[c]));
    expect(heads.filter((t) => t.classList.contains("req")).map((t) => t.textContent)).toEqual(REQUIRED.map((c) => LABELS[c]));
    expect(host.querySelector("th.ext")).toBeNull();
    expect(host.textContent).not.toContain("not in this Studio yet");
    expect(host.querySelector(".ctab-legend")).toBeNull();  // no legend in the golden view
    expect(host.querySelector(".ctab i.sw")).toBeNull();     // no coloured circles
    const [avc, ualr] = rows();
    expect(avc.querySelector("td.date")!.textContent).toBe("12 Oct 2026");
    expect(avc.querySelector("td.cov")!.textContent).toBe("9 of 11");
    const cellsOf = [...avc.querySelectorAll("td.c")];
    expect(cellsOf).toHaveLength(11);
    expect(cellsOf[9].textContent).toBe("—");   // creditValue → minValue: no rule in this catalog
    expect(cellsOf[10].textContent).toBe("—");  // prerequisite: not in the catalog's columns
    expect(avc.querySelectorAll("td.c .katex")).toHaveLength(9);
    expect(avc.querySelector("td.c[aria-label='inLanguage: published'] annotation")!.textContent).toBe("\\dfrac{14}{1{,}062}");
    expect(avc.querySelector("td.c[aria-label='name: in review'] annotation")!.textContent).toBe("\\dfrac{14}{1{,}062}");
    expect(avc.querySelector("a.btn")!.textContent).toBe("Open →");
    expect(avc.querySelector("a.btn")!.getAttribute("href")).toBe("#/c/avc/rules");
    expect(ualr.textContent).toContain("no rules yet");
    expect(ualr.querySelector("button")!.textContent).toBe("Generate rules");
    expect(ualr.querySelector("button .ico svg")).toBeTruthy();  // the AI sparkle
    // hovering a fraction says what it is, in words, after a second
    vi.useFakeTimers();
    const pub = avc.querySelector("td.c[aria-label='inLanguage: published'] .evx-tipw")!;
    await act(async () => pub.dispatchEvent(new MouseEvent("mouseover", { bubbles: true })));
    expect(document.querySelector("[role=tooltip]")).toBeNull();
    await act(async () => { vi.advanceTimersByTime(1000); });
    vi.useRealTimers();
    expect(document.querySelector("[role=tooltip]")!.textContent).toBe(
      "14 values an expert reviewed, of 1,062 values the rule found");
  });

  it("xtra score: exact matches with their count, per column % or n/s or —, the basis switch", async () => {
    await render();
    await act(async () => button("xtra score").click());
    expect(location.hash).toBe("#/?v=score");
    expect(host.textContent).toContain("How closely xtra's latest extract output matches each catalog's latest golden dataset");
    expect(host.querySelector("thead .evx-basis-pill")!.textContent).toBe("human-reviewed");
    const [avc, ualr] = rows();
    expect(avc.querySelector("td.rate .pct")!.textContent).toBe("55%of 56");
    // the % in its own column under "Exact matches", the overall bar in the next one with no heading
    const heads = [...host.querySelectorAll("thead th:not(.rot)")].map((t) => t.textContent);
    expect(heads.slice(2)).toEqual(["Catalog", "Exact matcheshuman-reviewed", "", "Coverage"]);
    expect(avc.querySelector("td.rate .evx-bar")).toBeNull();
    expect(avc.querySelector("td.ratebar .evx-bar")).not.toBeNull();
    // by the property's column key: a column with no score is "—", one xtra doesn't read is n/s
    const cells = [...avc.querySelectorAll("td.c")].map((t) => t.textContent);
    expect(cells).toEqual(["100%14", "0%14", "—", "100%14", "21%14", "n/s", "n/s", "n/s", "—", "—", "—"]);
    expect(ualr.querySelector("td.rate")!.textContent).toBe("no rules yet");
    // a column's bar explains its outcomes
    const desc = avc.querySelectorAll("td.sc .evx-tipw")[3];
    await act(async () => desc.dispatchEvent(new MouseEvent("mouseover", { bubbles: true })));
    const tip = document.querySelector("[role=tooltip]")!.textContent!;
    expect(tip).toContain("description · Antelope Valley College · 14 human-reviewed values");
    expect(tip).toContain("Numbers either match or are wrong.");
    // Rule-matched: no score yet shows "—"
    await act(async () => button("Rule-matched").click());
    expect(location.hash).toBe("#/?v=score&b=rule");
    expect(calls).toEqual(["human", "rule"]);
    expect(rows()[0].querySelector("td.rate")!.textContent).toBe("—");
    expect(host.querySelector("thead .evx-basis-pill")!.textContent).toBe("rule-matched");
  });
});
