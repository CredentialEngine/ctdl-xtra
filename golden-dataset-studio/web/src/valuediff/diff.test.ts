import { describe, expect, it } from "vitest";
import { fmtDay, sameText, sides, wordDiff } from "./diff";

describe("the shared value diff", () => {
  it("marks what only the left has on the left, and what only the right has on the right", () => {
    const { left, right } = sides("Prerequisite: GEOG 205. This course surveys GIS.", "This course surveys GIS data.");
    expect(left.filter((p) => p.op === "del").map((p) => p.text)).toEqual(["Prerequisite: GEOG 205. ", "GIS."]);
    expect(right.filter((p) => p.op === "add").map((p) => p.text)).toEqual(["GIS data."]);
    expect(left.some((p) => p.op === "add") || right.some((p) => p.op === "del")).toBe(false);
  });

  it("keeps each side's text whole", () => {
    const a = "Limitation on Enrollment: Formal enrollment.\n\nAdvisory: NS 102A.", b = "Limitation on Enrollment: Formal enrollment.";
    const { left, right } = sides(a, b);
    expect(left.map((p) => p.text).join("")).toBe(a);
    expect(right.map((p) => p.text).join("")).toBe(b);
    expect(wordDiff(a, a).every((p) => p.op === "same")).toBe(true);
  });

  it("shortens long unchanged text when compact", () => {
    const same = "word ".repeat(80);
    const { left } = sides(`Prerequisite: X. ${same}`, same, true);
    expect(left.some((p) => p.op === "gap")).toBe(true);
    expect(left.map((p) => p.text).join("").length).toBeLessThan(200);
  });

  it("treats spacing as no difference, and dates in the browser's time zone", () => {
    expect(sameText("a  b\n", "a b")).toBe(true);
    expect(sameText("a b", "a c")).toBe(false);
    expect(fmtDay("2026-10-28T12:00:00Z")).toBe("28 Oct");
  });
});
