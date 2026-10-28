import { describe, expect, it } from "vitest";
import type { CourseDetail, CourseField } from "../api/types";
import { courseHeading, foldLine, foundOn, groupCards, splitCards, valueKey } from "./logic";

const f = (rule_id: string, property_label: string, ctdl: string | null, value: string): CourseField => ({
  rule_id, property_label, ctdl_property: ctdl, value, status: "found", css_path: "html", char_start: 0, char_end: 1,
  state: null, verdict: null, comments: [],
});

const geog: CourseDetail = {
  course_key: "GEOG222", extraction: "rs-0002",
  occurrences: [
    { occurrence_key: "c@1", page_stem: "course", url: "u1", page_title: "GEOG 222 - Cartography", locator_rule_id: "locator-course-page", css_path: "html",
      fields: [f("course-code", "Coded Notation", "ceterms:codedNotation", "GEOG 222"), f("course-name", "Learning Opportunity Name", "ceterms:name", "Cartography"),
               f("course-description", "Description", "ceterms:description", "This course…")] },
    { occurrence_key: "p@1", page_stem: "prog", url: "u2", page_title: "GIS Cert", locator_rule_id: "locator-program-requirement", css_path: "html",
      fields: [f("stub-code", "Coded Notation", "ceterms:codedNotation", "GEOG222"), f("stub-name", "Learning Opportunity Name", "ceterms:name", "Cartography")] },
  ],
};

describe("records", () => {
  it("groups fields by property across occurrences, numbered", () => {
    const cards = groupCards(geog);
    expect(cards.map((c) => [c.n, c.property, c.values.length])).toEqual([
      [1, "Coded Notation", 2], [2, "Learning Opportunity Name", 2], [3, "Description", 1]]);
    expect(cards[0].values[1]).toMatchObject({ occurrence_key: "p@1", on_course_page: false, page_stem: "prog" });
    expect(valueKey(cards[0].values[0])).toBe("course-code|c@1");
  });
  it("says where the course was found and names it", () => {
    expect(foundOn(geog)).toBe("Found on 2 pages: its course page and 1 program page that lists it");
    expect(courseHeading(groupCards(geog), "GEOG222")).toBe("GEOG 222 · Cartography");
  });
});

describe("Annotated by on a course (Evals spec §6.8)", () => {
  it("puts the person's fields first and folds the rest", () => {
    const d: CourseDetail = { ...geog, occurrences: [{ ...geog.occurrences[0], fields: geog.occurrences[0].fields.map((x, i) => (i === 1
      ? { ...x, annotators: { "Jared Diener": { kinds: ["correct"], at: "t" } } } : i === 2 ? { ...x, engineer_checked: true } : x)) }] };
    const cards = groupCards(d);
    const names = (cs: typeof cards) => cs.map((c) => c.property);
    expect(names(splitCards(cards, "Jared Diener").mine)).toEqual(["Learning Opportunity Name"]);
    expect(splitCards(cards, "Jared Diener").folded).toHaveLength(2);
    expect(names(splitCards(cards, "waiting").mine)).toEqual(["Description"]);
    expect(splitCards(cards, "nobody").folded).toEqual([]);
    expect(splitCards(cards, null).mine).toBe(cards);
    expect(foldLine(4, "Jared Diener")).toBe("4 fields Jared Diener didn't annotate");
    expect(foldLine(1, "waiting")).toBe("1 field not waiting for an expert");
  });
});
