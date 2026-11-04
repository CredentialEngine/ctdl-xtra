import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { CatalogDetail, CatalogsSummary, ExtractOutputs, ScoreBrief, ScoreDoc, ScoreRow, ScoreValues, WrongGroups } from "../api/types";
import { parseRoute } from "../shell/router";

const api = { extractOutputs: vi.fn(), scoreDoc: vi.fn(), scoreValues: vi.fn(), scoreWrong: vi.fn(), startScore: vi.fn(), match: vi.fn(), annotate: vi.fn(),
  catalogsSummary: vi.fn() };
vi.mock("../api/client", () => ({ api: new Proxy({}, { get: (_t, k: string) => (...a: unknown[]) => (api as Record<string, (...x: unknown[]) => unknown>)[k](...a) }) }));
vi.mock("../pagepane", () => ({ PagePane: () => null }));
import EvalsTab, { rowText, scoreFor, shown, unscoredFacts } from "./EvalsTab";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const human = { missing: 0, wrong: 4, partial: 21, match: 31 }, rule = { missing: 1, wrong: 4, partial: 21, match: 31 };
const brief = (id: string, golden: string, created: string, o: Partial<ScoreBrief> = {}): ScoreBrief => ({
  id, status: "done", golden, output: "out-2", created_at: created, error: null, human_rate: .55, rule_rate: .54, human_values: 56,
  rule_values: 57, human_outcomes: human, rule_outcomes: rule, golden_kind: golden === "human-reviewed" ? "human-reviewed" : "version",
  golden_as_of: "2026-10-28T23:56:57Z", finished_at: created, slot_names: false, ...o });
const output = (id: string, modified: string, scores: ScoreBrief[]) => ({
  id, path: "/x/avc/crawl", report_etag: id, last_modified: modified, run_id: "crawl", discovery_run_id: null, only_golden_sample: false,
  records: 1065, records_written: 1065, records_mismatch: false, scores });
const INDEX: ExtractOutputs = {
  outputs: [output("out-2", "2026-10-26T20:36:03Z", [brief("sc-0006", "ruleset-v3", "2026-10-28T23:56:57Z"),
                                                     brief("sc-0007", "ruleset-v2", "2026-10-28T23:56:58Z")]),
            output("out-1", "2026-10-20T20:00:00Z", [])],
  latest_golden: "ruleset-v3", error: null, running: null,
  goldens: [{ id: "ruleset-v3", kind: "version", ruleset_version: 3, published_at: "2026-10-27T16:52:20Z", latest: true },
            { id: "ruleset-v2", kind: "version", ruleset_version: 2, published_at: "2026-10-27T01:02:29Z", latest: false },
            { id: "rs-0003", kind: "draft", ruleset_version: 3, published_at: null, latest: false }],
};
const counts = (c: typeof human) => ({ values: c.missing + c.wrong + c.partial + c.match, ...c });
// every property, in the home table's order: the Required ones first (property-rules spec §4.9)
const COLS = ["codedNotation", "identifier", "Learning Type", "description", "inLanguage", "creditValue", "creditValue>minValue", "prerequisite", "isNonCredit", "estimatedDuration"];
const LABELS: Record<string, string> = { ...Object.fromEntries(COLS.map((c) => [c, c])), "creditValue>minValue": "creditValue → minValue" };
const col = (status: "in review" | "published", found: number, no_rule = false) => ({ status, ruleset: null, human: 0, rule: 0, found, no_rule });
const SUMMARY = { basis: "human", columns: COLS, labels: LABELS, required: COLS.slice(0, 5), properties: COLS.length, catalogs: { "avc-x": {
  coverage: 6, score: null, columns: {
    codedNotation: { ...col("in review", 31), status: "needs work" }, identifier: { ...col("in review", 14), human: 12 }, description: col("in review", 14), inLanguage: col("published", 14),
    creditValue: col("in review", 1062), "creditValue>minValue": col("in review", 1062), isNonCredit: col("in review", 0, true) } } } } as unknown as CatalogsSummary;
const DOC = { id: "sc-0006", status: "done", golden: { id: "ruleset-v3", kind: "version", from: "/g/ruleset-v3", as_of: "2026-10-28T23:56:57Z", sha256: "x" },
  output: INDEX.outputs[0], commands: ["xtra score … human-reviewed", "xtra score … rule-matched"],
  results: { human: { implied: { inLanguage: 14 }, xtra: { values: 1065, exact_match_rate: 0.6 } } }, not_scored: ["creditValue", "creditValue>minValue"],
  candidates: { description: 1065, estimatedDuration: 4200, codedNotation: 0 },
  xtra_extracts: ["codedNotation", "identifier", "name", "description", "creditValue", "creditUnitType", "prerequisite", "estimatedDuration", "subjectWebpage"],
  scorer: { xtra_cli_commit: "86a36c1" }, created_at: "2026-10-28T23:56:57Z", finished_at: "2026-10-28T23:56:58Z" } as unknown as ScoreDoc;
const VALUES = { basis: "human", result: DOC.results.human, total: counts(human), outcomes: counts(human), groups: null,
  columns: [{ column: "description", ...counts({ missing: 0, wrong: 4, partial: 7, match: 3 }) },
    // ACCT199, rule A: 4 exact durations and one extra ("Minimum Credit Units"), plus one course with an unsure unit
    { column: "estimatedDuration", values: 5, missing: 0, wrong: 0, partial: 0, unsure: 1, match: 4, extra: 1, extracted: 5,
      found: .8, right: .8, courses: 2, courses_exact: 0, list: true }],
  rows: { total: 1, offset: 0, page: 50, items: [{ key: "ns922l|0|description|0", basis: "human", column: "description", golden_record_id: "NS922L",
    page_stem: "ns922l", outcome: "wrong", similarity: .35, golden_value: "Limitation. Advisory.", extracted_value: "Limitation.",
    rule_id: "course-description", occurrence_key: "ns922l@div", value_index: 0 }] } } as unknown as ScoreValues;
const DUR = (d: string, t: string) => JSON.stringify({ "ceterms:description": d, "ceterms:timeRequired": t });
const WRONG: WrongGroups = { basis: "human", column: null, key: "auto", groups: [
  { outcome: "extra", field: null, column: "estimatedDuration", by: "description label", key: "Minimum Credit Units",
    reason: "no golden value", units: 708, courses: 708,
    example: { row: "acct199|0|estimatedDuration|4", golden_record_id: "ACCT199", golden_value: null,
               extracted_value: DUR("Minimum Credit Units", "1.0"), rule_id: "course-estimated-duration", occurrence_key: "acct199@div" },
    targets: [{ golden_record_id: "ACCT199", rule_id: "course-estimated-duration", occurrence_key: "acct199@div" },
              { golden_record_id: "ACCT299", rule_id: null, occurrence_key: null }] },
  { outcome: "wrong", field: "timeRequired", column: "estimatedDuration", by: "value shape", key: "9.9 - 9.9 → 9.9",
    reason: "cut short", units: 312, courses: 156,
    example: { row: "x", golden_record_id: "ACCT101", golden_value: DUR("Total Course In-Class (Contact) Hours", "54.0 - 432.0"),
               extracted_value: DUR("Total Course In-Class (Contact) Hours", "54.0"), rule_id: "course-estimated-duration", occurrence_key: "acct101@div" },
    targets: [{ golden_record_id: "ACCT101", rule_id: "course-estimated-duration", occurrence_key: "acct101@div" }] }] };

const CATALOG = { catalog: "avc-x", short: "avc", name: "AVC", ruleset_version: 3 } as CatalogDetail;
let host: HTMLDivElement, root: Root;
beforeEach(() => {
  host = document.createElement("div"); document.body.appendChild(host); root = createRoot(host);
  api.extractOutputs.mockResolvedValue(INDEX); api.scoreDoc.mockResolvedValue(DOC); api.scoreValues.mockResolvedValue(VALUES);
  api.catalogsSummary.mockResolvedValue(SUMMARY); api.scoreWrong.mockResolvedValue(WRONG);
});
afterEach(() => { act(() => root.unmount()); host.remove(); Object.values(api).forEach((f) => f.mockReset()); });
const render = async (hash: string) => {
  await act(async () => { root.render(<EvalsTab catalog={CATALOG} route={parseRoute(hash)} reload={() => {}} />); });
  await act(async () => { await new Promise((r) => setTimeout(r, 0)); });
};

describe("EvalsTab", () => {
  it("picks the score that shows an output against each golden side", () => {
    const o = INDEX.outputs[0];
    expect(scoreFor(o, "human", "human-reviewed", "ruleset-v3")!.id).toBe("sc-0006");  // the latest version's human-reviewed tree
    expect(scoreFor(o, "rule", "ruleset-v2", "ruleset-v3")!.id).toBe("sc-0007");
    expect(scoreFor(o, "rule", "rs-0003", "ruleset-v3")).toBeUndefined();
  });

  it("titles the comparison, charts every output and shows the human-reviewed headline", async () => {
    await render("#/c/avc/evals");
    expect(host.querySelector(".evx-title")!.textContent).toContain("Golden dataset (human-reviewed)");
    expect(host.querySelector(".evx-title")!.textContent).toContain("vsxtra catalog extractoutputs over time");
    const bars = host.querySelectorAll("[data-testid=history-bar]");
    expect(bars).toHaveLength(2);                                   // oldest first
    expect(bars[0].querySelector(".evx-score")).not.toBeNull();     // not scored yet: a dashed bar with Score
    expect(bars[1].classList.contains("sel")).toBe(true);           // the latest, picked
    expect(bars[1].textContent).toContain("55%");
    expect(bars[1].textContent).toContain("(latest)");
    expect(host.querySelector("[data-testid=headline]")!.textContent).toBe("55%exact matcheshuman-reviewed31 of 56 values an expert reviewed");
    expect(host.querySelector("[data-column=inLanguage]")!.textContent).toContain("Not scored");
    expect(host.textContent).not.toMatch(/records/);
    expect(api.scoreValues).toHaveBeenCalledWith("avc", "sc-0006", expect.objectContaining({ basis: "human" }));
  });

  it("lists every property: a scored one with its bar, the others say why", async () => {
    await render("#/c/avc/evals");
    const row = (c: string) => host.querySelector(`[data-column="${c}"]`)!;
    expect([...host.querySelectorAll(".evx-cols .evx-h")].map((h) => h.textContent)).toEqual(["Required", "Other properties"]);
    expect([...host.querySelectorAll(".evx-cols tbody tr[data-column]")].map((r) => r.getAttribute("data-column")))
      .toEqual(COLS);
    expect(row("description").querySelector(".evx-bar")).not.toBeNull();
    expect(row("description").textContent).toContain("21%");
    // an unscored column: "Not scored" and its two facts, candidates and golden values (each a chip with the sentence)
    const facts = (c: string) => [...row(c).querySelectorAll(".evx-fact")].map((f) => f.getAttribute("title"));
    expect(row("codedNotation").textContent).toContain("Not scored");
    expect(facts("codedNotation")).toEqual(["No candidates in this output", "No golden values: the Studio rule needs work"]);
    expect(row("codedNotation").textContent).toContain("Candidates: none in this output");
    expect(row("codedNotation").textContent).toContain("Golden values: none · Studio rule needs work");
    expect(facts("identifier")).toEqual(["No candidates in this output", "12 golden values · the Studio rule is in review"]);
    expect(row("identifier").textContent).toContain("Golden values: 12 · Studio rule in review");
    expect(facts("Learning Type")).toEqual(["No candidates: xtra doesn't extract this property", "Studio only: no CTDL property"]);
    expect(facts("creditValue")).toEqual(["No candidates in this output", "No golden values: the Studio rule is in review"]);
    expect(row("creditValue>minValue").textContent).toContain("creditValue → minValue");
    expect(facts("creditValue>minValue")[0]).toBe("No candidates: xtra doesn't extract this property");
    expect(row("creditValue>minValue").textContent).toContain("Candidates: none · xtra doesn't extract it");
    expect(facts("inLanguage")[1]).toBe("Not read from the page");
    expect(facts("isNonCredit")[1]).toBe("No golden values: no Studio rule yet");
    expect(facts("prerequisite")).toEqual(["No candidates in this output", "No golden values: no Studio rule yet"]);  // not in the catalog's columns: no rule
    expect(row("prerequisite").textContent).not.toMatch(/needs work|in review/);
  });

  it("defines candidates and golden values in each fact's tooltip, and says rule-matched values on that side", async () => {
    await render("#/c/avc/evals");
    const [cand, gold] = host.querySelectorAll<HTMLElement>('[data-column="identifier"] .evx-fact');
    await act(async () => { cand.focus(); });
    expect(document.querySelector("[role=tooltip]")!.textContent).toContain("Candidates: the values in xtra's extract output for this property.");
    await act(async () => { cand.blur(); gold.focus(); });
    expect(document.querySelector("[role=tooltip]")!.textContent).toContain("Golden values: the values a person reviewed");
    const doc = DOC;
    const col = { status: "in review" as const, ruleset: null, human: 2, rule: 5, found: 7, no_rule: false };
    const rule = unscoredFacts("identifier", col, doc, "rule", []);
    expect(rule.golden.full).toBe("7 rule-matched values · the Studio rule is in review");
    expect(rule.golden.term).toBe("Rule-matched values");
    expect(unscoredFacts("description", col, doc, "human", []).candidates.full).toBe("1,065 candidates");
    expect(unscoredFacts("identifier", { ...col, human: 0, rule: 0, status: "published" }, doc, "rule", []).golden.full)
      .toBe("No rule-matched values");
    // a score from before sme-fixes has no candidates or xtra_extracts: not_scored says xtra doesn't extract it
    const old = { ...doc, candidates: undefined, xtra_extracts: undefined } as ScoreDoc;
    expect(unscoredFacts("creditValue", col, old, "human", []).candidates.full).toBe("No candidates: xtra doesn't extract this property");
    expect(unscoredFacts("codedNotation", col, old, "human", []).candidates.full).toBe("No candidates in this output");
  });

  it("shows found, right and courses exact per column, with extra (striped) and unsure segments", async () => {
    await render("#/c/avc/evals");
    const dur = host.querySelector('[data-column="estimatedDuration"]')!;
    expect(dur.querySelector("[data-num=found]")!.textContent).toBe("80%");
    expect(dur.querySelector("[data-num=right]")!.textContent).toBe("80%");
    expect(dur.querySelector("[data-num=courses]")!.textContent).toBe("0%");
    expect(dur.querySelector(".evx-bar .o-extra")).not.toBeNull();
    expect(dur.querySelector(".evx-bar .o-unsure")).not.toBeNull();
    expect(dur.querySelector(".evx-bar")!.lastElementChild!.className).toBe("o-extra");  // extras last, beside the golden side
    // a value column isn't a list: no courses exact
    expect(host.querySelector('[data-column="description"] [data-num=courses]')!.textContent).toBe("");
    // the headers' tooltips give the formulas
    const found = [...host.querySelectorAll<HTMLElement>(".evx-cols thead th span[tabindex]")].find((s) => s.textContent === "Found")!;
    await act(async () => { found.focus(); });
    expect(document.querySelector("[role=tooltip]")!.textContent).toContain("found = match ÷ golden values = match ÷ (match + partial + wrong + missing + unsure)");
    const right = [...host.querySelectorAll<HTMLElement>(".evx-cols thead th span[tabindex]")].find((s) => s.textContent === "Right")!;
    await act(async () => { found.blur(); right.focus(); });
    expect(document.querySelector("[role=tooltip]")!.textContent).toContain("right = match ÷ candidates = match ÷ (match + partial + wrong + extra)");
    expect(host.querySelector("[data-testid=found-right]")!.textContent).toContain("found 55% of 56 golden values");
    // the outcome filter has unsure and extra
    expect([...host.querySelectorAll(".evx-controls .seg button")].map((b) => b.textContent!.replace(/\d|,/g, "").trim()))
      .toEqual(["All", "missing", "wrong", "partial", "unsure", "match", "extra"]);
  });

  it("groups what's wrong, biggest first, each with an example and links to its courses in the Rules tab", async () => {
    await render("#/c/avc/evals?col=estimatedDuration");
    expect(api.scoreWrong).toHaveBeenCalledWith("avc", "sc-0006", { basis: "human", column: "estimatedDuration", key: "auto" });
    const groups = host.querySelectorAll("[data-testid=wrong-group]");
    expect(groups).toHaveLength(2);
    expect(groups[0].textContent).toContain("708");
    expect(groups[0].textContent).toContain("extra");
    expect(groups[0].textContent).toContain("description label Minimum Credit Units");
    expect(groups[0].textContent).toContain("none → description: Minimum Credit Units · timeRequired: 1.0");
    const links = [...groups[0].querySelectorAll("a")].map((a) => a.getAttribute("href"));
    expect(links).toEqual(["#/c/avc/rules/course-estimated-duration?row=acct199%40div&by=anyone",
                           "#/c/avc/rules/course-estimated-duration?row=acct199%40div&by=anyone"]);
    expect(groups[0].textContent).toContain("ACCT299");  // no Studio row: listed, not linked
    expect(groups[1].textContent).toContain("timeRequired cut short");
    expect(groups[1].textContent).toContain("value shape 9.9 - 9.9 → 9.9");
    // the grouping key is in the URL
    const pick = host.querySelector<HTMLSelectElement>("[aria-label=\"Where it's wrong: group by\"]")!;
    await act(async () => { pick.value = "subject"; pick.dispatchEvent(new Event("change", { bubbles: true })); });
    expect(location.hash).toContain("wk=subject");
  });

  it("writes what each row's candidate is, or why there is none", () => {
    const r = (o: Partial<ScoreRow>) => {
      const el = document.createElement("div");
      const rt = createRoot(el);
      act(() => rt.render(<>{rowText({ golden_value: "A", extracted_value: "B", unit: "value", ...o } as ScoreRow)}</>));
      const t = el.textContent;
      act(() => rt.unmount());
      return t;
    };
    expect(r({ outcome: "unsure", unit: "absent", golden_value: null, extracted_value: null })).toBe("golden: not on the page · xtra made no claim");
    expect(r({ outcome: "missing", reason: "nothing extracted", extracted_value: null })).toBe("no candidate");
    expect(r({ outcome: "missing", reason: "claimed not on the page", extracted_value: null })).toBe("xtra claims it isn't on the page");
    expect(r({ outcome: "extra", golden_value: null, extracted_value: DUR("Minimum Credit Units", "1.0"), unit: "object", reason: "no golden value" }))
      .toBe("description: Minimum Credit Units · timeRequired: 1.0 · no golden value");
    expect(r({ outcome: "match", unit: "absent", golden_value: null, extracted_value: null })).toBe("not on the page");
    expect(shown("plain")).toBe("plain");
  });

  it("says what xtra's own score covers, under the headline, when the score has it", async () => {
    await render("#/c/avc/evals");
    expect(host.querySelector("[data-testid=xtra-line]")!.textContent).toBe("xtra's own, over every column: 60% exact matches of 1,065 values");
  });

  it("names the golden side: the silver dataset of a version, the golden dataset for human-reviewed values", async () => {
    await render("#/c/avc/evals?b=rule&g=ruleset-v2");
    expect(host.querySelector(".evx-title")!.textContent).toContain("Silver dataset ruleset-v2");
    expect(host.querySelector(".evx-title")!.textContent).not.toContain("ruleset v2");
  });

  it("scores an output from its dashed bar, against the golden side shown", async () => {
    api.startScore.mockResolvedValue({});
    await render("#/c/avc/evals?b=rule&g=ruleset-v2");
    await act(async () => { host.querySelector<HTMLButtonElement>(".evx-score")!.click(); });
    expect(api.startScore).toHaveBeenCalledWith("avc", { golden: "ruleset-v2", output: "out-1", by: expect.any(String) });
  });

  it("opens a value as a split diff with a note box that records the comparison", async () => {
    api.match.mockResolvedValue({ rule_id: "course-description", occurrence_key: "ns922l@div", page_stem: "ns922l", state: null,
      verdict: null, comments: [] });
    api.annotate.mockResolvedValue({ event: {}, rule: null });
    await render("#/c/avc/evals?row=ns922l%7C0%7Cdescription%7C0");
    const panel = host.querySelector("[data-testid=row-panel]")!;
    expect(panel.querySelector(".vd.split .vd-side.del mark")!.textContent!.trim()).toBe("Advisory.");
    expect(panel.querySelector(".vd-side.add .vd-lab")!.textContent).toBe("extract output 26 Oct");
    const box = panel.querySelector("textarea")!;
    await act(async () => {
      Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, "value")!.set!.call(box, "xtra stops early");
      box.dispatchEvent(new Event("input", { bubbles: true }));
    });
    await act(async () => { [...panel.querySelectorAll("button")].find((b) => b.textContent === "Save note")!.click(); });
    expect(api.annotate).toHaveBeenCalledWith("avc", expect.objectContaining({ type: "comment", note: "xtra stops early",
      target: expect.objectContaining({ kind: "match", rule_id: "course-description", occurrence_key: "ns922l@div" }),
      compared_with: { kind: "extract", score: "sc-0006", value: "Limitation." } }));
    expect([...panel.querySelectorAll("button")].some((b) => b.textContent === "The golden value is wrong…")).toBe(true);
    // one Split | Unified switch, at the top of the tab, not in the panel
    expect(panel.querySelector("[aria-label='Diff layout']")).toBeNull();
    expect(host.querySelector(".evx-title [aria-label='Diff layout']")).not.toBeNull();
    expect(panel.querySelector(".evx-more")!.textContent).toContain("Scroll for more");
  });

  it("says what each basis scores in the ⓘ beside the switch", async () => {
    await render("#/c/avc/evals");
    const i = host.querySelector<HTMLElement>(".evx-basis .evx-i")!;
    await act(async () => { i.focus(); });
    const tip = document.querySelector("[role=tooltip]")!.textContent!;
    expect(tip).toContain("Rule-matched scores every value in the golden dataset: the values the rules matched and the human-reviewed ones.");
    expect(tip).toContain("Human-reviewed scores only the values an expert reviewed.");
  });
});
