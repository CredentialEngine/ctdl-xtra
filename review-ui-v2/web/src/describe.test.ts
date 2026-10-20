import { describe, expect, it } from "vitest";
import { describeTarget } from "./components/NotesDrawer";
import type { Note } from "./types";

const note = (scope: Note["scope"], target: string | null) =>
  ({ id: "1", scope, target, text: "t", author: "Seth", at: "x" }) as Note;

describe("describeTarget", () => {
  it("shows record and property for a field note", () => {
    expect(describeTarget(note("field", "GEOG222::Credit Value::https://x/y::0"))).toBe(
      "GEOG222 · Credit Value",
    );
  });
  it("shows the label name for a label note", () => {
    expect(describeTarget(note("field", "label::https://x/y::Course::label-course-page"))).toBe(
      "label · Course",
    );
  });
  it("leaves rule and property targets as they are", () => {
    expect(describeTarget(note("rule", "course-name"))).toBe("course-name");
  });
});
