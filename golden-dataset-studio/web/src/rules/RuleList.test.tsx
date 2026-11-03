import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { RuleGroup, RuleSummary, RulesResponse } from "../api/types";
import { RuleList } from "./RuleList";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const rule = (o: Partial<RuleSummary>): RuleSummary => ({
  rule_id: "course-description", kind: "property", version: 1, title: "Description", subtitle: "ceterms:description",
  ctdl_property: "ceterms:description", property_label: "Description", locator: "locator-course-page", status: "in review",
  reviewed: 14, total: 1062, open_wrong: 0, open_missing: 0, questions: 0, approved_by: null, approved_at: null, comments: 0,
  required: false, course_key: false, no_rule: false, list: false, path_shown: null, parent_label: null, input: "the course record", ...o });
const credit = rule({ rule_id: "creditValue", title: "Credit Value", subtitle: "ceterms:creditValue", ctdl_property: "ceterms:creditValue",
  property_label: "Credit Value", reviewed: 9 });
const minValue = rule({ rule_id: "creditUnitMinValue", title: "Credit Unit Min Value", subtitle: "part of Credit Value",
  ctdl_property: "ceterms:creditValue>schema:minValue", property_label: "Credit Unit Min Value", parent_label: "Credit Value" });
const isNonCredit = rule({ rule_id: "isNonCredit", title: "Is Non-Credit", subtitle: "ceterms:isNonCredit", ctdl_property: "ceterms:isNonCredit",
  property_label: "Is Non-Credit", no_rule: true });
const unitType = rule({ rule_id: "creditUnitType", title: "Credit Unit Type", subtitle: "part of Credit Value", ctdl_property: "ceterms:creditValue>schema:unitType",
  property_label: "Credit Unit Type", parent_label: "Credit Value", no_rule: true });
const coded = rule({ rule_id: "codedNotation", title: "Coded Notation", subtitle: "ceterms:codedNotation", ctdl_property: "ceterms:codedNotation",
  property_label: "Coded Notation", required: true, course_key: true, reviewed: 31 });
const estimated = rule({ rule_id: "estimatedDuration", title: "Estimated Duration", subtitle: "ceterms:estimatedDuration", ctdl_property: "ceterms:estimatedDuration",
  property_label: "Estimated Duration", list: true, reviewed: 5 });
const language = rule({ rule_id: "course-language", title: "Language", subtitle: "ceterms:inLanguage", ctdl_property: "ceterms:inLanguage",
  property_label: "Language", status: "approved", required: true, reviewed: 14 });

const group = (o: Partial<RuleGroup> & Pick<RuleGroup, "id" | "label" | "rules">): RuleGroup =>
  ({ kind: "property", collapsed: false, approved: o.rules.filter((r) => r.status === "approved").length, ...o });
// the server's order (Required first, Other by reviewed counts, Not started last, shut)
const GROUPS: RuleGroup[] = [
  group({ id: "required", label: "Required", rules: [coded, language] }),
  group({ id: "other", label: "Other properties", rules: [estimated, credit, minValue] }),
  group({ id: "not-started", label: "Not started", collapsed: true, rules: [isNonCredit, unitType] }),
];
const rules: RulesResponse = { extraction: "rs-0002", ruleset_version: 2, groups: GROUPS };

let host: HTMLDivElement, root: Root;
const onPick = vi.fn();
const render = (groups = rules) => act(async () => { root.render(<RuleList rules={groups} active={null} onPick={onPick} />); });
const input = () => host.querySelector<HTMLInputElement>("input.rule-search")!;
const type = async (text: string) => {
  const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")!.set!;
  await act(async () => { setter.call(input(), text); input().dispatchEvent(new Event("input", { bubbles: true })); });
};
const key = async (el: Element, k: string) => act(async () => { el.dispatchEvent(new KeyboardEvent("keydown", { key: k, bubbles: true })); });
const header = (id: string) => host.querySelector<HTMLButtonElement>(`[data-group=${id}] > .group-h`)!;
const items = () => [...host.querySelectorAll<HTMLElement>(".rule-item[data-rule]")].map((e) => e.dataset.rule);

beforeEach(() => {
  onPick.mockReset();
  host = document.createElement("div"); document.body.appendChild(host); root = createRoot(host);
});
afterEach(() => { act(() => root.unmount()); host.remove(); });

describe("the rule list's groups (property-rules spec §4.8)", () => {
  it("lists the groups in the server's order, with their approved counts, and starts Not started shut", async () => {
    await render();
    expect([...host.querySelectorAll(".group-h")].map((g) => g.textContent)).toEqual([
      "Required1 of 2 approved", "Other properties0 of 3 approved", "Not started2 properties"]);
    expect(items()).toEqual(["codedNotation", "course-language", "estimatedDuration", "creditValue", "creditUnitMinValue"]);
    expect(header("not-started").getAttribute("aria-expanded")).toBe("false");
  });

  it("opens and shuts a group from its header", async () => {
    await render();
    await act(async () => header("not-started").click());
    expect(header("not-started").getAttribute("aria-expanded")).toBe("true");
    expect(items()).toContain("isNonCredit");
    await act(async () => header("not-started").click());
    expect(items()).not.toContain("isNonCredit");
  });

  it("a child says part of its parent, without a path; a course key and a list are tagged", async () => {
    await render();
    const child = host.querySelector<HTMLElement>("[data-rule=creditUnitMinValue] .id")!;
    expect(child.textContent).toBe("part of Credit Value");
    expect(child.classList.contains("plain")).toBe(true);
    expect(host.querySelector("[data-rule=codedNotation] .rl-tag")!.textContent).toBe("course key");
    expect(host.querySelector("[data-rule=estimatedDuration] .rl-tag")!.textContent).toBe("list");
    expect(host.querySelector("[data-rule=creditUnitMinValue] .rl-tag")).toBeNull();
  });
});

describe("searching the rules (m4)", () => {
  beforeEach(async () => { await render(); });

  it("/ focuses the search from anywhere on the page", async () => {
    await act(async () => { window.dispatchEvent(new KeyboardEvent("keydown", { key: "/" })); });
    expect(document.activeElement).toBe(input());
  });

  it("matches the name, the CTDL term and the parent's name; collapsed groups open while there is text", async () => {
    await type("credit");
    expect(items()).toEqual(["creditValue", "creditUnitMinValue", "isNonCredit", "creditUnitType"]);
    expect(header("other").getAttribute("aria-expanded")).toBe("true");
    expect(header("not-started").getAttribute("aria-expanded")).toBe("true");
    expect(header("other").textContent).toContain("2 of 3 match");
    expect(header("not-started").textContent).toContain("2 of 2 match");
    expect(host.querySelector("[data-rule=creditUnitType] mark")!.textContent).toBe("Credit");
    expect(host.querySelector("[data-rule=creditUnitMinValue] .id mark")!.textContent).toBe("Credit");
  });

  it("names the groups with no match in one grey line", async () => {
    await type("credit");
    expect(host.querySelector(".rl-nomatch")!.textContent).toBe("Required: no match");
    expect(host.querySelector("[data-group=required]")).toBeNull();
  });

  it("Esc clears the search, and the groups go back to their own state", async () => {
    await type("credit");
    await key(input(), "Escape");
    expect(input().value).toBe("");
    expect(items()).toEqual(["codedNotation", "course-language", "estimatedDuration", "creditValue", "creditUnitMinValue"]);
    expect(header("not-started").getAttribute("aria-expanded")).toBe("false");
  });

  it("↓ moves to the first result; Enter opens it; Enter in the search opens the first result", async () => {
    await type("credit");
    await key(input(), "ArrowDown");
    expect(document.activeElement).toBe(host.querySelector("[data-rule=creditValue]"));
    await key(host.querySelector("[data-rule=creditValue]")!, "Enter");
    expect(onPick).toHaveBeenLastCalledWith("creditValue");
    await act(async () => input().focus());
    await key(input(), "Enter");
    expect(onPick).toHaveBeenLastCalledWith("creditValue");
  });
});
