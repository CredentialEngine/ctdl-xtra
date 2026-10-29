// A link to one row that this ruleset doesn't show (Compare's "See on page →" for AJ 101's program-page line, whose
// rule ruleset v3 dropped): the Rules tab says so plainly and still shows the saved page, never a blank column.
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { setIdentity } from "../shell/reviewer";
import type { CatalogDetail, RulesResponse, RuleSummary } from "../api/types";
import { parseRoute } from "../shell/router";
import type { RowX } from "./api";
import { focusStem } from "./NotHere";
import RulesTab from "./RulesTab";
import type { PagePaneProps } from "../pagepane/PagePane";

const pane: { props: PagePaneProps | null } = { props: null };
vi.mock("../pagepane", async (orig) => ({
  ...(await orig<typeof import("../pagepane")>()),
  PagePane: (p: PagePaneProps) => { pane.props = p; return <div data-testid="pane" />; },
}));

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const catalog = { catalog: "avc-x", short: "avc", name: "AVC", institution: "AVC", logo: null, crawl: "c", crawl_started: "",
  pages: 1467, extraction: "rs-0003", ruleset_version: 3, extractions: [
    { extraction: "rs-0002", ruleset_version: 2, parent_extraction: null },
    { extraction: "rs-0003", ruleset_version: 3, parent_extraction: "rs-0002" }], rulesets: [], authors: [], pane_css: "", root: "",
} as CatalogDetail;

const summary = (o: Partial<RuleSummary> = {}): RuleSummary => ({
  rule_id: "course-code", kind: "field", version: 1, title: "Coded Notation", subtitle: "ceterms:codedNotation",
  ctdl_property: "ceterms:codedNotation", property_label: "Coded Notation", locator: "locator-course-page", status: "in review",
  reviewed: 0, total: 1062, open_wrong: 0, open_missing: 0, questions: 0, approved_by: null, approved_at: null, comments: 0, ...o,
});
const rules: RulesResponse = { extraction: "rs-0003", ruleset_version: 3, groups: [
  { kind: "field", label: "Field rules", approved: 0, rules: [summary()] }] };
const row: RowX = {
  key: "p0@html", occurrence_key: "p0@html", course_key: "GEOG0", page_stem: "p0", url: "https://x/p0", page_title: "Page 0",
  value: "GEOG 0", status: "found", css_path: "html", char_start: 0, char_end: 5, occurrence_css_path: "html", context: "",
  state: null, verdict: null, reattached: false, comments: [], signal_count: 0, other_pages: [], group: null,
} as RowX;
const STEM = "avc-program-administration-of-justice-aa-25fef01d2e";
const KEY = `${STEM}@html > body:nth-of-type(1)`;

let container: HTMLDivElement, root: Root, urls: string[];
const json = (body: unknown, status = 200) =>
  Promise.resolve(new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } }));

beforeEach(() => {
  setIdentity("Jared", "sme");
  urls = [];
  vi.stubGlobal("fetch", vi.fn((url: string) => {
    const u = String(url);
    urls.push(u);
    const ext = new URL(u, "http://x").searchParams.get("ext");
    if (u.includes("/meta")) return json({ stem: STEM, url: "https://avc/program/aj", title: "Administration of Justice AA" });
    if (u.includes("/rules/stub-code")) return ext === "rs-0002" ? json(summary({ rule_id: "stub-code" }))
      : json({ detail: "stub-code is not in ruleset v3" }, 404);
    if (u.endsWith("/rules") || u.includes("/rules?")) return json(rules);
    if (u.includes("/annotators")) return json({ people: [{ name: "Jared Diener", role: "sme", values: 14 }], waiting: 0, rules: {} });
    if (u.includes("/rows")) return json({ rule_id: "course-code", extraction: "rs-0003", total: 1, offset: 0, missing: [],
      elapsed_ms: 1, focus_index: null, rows: [row], spread: { by: "", groups: [] } });
    if (/\/rules\/[^/?]+(\?|$)/.test(u)) return json({ ...summary(), definition: {}, what: "", how: "", why: "", examples: [],
      depends_on: [], content_hash: "", published_by: null, published_at: null, parent_version: null, versions: [1],
      fill: { rows: 1, found: 1 }, signal_counts: {}, settings: {} });
    return json({});
  }));
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
});
afterEach(() => { act(() => root.unmount()); container.remove(); vi.unstubAllGlobals(); pane.props = null; });

async function render(hash: string) {
  await act(async () => { root.render(<RulesTab catalog={catalog} route={parseRoute(hash)} reload={() => {}} />); });
  for (let i = 0; i < 4; i++) await act(async () => { await new Promise((r) => setTimeout(r, 0)); });
}

describe("a linked row this ruleset doesn't show", () => {
  it("names the page of a row key or page stem, not of a course key", () => {
    expect(focusStem(KEY)).toBe(STEM);
    expect(focusStem(STEM)).toBe(STEM);
    expect(focusStem("AJ101")).toBeNull();
  });

  it("says a rule the ruleset dropped has no value here, links to the ruleset that has it, and shows the page", async () => {
    await render(`#/c/avc/rules/stub-code?row=${encodeURIComponent(KEY)}`);
    const box = container.querySelector("[data-testid=not-here]")!;
    expect(box.textContent).toContain("This record has no value in ruleset v3: this ruleset has no rule stub-code.");
    expect(box.querySelector("a")!.textContent).toBe("See it in ruleset v2 →");
    expect(box.querySelector("a")!.getAttribute("href")).toBe(`#/c/avc/rules/stub-code?${new URLSearchParams({ row: KEY, ext: "rs-0002" })}`);
    expect(pane.props!.tabs.map((t) => [t.stem, t.url, t.title])).toEqual([[STEM, "https://avc/program/aj", "Administration of Justice AA"]]);
    expect(pane.props!.activeStem).toBe(STEM);
  });

  it("says the rule found no value for it, selects no other row, shows its page, and isn't hidden by the default Annotated by", async () => {
    await render(`#/c/avc/rules/course-code?row=${encodeURIComponent(KEY)}`);
    expect(urls.find((u) => u.includes("/rows"))).not.toContain("by=");  // a link to one row: everyone's rows
    expect(container.querySelector("[data-testid=not-here]")!.textContent)
      .toContain("This record has no value for Coded Notation in ruleset v3:");
    expect(container.querySelector(".row.on")).toBeNull();
    expect(pane.props!.activeStem).toBe(STEM);
  });
});
