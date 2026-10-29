import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { CatalogDetail, ExtractOutputs, ScoreBrief, ScoreDoc, ScoreValues } from "../api/types";
import { parseRoute } from "../shell/router";

const api = { extractOutputs: vi.fn(), scoreDoc: vi.fn(), scoreValues: vi.fn(), startScore: vi.fn(), match: vi.fn(), annotate: vi.fn() };
vi.mock("../api/client", () => ({ api: new Proxy({}, { get: (_t, k: string) => (...a: unknown[]) => (api as Record<string, (...x: unknown[]) => unknown>)[k](...a) }) }));
vi.mock("../pagepane", () => ({ PagePane: () => null }));
import EvalsTab, { scoreFor } from "./EvalsTab";

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
const DOC = { id: "sc-0006", status: "done", golden: { id: "ruleset-v3", kind: "version", from: "/g/ruleset-v3", as_of: "2026-10-28T23:56:57Z", sha256: "x" },
  output: INDEX.outputs[0], commands: ["xtra score … human-reviewed", "xtra score … rule-matched"], results: { human: { implied: { inLanguage: 14 } } },
  scorer: { xtra_cli_commit: "86a36c1" }, created_at: "2026-10-28T23:56:57Z", finished_at: "2026-10-28T23:56:58Z" } as unknown as ScoreDoc;
const VALUES = { basis: "human", result: DOC.results.human, total: counts(human), outcomes: counts(human), groups: null,
  columns: [{ column: "description", ...counts({ missing: 0, wrong: 4, partial: 7, match: 3 }) }],
  rows: { total: 1, offset: 0, page: 50, items: [{ key: "ns922l|0|description|0", basis: "human", column: "description", golden_record_id: "NS922L",
    page_stem: "ns922l", outcome: "wrong", similarity: .35, golden_value: "Limitation. Advisory.", extracted_value: "Limitation.",
    rule_id: "course-description", occurrence_key: "ns922l@div", value_index: 0 }] } } as unknown as ScoreValues;

const CATALOG = { catalog: "avc-x", short: "avc", name: "AVC", ruleset_version: 3 } as CatalogDetail;
let host: HTMLDivElement, root: Root;
beforeEach(() => {
  host = document.createElement("div"); document.body.appendChild(host); root = createRoot(host);
  api.extractOutputs.mockResolvedValue(INDEX); api.scoreDoc.mockResolvedValue(DOC); api.scoreValues.mockResolvedValue(VALUES);
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
    expect(host.querySelector(".evx-title")!.textContent).toContain("Human-reviewed values");
    expect(host.querySelector(".evx-title")!.textContent).toContain("vsxtra catalog extractoutputs over time");
    const bars = host.querySelectorAll("[data-testid=history-bar]");
    expect(bars).toHaveLength(2);                                   // oldest first
    expect(bars[0].querySelector(".evx-score")).not.toBeNull();     // not scored yet: a dashed bar with Score
    expect(bars[1].classList.contains("sel")).toBe(true);           // the latest, picked
    expect(bars[1].textContent).toContain("55%");
    expect(bars[1].textContent).toContain("(latest)");
    expect(host.querySelector("[data-testid=headline]")!.textContent).toBe("55%exact matcheshuman-reviewed31 of 56 values an expert reviewed");
    expect(host.textContent).toContain("not scored: inLanguage (not read from the page)");
    expect(host.textContent).not.toMatch(/records|fields/);
    expect(api.scoreValues).toHaveBeenCalledWith("avc", "sc-0006", expect.objectContaining({ basis: "human" }));
  });

  it("scores an output from its dashed bar, against the golden side shown", async () => {
    api.startScore.mockResolvedValue({});
    await render("#/c/avc/evals?b=rule&g=ruleset-v2");
    expect(host.querySelector(".evx-title")!.textContent).toContain("ruleset v2");
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
