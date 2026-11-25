// Classes in the UI (LearningProgram plan, Phase 4): the class menu (w4-class-menu), the API's class from the address,
// and the Records tab under one class and under All classes (w2-records-lp, w2-records-all).
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { CatalogDetail, ClassSummary } from "../api/types";
import { recordHeading } from "../records/logic";
import { ClassMenu, classLine } from "./ClassMenu";
import { apiClass, inClass, withClass } from "./klass";
import { setIdentity } from "./reviewer";
import { parseRoute } from "./router";

const course = vi.fn();
vi.mock("../api/client", () => ({ api: { course: (...a: unknown[]) => course(...a), annotate: vi.fn() } }));
const HITS = {
  course: [{ record_external_identifier: "ACCT 201", occurrences: 1, line: "ACCT 201 - Principles", name: "Principles", pages: 1 }],
  learningprogram: [
    { record_external_identifier: "2166", occurrences: 1, line: "2166 - Accountancy, M.Acc.", name: "Accountancy, M.Acc.", pages: 1 },
    { record_external_identifier: "program-economics", occurrences: 1, line: null, name: "Economics", pages: 1 }],
};
vi.mock("../rules/api", async () => {
  const k = await import("./klass");
  return { apiX: {
    courses: () => Promise.resolve(HITS[k.apiClass() as keyof typeof HITS]),
    annotators: () => Promise.resolve({ people: [], waiting: 0, rules: null }),
  } };
});
vi.mock("../pagepane", () => ({ PagePane: () => null }));
import RecordsTab from "../records/RecordsTab";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
const sum = (o: Partial<ClassSummary>): ClassSummary => ({
  slug: "course", name: "Course", properties: 37, noun: ["course", "courses"], ruleset_version: 8, rules_total: 45,
  rules_approved: 9, records: 22023, ...o } as ClassSummary);
const CLASSES = [sum({}), sum({ slug: "learningprogram", name: "LearningProgram", properties: 30, noun: ["program", "programs"],
  ruleset_version: 2, rules_total: 32, rules_approved: 0, records: 105 })];
const CAT = { short: "wvu", ruleset_version: 8, classes: CLASSES } as unknown as CatalogDetail;

let host: HTMLDivElement, root: Root;
const flush = () => act(async () => { for (let i = 0; i < 4; i++) await new Promise((r) => setTimeout(r, 0)); });
beforeEach(() => {
  setIdentity("Jared", "sme");
  course.mockReset().mockResolvedValue({ record_external_identifier: "2166", extraction: "rs-0001", occurrences: [] });
  host = document.createElement("div"); document.body.appendChild(host); root = createRoot(host);
});
afterEach(() => { act(() => root.unmount()); host.remove(); location.hash = ""; });

describe("the class menu", () => {
  it("lists each class with what it has here, then All classes; picking one keeps the tab", async () => {
    location.hash = "#/c/wvu/learningprogram/rules";
    await act(async () => root.render(<ClassMenu catalog={CAT} cls="learningprogram" tab="records" />));
    const chip = host.querySelector<HTMLButtonElement>("[data-testid=class-chip]")!;
    expect(chip.textContent).toBe("LearningProgram");
    await act(async () => chip.click());
    expect([...host.querySelectorAll("[role=menuitem]")].map((b) => b.textContent)).toEqual([
      "Course45 rules, 22,023 courses, 9 approved", "LearningProgram32 rules, 105 programs, 0 approved",
      "All classesBoth classes' rules in one list"]);
    expect(host.querySelector("[role=menuitem].on")!.textContent).toContain("LearningProgram");
    await act(async () => host.querySelectorAll<HTMLButtonElement>("[role=menuitem]")[2].click());
    expect(location.hash).toBe("#/c/wvu/all/records");
  });

  it("says a class with no rules has none yet", () => {
    expect(classLine(sum({ ruleset_version: null, properties: 30 }))).toBe("30 properties, no rules yet");
  });
});

describe("the API's class", () => {
  it("is the address's class, else the record's ?in=, else the rule id's, else Course (which is never sent)", () => {
    location.hash = "#/c/wvu/learningprogram/rules";
    expect(withClass("/api/catalogs/wvu/rules")).toBe("/api/catalogs/wvu/rules?class=learningprogram");
    location.hash = "#/c/wvu/course/rules";
    expect(withClass("/api/catalogs/wvu/rules?x=1")).toBe("/api/catalogs/wvu/rules?x=1");
    location.hash = "#/c/wvu/all/records/2166?in=learningprogram";
    expect(apiClass()).toBe("learningprogram");
    location.hash = "#/c/wvu/all/rules/locator-learningprogram-page";
    expect(apiClass()).toBe("learningprogram");
    location.hash = "#/c/wvu/all/rules/course-name";
    expect(apiClass()).toBe("course");
    expect(inClass("learningprogram", () => withClass("/api/catalogs/wvu/courses"))).toBe("/api/catalogs/wvu/courses?class=learningprogram");
    expect(withClass("/api/agent-runs/queue")).toBe("/api/agent-runs/queue");  // not a catalog's
  });
});

describe("the Records tab with classes", () => {
  it("lists one class's records by name, a generated identifier greyed", async () => {
    location.hash = "#/c/wvu/learningprogram/records/2166";
    await act(async () => root.render(<RecordsTab catalog={CAT} route={parseRoute(location.hash)} reload={() => {}} />));
    await flush();
    expect(host.querySelector<HTMLInputElement>(".search")!.placeholder).toBe("Find a program by name or identifier");
    const items = [...host.querySelectorAll(".course-item.named")];
    expect(items.map((i) => [i.querySelector(".t")!.textContent, i.querySelector(".c")!.textContent])).toEqual([
      ["Accountancy, M.Acc.", "2166"], ["Economics", "program-economics"]]);
    expect(items.map((i) => i.querySelector(".c")!.classList.contains("gen"))).toEqual([false, true]);
    expect(host.querySelector(".cls-h")).toBeNull();
  });

  it("with All classes, lists each class under a heading that folds, the record's class open", async () => {
    location.hash = "#/c/wvu/all/records/2166?in=learningprogram";
    await act(async () => root.render(<RecordsTab catalog={CAT} route={parseRoute(location.hash)} reload={() => {}} />));
    await flush();
    const heads = [...host.querySelectorAll<HTMLButtonElement>(".cls-h")];
    expect(heads.map((h) => [h.textContent, h.getAttribute("aria-expanded")])).toEqual([
      ["Course22,023 courses", "false"], ["LearningProgram105 programs", "true"]]);
    expect([...host.querySelectorAll(".course-item.named .c")].map((c) => c.textContent)).toEqual(["2166", "program-economics"]);
    expect(host.querySelector(".course-item.on")!.getAttribute("href")).toContain("in=learningprogram");
    await act(async () => heads[0].click());
    expect([...host.querySelectorAll(".course-item.named .c")].map((c) => c.textContent)).toEqual(
      ["ACCT 201", "2166", "program-economics"]);
    expect(host.querySelector<HTMLInputElement>(".search")!.placeholder).toBe("Find a course or a program");
  });

  it("heads a program with its name, a course with its code and title", () => {
    const cards = [{ ctdl_property: "ceterms:name", values: [{ value: "Accountancy, M.Acc." }] }] as never;
    expect(recordHeading(cards, "2166", "learningprogram")).toBe("Accountancy, M.Acc.");
    expect(recordHeading([], "program-x", "learningprogram")).toBe("program-x");
  });
});
