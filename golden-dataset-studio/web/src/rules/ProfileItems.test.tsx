// sme-fixes §5 and §6 in the Rules tab: a list-of-objects row (a ✓ ✕ per object, adding one by labelling its fields on
// the page), the three ways a rule ends ("not on the page" is its claim, dashed where it looked), and "Why wrong?".
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { setIdentity } from "../shell/reviewer";
import type { CatalogDetail, RuleDetail, RulesResponse, RuleSummary } from "../api/types";
import { parseRoute } from "../shell/router";
import type { RowX, RowsX } from "./api";
import RulesTab from "./RulesTab";
import type { PagePaneProps } from "../pagepane/PagePane";
import { addComplete, addSavable, emptyAdd, labelField, objectEvent, objectOf, profileOf, statusWords } from "./claims";

const pane: { props: PagePaneProps | null } = { props: null };
vi.mock("../pagepane", async (orig) => ({
  ...(await orig<typeof import("../pagepane")>()),
  PagePane: (p: PagePaneProps) => { pane.props = p; return <div data-testid="pane">{p.banner}{p.legend}</div>; },
}));

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const catalog = { catalog: "avc-x", short: "avc", name: "AVC", institution: "AVC", logo: null, crawl: "c", crawl_started: "", pages: 1,
  extraction: "rs-0009", ruleset_version: 9, extractions: [{ extraction: "rs-0009", ruleset_version: 9, parent_extraction: null }],
  rulesets: [], authors: [], pane_css: "", root: "" } as CatalogDetail;

const D = "ceterms:description", T = "ceterms:timeRequired";
const summary = (o: Partial<RuleSummary> = {}): RuleSummary => ({
  rule_id: "course-estimated-duration", kind: "property", version: 3, title: "Estimated Duration", subtitle: "ceterms:estimatedDuration",
  ctdl_property: "ceterms:estimatedDuration", property_label: "Estimated Duration", locator: "locator-course-page", status: "in review",
  reviewed: 0, total: 1062, open_wrong: 0, open_missing: 0, questions: 0, approved_by: null, approved_at: null, comments: 0, ...o,
});
const rules: RulesResponse = { extraction: "rs-0009", ruleset_version: 9, groups: [
  { id: "other", kind: "property", label: "Other properties", collapsed: false, approved: 0, rules: [summary(), summary({ rule_id: "course-prerequisite-description", title: "Prerequisite: Description" })] }] };
const profile = { fields: { [D]: { regex: "(Total Course .*Hours)" }, [T]: { regex: "Hours\\s*(\\S.*)" } }, key: D };
const detail = (o: Partial<RuleDetail> = {}): RuleDetail => ({
  ...summary(), definition: { locator: "locator-course-page", selector: ".infocard", multiple: { split: "regex", regex: "x" }, profile },
  what: "", how: "", why: "", examples: [], depends_on: [], content_hash: "sha256:abc", published_by: null, published_at: null,
  parent_version: 2, versions: [1, 2, 3], fill: { rows: 1, found: 1 }, signal_counts: {}, settings: { content_root: "main" }, list: true, ...o,
} as RuleDetail);

const P = "html > body > div:nth-of-type(3)";
const field = (text: string, at: number) => ({ text, css_path: P, char_start: at, char_end: at + text.length });
const obj = (i: number, d: string, t: string, state: "correct" | "wrong" | null = null) => ({
  value_index: i, value: JSON.stringify({ [D]: d, [T]: t }), css_path: P, char_start: 0, char_end: 5, state, verdict: null, human: false,
  fields: { [D]: field(d, i * 100), [T]: field(t, i * 100 + 60) } });
const row = (o: Partial<RowX> = {}): RowX => ({
  key: "acct199@html", occurrence_key: "acct199@html", course_key: "ACCT199", page_stem: "acct199", url: "https://x/acct199",
  page_title: "ACCT199", value: "…", status: "found", css_path: P, char_start: 0, char_end: 5, occurrence_css_path: "html",
  context: "ACCT 199 - Work Experience", state: null, verdict: null, reattached: false, comments: [], signal_count: 0, other_pages: [],
  group: null, missing_items: [],
  items: [obj(0, "Total Course In-Class (Contact) Hours", "54.0 - 432.0", "correct"), obj(1, "Total Course Out-of-Class Hours", "0.0 - 0.0"),
          obj(2, "Total Course Lecture Hours", "0.0"), obj(3, "Minimum Credit Units", "1.0", "wrong")], ...o,
});
const rowsOf = (rs: RowX[]): RowsX => ({ rule_id: "x", extraction: "rs-0009", total: rs.length, offset: 0, missing: [], elapsed_ms: 1,
  focus_index: 0, spread: { by: "", groups: [] }, rows: rs });

let posted: Record<string, unknown>[] = [];
let container: HTMLDivElement;
let root: Root;
const json = (body: unknown) => Promise.resolve(new Response(JSON.stringify(body), { status: 200, headers: { "Content-Type": "application/json" } }));

function serve(d: RuleDetail, r: RowsX) {
  vi.stubGlobal("fetch", vi.fn((url: string, init?: RequestInit) => {
    const u = String(url);
    if (init?.method === "POST") {
      const ev = JSON.parse(String(init.body));
      posted.push(ev);
      return json({ event: { ...ev, annotation_id: `an-${posted.length}`, at: "now", note: ev.note ?? null, expected: ev.expected ?? null,
                             verdict: ev.verdict ?? null, target: { ...ev.target, rule_version_seen: 3 } }, rule: summary(), elapsed_ms: 1 });
    }
    if (u.endsWith("/rules")) return json(rules);
    if (u.includes("/rows")) return json(r);
    if (/\/rules\/[^/?]+$/.test(u)) return json(d);
    return json({});
  }));
}

async function render(hash = "#/c/avc/rules/course-estimated-duration?by=anyone") {
  await act(async () => { root.render(<RulesTab catalog={catalog} route={parseRoute(hash)} reload={() => {}} />); });
  await act(async () => { await new Promise((r) => setTimeout(r, 0)); });
}

beforeEach(() => {
  setIdentity("Jared", "sme");
  posted = [];
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
});
afterEach(() => { act(() => root.unmount()); container.remove(); vi.unstubAllGlobals(); });

describe("claims helpers", () => {
  it("words a rule's three outcomes", () => {
    expect(statusWords("found", "3.0")).toBe("3.0");
    expect(statusWords("absent", null)).toBe("Not on the page (rule's claim)");
    expect(statusWords("no_match", null)).toBe("Nothing found · the rule made no claim; check the page");
    expect(statusWords("empty", null)).toBe("Nothing found · the rule made no claim; check the page");
    expect(statusWords("none", null)).toBe("no rule yet");
  });
  it("reads a profile rule and builds the object a reviewer labels", () => {
    expect(profileOf({ profile })).toEqual({ fields: [D, T], key: D });
    expect(profileOf({ selector: "x" })).toBeNull();
    expect(objectOf({ value: JSON.stringify({ [D]: "a", [T]: "1" }) })).toEqual({ [D]: "a", [T]: "1" });
    const sel = (text: string) => ({ text, css_path: P, char_start: 1, char_end: 4, prefix: "", suffix: "" });
    let a = labelField({ ...emptyAdd(), pending: sel("Total Course Lab Hours ") }, D);
    expect(addSavable(a, D) && !addComplete(a, [D, T])).toBe(true);
    a = labelField({ ...a, pending: sel("432.0") }, T);
    expect(addComplete(a, [D, T])).toBe(true);
    expect(objectEvent("Jared", "r", "o", a, [D, T])).toMatchObject({ verdict: "missing", target: { item: true, occurrence_key: "o" },
      expected: { objects: [{ fields: { [D]: { text: "Total Course Lab Hours", css_path: P }, [T]: { text: "432.0" } } }] } });
  });
});

describe("a list of objects", () => {
  it("shows one sub-row per object, fields side by side, a ✓ ✕ each; one ✕ makes the row wrong", async () => {
    serve(detail(), rowsOf([row()]));
    await render();
    const objs = [...container.querySelectorAll(".row.on [data-testid=object]")];
    expect(objs).toHaveLength(4);
    expect(objs[0].textContent).toContain("Total Course In-Class (Contact) Hours description");
    expect(objs[0].textContent).toContain("54.0 - 432.0 timeRequired");
    expect(container.querySelector(".row.on .obj-wrong")!.textContent).toBe("1 ✕ → row wrong");
    expect(container.querySelector(".row.on .cb.ok")).toBeNull();  // no ✓ ✕ for the whole row
    await act(async () => container.querySelector<HTMLButtonElement>("[aria-label='Correct 2']")!.click());
    expect(posted[0]).toMatchObject({ verdict: "correct", target: { item: true, value_index: 2, rule_id: "course-estimated-duration" } });
    // each field is outlined where it is on the page
    expect(pane.props!.highlights.filter((h) => h.id.startsWith("item-0-")).map((h) => h.text)).toEqual(
      ["Total Course In-Class (Contact) Hours", "54.0 - 432.0"]);
  });

  it("+ Add a duration: select a piece, label it with a field name; saved once every field is labelled", async () => {
    serve(detail(), rowsOf([row()]));
    await render();
    expect(pane.props!.captureSelection).toBe(false);
    await act(async () => container.querySelector<HTMLButtonElement>(".row.on .add-item")!.click());
    expect(container.querySelector(".row.on .add-item")).toBeNull();
    expect(pane.props!.captureSelection).toBe(true);
    const sel = (text: string, at: number) => ({ text, css_path: P, char_start: at, char_end: at + text.length, prefix: "", suffix: "" });
    await act(async () => pane.props!.onSelection!(sel("Total Course Lab Hours", 300)));
    const labels = () => [...container.querySelectorAll(".row.on .label-bar .lbl")].map((b) => b.textContent);
    expect(labels()).toEqual(["description", "timeRequired"]);
    expect(container.querySelector("[data-testid=pane]")!.textContent).toContain("Which field is it?");
    await act(async () => container.querySelector<HTMLButtonElement>(".row.on .label-bar .lbl")!.click());
    expect(posted).toHaveLength(0);
    expect(container.querySelector<HTMLButtonElement>(".row.on .add-obj .save")!.disabled).toBe(false);  // the key field is there
    expect(pane.props!.highlights.some((h) => h.id === `obj-${D}`)).toBe(true);
    await act(async () => pane.props!.onSelection!(sel("432.0", 360)));
    await act(async () => [...container.querySelectorAll<HTMLButtonElement>(".row.on .label-bar .lbl")][1].click());
    expect(posted[0]).toMatchObject({ type: "verdict", verdict: "missing", target: { kind: "match", item: true, occurrence_key: "acct199@html" },
      expected: { objects: [{ fields: { [D]: { text: "Total Course Lab Hours", char_start: 300 }, [T]: { text: "432.0", char_start: 360 } } }] } });
    expect(container.querySelector(".row.on [data-testid=added-object]")!.textContent).toContain("Total Course Lab Hours");
  });
});

describe("not on the page", () => {
  const prereq = (o: Partial<RowX>) => ({ ...row(), items: undefined, ...o });
  const flat = detail({ rule_id: "course-prerequisite-description", list: false, definition: { locator: "locator-course-page", selector: "p.prereq",
    absent_if: { within: ".details", missing: ".prereq" } } });

  it("reads 'Not on the page (rule's claim)' with the box the rule looked in dashed; 'Nothing found' claims nothing", async () => {
    serve(flat, rowsOf([prereq({ status: "absent", value: null, css_path: "html > body > div:nth-of-type(1)", char_start: null, char_end: null }),
                        prereq({ key: "k2", occurrence_key: "k2", status: "no_match", value: null, css_path: null })]));
    await render("#/c/avc/rules/course-prerequisite-description?by=anyone");
    expect(container.querySelector(".row.on [data-testid=row-full-value]")!.textContent).toBe("Not on the page (rule's claim)");
    expect(container.querySelector(".row.on .valbox")!.className).toContain("claim");
    expect(pane.props!.highlights.map((h) => [h.id, h.kind])).toEqual([["looked", "looked"]]);
    expect(container.querySelector("[data-testid=pane]")!.textContent).toContain("claims this property isn't on the page");
    expect(container.querySelectorAll(".row")[1].textContent).toContain("Nothing found · the rule made no claim; check the page");
  });

  it("✕ shows 'Why wrong?'; ticking Not on the page saves it as a reason", async () => {
    serve(flat, rowsOf([prereq({ value: "Grade Mode: Normal Grading Mode" })]));
    await render("#/c/avc/rules/course-prerequisite-description?by=anyone");
    expect(container.querySelector("[data-testid=why-wrong]")).toBeNull();  // only after ✕
    await act(async () => container.querySelector<HTMLButtonElement>(".row.on .cb.no")!.click());
    const box = container.querySelector<HTMLLabelElement>("[data-testid=why-wrong] .why-r")!;
    expect(box.title).toBe("This course's page doesn't state this property anywhere.");
    await act(async () => box.querySelector("input")!.click());
    await act(async () => container.querySelector<HTMLButtonElement>(".row.on .save")!.click());
    expect(posted[0]).toMatchObject({ type: "verdict", verdict: "wrong", reasons: ["not_on_page"] });
  });
});
