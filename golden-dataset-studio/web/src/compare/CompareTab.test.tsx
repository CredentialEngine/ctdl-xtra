import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { CatalogDetail } from "../api/types";
import { parseRoute } from "../shell/router";
import type { CompareResponseX } from "./types";

const compareMock = vi.fn();
const recordsMock = vi.fn();
const annotateMock = vi.fn();
vi.mock("../api/client", () => ({ api: { compare: (...args: unknown[]) => compareMock(...args),
                                         compareRecords: (...args: unknown[]) => recordsMock(...args),
                                         annotate: (...args: unknown[]) => annotateMock(...args) } }));
import CompareTab from "./CompareTab";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const brief = (ck: string, a: string, b: string) => ({
  key: `${ck.toLowerCase()}@div`, course_key: ck, page_stem: ck.toLowerCase(), a_value: a, b_value: b,
  diff: a === b ? [{ op: "same" as const, text: a }]
    : [{ op: "del" as const, text: a.slice(0, a.length - b.length) }, { op: "same" as const, text: b }],
  css_path: null, char_start: null, char_end: null,
});

const RESPONSE: CompareResponseX = {
  a: 1, b: 2, a_extraction: "rs-0001", b_extraction: "rs-0002",
  versions: [{ version: 1, extraction: "rs-0001", note: null }, { version: 2, extraction: "rs-0002", note: null }],
  changed_rules: [{ rule_id: "course-description", title: "Description", subtitle: "ceterms:description", kind: "field",
                    ctdl_property: "ceterms:description", a_version: 1, b_version: 2, records_changed: 278 }],
  records_changed: 278, totals: { fixed: 5, still_wrong: 0, newly_wrong: 0, unchanged: 9 }, elapsed_ms: 2,
  rules: [{
    rule_id: "course-description", kind: "field", ctdl_property: "ceterms:description", property_label: "Description",
    title: "Description", subtitle: "ceterms:description", a_version: 1, b_version: 2, why: "Prerequisite lines were included.",
    annotated: { rows: 2, fixed: 1, still_wrong: 0, newly_wrong: 0, unchanged: 1 },
    annotated_rows: [
      { ...brief("GEOG222", "Prerequisite: GEOG 205. This course provides", "This course provides"), verdict: "wrong",
        author: "Jared", note: "Prerequisite should be a separate property.", expected: "This course provides",
        outcome: "fixed", annotation_id: "a1", history: "previously-wrong" },
      { ...brief("ACCT199", "LIMITATION ON ENROLLMENT", "LIMITATION ON ENROLLMENT"), verdict: "correct", author: "Jared",
        note: null, expected: null, outcome: "unchanged", annotation_id: "a2", history: "previously-correct" },
    ],
    values: { changed: 278, total: 1062, new: 0, vanished: 0 },
    signals: [{ signal: "contains-label-text", a: 547, b: 273, lost_total: 274, gained_total: 0,
                lost: [brief("CS120", "Prerequisite: MATH 150. A first course", "A first course")], gained: [] }],
    sample: [brief("AUTO240", "Prerequisite: AUTO 100. Theory", "Theory")], sample_total: 273,
    new_rows: [], vanished_rows: [], verdict: "BETTER",
  }],
};

const SAMPLE = (f: string[], order: string) => ({ order, seed: 0, total: 273, listed: f.length ? 268 : 273, cell_count: 2,
  cross: order === "auto" ? ["lead_a"] : [], tag_dims: order === "auto" ? ["lead_a"] : f.map((x) => x.split(":")[0]),
  cells: [{ buckets: { lead_a: "none" }, rows: 5 }, { buckets: { lead_a: "Prerequisite:" }, rows: 268 }],
  histograms: [
    { id: "lead_a", label: "Leading label in A", help: "", uniform: false, spread: 0.5,
      buckets: [{ id: "Prerequisite:", count: 268, on: f.length > 0 }, { id: "none", count: 5, on: false }] },
    { id: "url", label: "URL pattern", help: "", uniform: true, spread: 0, buckets: [{ id: "/catalog/9-9/course/*", count: 273, on: false }] },
  ] });
const records = (offset: number, limit: number, f: string[], order: string) => {
  const total = f.length ? 268 : 273;
  return { total, all: 273, offset, limit, sample: SAMPLE(f, order),
    records: Array.from({ length: Math.min(limit, total - offset) }, (_, i) =>
      ({ ...brief(`AUTO${offset + i}`, "Prerequisite: X. Theory", "Theory"), rule_id: "course-description",
         tags: order === "auto" || f.length ? [{ dim: "lead_a", label: "Leading label in A", bucket: "Prerequisite:" }] : [] })) };
};

const CATALOG = { catalog: "avc-elumenapp-com-catalog-2026-27", short: "avc", name: "AVC" } as CatalogDetail;

let host: HTMLDivElement, root: Root;
beforeEach(() => { host = document.createElement("div"); document.body.appendChild(host); root = createRoot(host); });
afterEach(() => { act(() => root.unmount()); host.remove(); compareMock.mockReset(); location.hash = ""; });

async function render(hash: string, resp: CompareResponseX = RESPONSE) {
  compareMock.mockResolvedValue(resp);
  recordsMock.mockReset().mockImplementation(async (_c: string, o: { offset: number; limit: number; f: string[]; order: string }) =>
    records(o.offset, o.limit, o.f, o.order));
  await act(async () => {
    root.render(<CompareTab catalog={CATALOG} route={parseRoute(hash)} reload={() => {}} />);
  });
}

describe("CompareTab", () => {
  it("shows the summary line, the changed rules and the earlier verdicts", async () => {
    await render("#/c/avc/compare");
    expect(compareMock).toHaveBeenCalledWith("avc", { a: undefined, b: undefined, rule: undefined });
    const to = host.querySelector<HTMLSelectElement>("select[aria-label=to]")!;
    expect([...to.options].map((o) => o.textContent)).toEqual(["ruleset v1", "ruleset v2 (latest)"]);
    const sum = host.querySelector("[data-testid=sumline]")!;
    expect(sum.textContent).toBe("278 records changed·5 fixed·0 still wrong·0 newly wrong");  // CSS gap spaces the dots
    expect(sum.querySelectorAll(".zero")).toHaveLength(2);       // zeros muted inline
    const items = host.querySelectorAll(".rule-item");
    expect(items[0].textContent).toContain("All changed rules");
    expect(items[1].textContent).toContain("ceterms:description");
    expect(items[1].textContent).toContain("Description · v1 → v2");
    expect(host.textContent).toContain("Counts are records whose value changed.");
    expect(host.querySelector("h2")!.textContent).toContain("Jared's earlier verdicts");
    const rows = host.querySelectorAll(".crec.cv");
    expect(rows[0].querySelector(".outcome")!.textContent).toBe("fixed");
    // the shared value diff, Split by default: v1 on the left with what's gone marked, v2 on the right
    expect(rows[0].querySelector(".vd.split")).not.toBeNull();
    expect(rows[0].querySelector(".vd-side.del mark")!.textContent).toBe("Prerequisite: GEOG 205. ");
    expect(rows[0].querySelector(".vd-side.del .vd-lab")!.textContent).toBe("ruleset v1");
    expect(rows[0].querySelector(".vd-side.add mark")).toBeNull();
    expect(rows[0].textContent).toContain("Jared: “Prerequisite should be a separate property.”");
    expect(rows[1].querySelector(".outcome")!.textContent).toBe("still correct");
    expect(rows[1].querySelector(".vd.same")).not.toBeNull();
    expect(host.querySelector("details.why1")!.hasAttribute("open")).toBe(false);
  });

  it("links a record To dropped to the ruleset that has it, and To's records to To's ruleset", async () => {
    const card = RESPONSE.rules[0];
    const dropped = { ...card, rule_id: "stub-code", ctdl_property: "ceterms:codedNotation", b_version: null, annotated_rows: [],
      signals: [], sample: [], vanished_rows: [brief("AJ101", "AJ 101", "")], values: { changed: 1, total: 1, new: 0, vanished: 1 } };
    const resp = { ...RESPONSE, a: 2, b: 3, a_extraction: "rs-0002", b_extraction: "rs-0003",
      versions: [...RESPONSE.versions, { version: 3, extraction: "rs-0003", note: null }], rules: [card, dropped] };
    await render("#/c/avc/compare?a=2&b=3", resp);
    const links = [...host.querySelectorAll<HTMLAnchorElement>("a.see")].map((x) => x.getAttribute("href")!);
    expect(links).toContain("#/c/avc/rules/stub-code?row=aj101%40div&ext=rs-0002");  // From's ruleset: v3 has no stub-code
    expect(links).toContain("#/c/avc/rules/course-description?row=geog222%40div");    // To is the latest: no ?ext
    await render("#/c/avc/compare?a=1&b=2", { ...resp, a: 1, b: 2, a_extraction: "rs-0001", b_extraction: "rs-0002" });
    expect(host.querySelector<HTMLAnchorElement>("a.see")!.getAttribute("href")).toBe(
      "#/c/avc/rules/course-description?row=geog222%40div&ext=rs-0002");  // To isn't the latest
  });

  it("saves a note on a changed value with what it was compared with", async () => {
    annotateMock.mockReset().mockResolvedValue({ event: {}, rule: null, elapsed_ms: 1 });
    await render("#/c/avc/compare");
    const row = host.querySelector(".crec.cv")!;
    const note = [...row.querySelectorAll("button")].find((b) => b.textContent === "Note…")!;
    expect([...row.querySelectorAll("button")].some((b) => b.textContent === "The new value is wrong…")).toBe(true);
    await act(async () => { note.click(); });
    const box = row.querySelector("textarea")!;
    await act(async () => {
      Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, "value")!.set!.call(box, "v2 drops the prerequisite, rightly");
      box.dispatchEvent(new Event("input", { bubbles: true }));
    });
    const save = [...row.querySelectorAll("button")].find((b) => b.textContent === "Save note")!;
    await act(async () => { save.click(); });
    const [cat, ev] = annotateMock.mock.calls[0];
    expect(cat).toBe("avc");
    expect(ev).toMatchObject({ type: "comment", note: "v2 drops the prerequisite, rightly", extraction: "rs-0002",
      target: { kind: "match", rule_id: "course-description", occurrence_key: "geog222@div" },
      compared_with: { kind: "ruleset", ruleset: 1, value: expect.stringContaining("Prerequisite: GEOG 205.") } });
  });

  it("links every record to the Rules tab with that record selected", async () => {
    await render("#/c/avc/compare");
    const see = host.querySelector<HTMLAnchorElement>(".crec .see")!;
    expect(see.getAttribute("href")).toBe("#/c/avc/rules/course-description?row=geog222%40div");
    expect(see.textContent).toBe("See on page →");
  });

  it("expands a signal into the records that lost it", async () => {
    await render("#/c/avc/compare");
    const sig = host.querySelector<HTMLElement>(".sigrow")!;
    expect(sig.textContent).toContain("-274");
    expect(host.querySelector(".sigdrill")).toBeNull();
    await act(async () => sig.click());
    const drill = host.querySelector(".sigdrill")!;
    expect(drill.textContent).toContain("− 274 lost it (first 1)");
    expect(drill.querySelector(".ck")!.textContent).toBe("CS120");
  });

  it("pages through every other changed record, 50 at a time by default", async () => {
    await render("#/c/avc/compare");
    expect(recordsMock).toHaveBeenLastCalledWith("avc", { a: 1, b: 2, rule: undefined, offset: 0, limit: 50, order: "shuffle", f: [], seed: 0 });
    expect(host.textContent).toContain("Other changed records 273, in random order");
    expect(host.querySelectorAll(".clist")[1].querySelectorAll(".crec").length).toBe(50);
    expect(host.querySelector("[data-testid=pager]")!.textContent).toContain("1–50 of 273");
    const next = [...host.querySelectorAll<HTMLButtonElement>("[data-testid=pager] button")].find((b) => b.textContent === "Next →")!;
    await act(async () => next.click());
    expect(recordsMock).toHaveBeenLastCalledWith("avc", expect.objectContaining({ offset: 50, limit: 50 }));
    const per = host.querySelector<HTMLSelectElement>("select[aria-label='Per page']")!;
    await act(async () => { per.value = "500"; per.dispatchEvent(new Event("change", { bubbles: true })); });
    expect(recordsMock).toHaveBeenLastCalledWith("avc", expect.objectContaining({ offset: 0, limit: 500 }));
    expect(host.querySelector("[data-testid=pager]")!.textContent).toContain("1–273 of 273");
    try { localStorage.removeItem("studio.compare.pageSize"); } catch { /* jsdom */ }
  });

  it("samples by autostratify with tags, filters by a bar in manual select, and reshuffles", async () => {
    await render("#/c/avc/compare");
    const mode = (name: string) => [...host.querySelectorAll<HTMLButtonElement>(".sm-modes button")].find((b) => b.textContent === name)!;
    await act(async () => mode("Autostratify").click());
    expect(recordsMock).toHaveBeenLastCalledWith("avc", expect.objectContaining({ order: "auto", offset: 0 }));
    expect(host.querySelector("[data-testid=auto-panel]")!.textContent).toContain("Leading label in A: 2 combinations");
    expect(host.querySelector(".sm-tag")!.textContent).toBe("Leading label in A Prerequisite:");
    await act(async () => mode("Manual select").click());
    const bars = host.querySelectorAll<HTMLButtonElement>("[data-testid=sample-bars] .sm-bar");
    expect([...bars].map((b) => b.querySelector(".sm-c")!.textContent)).toEqual(["268", "5"]); // one bar: how many records
    expect(host.querySelector("[data-testid=manual-panel]")!.textContent).toContain("Same for every record: URL pattern");
    await act(async () => bars[0].click());
    expect(recordsMock).toHaveBeenLastCalledWith("avc", expect.objectContaining({ order: "shuffle", f: ["lead_a:Prerequisite:"] }));
    expect(host.textContent).toContain("Other changed records 268 of 273");
    expect(host.querySelector(".sm-chip")!.textContent).toContain("Leading label in A: Prerequisite:");
    await act(async () => mode("Shuffle").click());
    const re = [...host.querySelectorAll<HTMLButtonElement>(".sample button")].find((b) => b.textContent === "Reshuffle")!;
    await act(async () => re.click());
    expect(recordsMock).toHaveBeenLastCalledWith("avc", expect.objectContaining({ order: "shuffle", seed: 1 }));
  });

  it("keeps From / To and the selected rule in the URL", async () => {
    await render("#/c/avc/compare?a=1&b=2&rule=course-description");
    expect(compareMock).toHaveBeenCalledWith("avc", { a: 1, b: 2, rule: "course-description" });
    const from = host.querySelector<HTMLSelectElement>("select[aria-label=from]")!;
    expect(from.value).toBe("1");
    await act(async () => { from.value = "2"; from.dispatchEvent(new Event("change", { bubbles: true })); });
    expect(location.hash).toBe("#/c/avc/compare?a=2&b=2&rule=course-description");
    await act(async () => host.querySelectorAll<HTMLElement>(".rule-item")[0].click());
    expect(location.hash).toBe("#/c/avc/compare?a=1&b=2");
  });

  it("says so when there is only one ruleset version", async () => {
    await render("#/c/avc/compare", { ...RESPONSE, a: 1, b: 1, versions: [RESPONSE.versions[0]], changed_rules: [],
                                      rules: [], records_changed: 0 });
    expect(host.textContent).toContain("Only one ruleset version so far");
    expect(host.querySelector(".sumline")).toBeNull();
  });
});
