import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { setIdentity } from "../shell/reviewer";
import type { CourseDetail } from "../api/types";
import { parseRoute } from "../shell/router";
import type { CatalogDetail } from "../api/types";

const course = vi.fn();
vi.mock("../api/client", () => ({ api: { course: (...a: unknown[]) => course(...a), annotate: vi.fn() } }));
vi.mock("../rules/api", () => ({ apiX: {
  courses: () => Promise.resolve([{ course_key: "GEOG 222", occurrences: 1, line: null }]),
  annotators: () => Promise.resolve({ people: [], waiting: 0, rules: null }),
} }));
vi.mock("../pagepane", () => ({ PagePane: () => null }));
import RecordsTab from "./RecordsTab";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
const COURSE: CourseDetail = { course_key: "GEOG 222", extraction: "rs-0002", occurrences: [{
  occurrence_key: "p1@html", page_stem: "p1", url: "https://x/p1", page_title: "GEOG 222 - Cartography", locator_rule_id: "locator-course-page",
  css_path: "html", properties: [
    { rule_id: "codedNotation", property_label: "Coded Notation", ctdl_property: "ceterms:codedNotation", value: "GEOG 222", status: "found",
      css_path: "html > p", char_start: 0, char_end: 8, state: null, verdict: null, comments: [] },
    { rule_id: "isNonCredit", property_label: "Is Non-Credit", ctdl_property: "ceterms:isNonCredit", value: null, status: "none",
      css_path: null, char_start: null, char_end: null, state: null, verdict: null, comments: [] },
    { rule_id: "estimatedDuration", property_label: "Estimated Duration", ctdl_property: "ceterms:estimatedDuration",
      value: "Lecture - 87.5\nLab - 35", status: "found", css_path: null, char_start: null, char_end: null, state: null, verdict: null, comments: [],
      items: [{ value_index: 0, value: "Lecture - 87.5", css_path: "html > p", char_start: 0, char_end: 14 },
              { value_index: 1, value: "Lab - 35", css_path: "html > p", char_start: 20, char_end: 28 }] },
  ] }] };

let host: HTMLDivElement, root: Root;
const flush = () => act(async () => { await new Promise((r) => setTimeout(r, 0)); });

beforeEach(() => {
  setIdentity("Jared", "sme");
  course.mockReset().mockResolvedValue(COURSE);
  host = document.createElement("div"); document.body.appendChild(host); root = createRoot(host);
});
afterEach(() => { act(() => root.unmount()); host.remove(); });

describe("the Records tab's cards", () => {
  it("shows every property of the course as a card; one with no rule yet says so; a list shows one line per item", async () => {
    await act(async () => {
      root.render(<RecordsTab catalog={{ short: "avc", ruleset_version: 2 } as CatalogDetail} route={parseRoute("#/c/avc/records/GEOG%20222")} reload={() => {}} />);
    });
    await flush();
    const cards = [...host.querySelectorAll(".card")];
    expect(cards.map((c) => c.querySelector(".lbl")!.textContent)).toEqual(["Coded Notation", "Is Non-Credit", "Estimated Duration"]);
    expect(cards[1].querySelector(".tx")!.textContent).toBe("no rule yet");
    expect([...cards[2].querySelectorAll(".item-line")].map((l) => l.textContent)).toEqual(["Lecture - 87.5", "Lab - 35"]);
    expect(cards[2].querySelector(".tx")).toBeNull();
  });
});
