import { describe, expect, it } from "vitest";
import { downloadName, highlight, highlightLine } from "./highlight";

describe("prompt highlighting", () => {
  it("marks headings", () => {
    expect(highlightLine("# Improve rule `x` — AVC catalog")).toEqual([{ cls: "h1", text: "# Improve rule `x` — AVC catalog" }]);
    expect(highlightLine("## Context")[0].cls).toBe("h2");
    expect(highlightLine("### Open annotations (5)")[0].cls).toBe("h3");
  });
  it("splits code and commands, keeping every character", () => {
    const line = "1. `golden-datasets rule show x` — current `definition`, done";
    const segs = highlightLine(line);
    expect(segs.map((s) => s.text).join("")).toBe(line);
    expect(segs.filter((s) => s.cls).map((s) => [s.cls, s.text])).toEqual([
      ["cmd", "`golden-datasets rule show x`"], ["code", "`definition`"]]);
  });
  it("keeps empty lines and text that looks like HTML as plain text", () => {
    const lines = highlight("a\n\n<div>b</div>\n");
    expect(lines.length).toBe(3);
    expect(lines[1]).toEqual([{ cls: null, text: "" }]);
    expect(lines[2]).toEqual([{ cls: null, text: "<div>b</div>" }]);
  });
  it("names the download", () => {
    expect(downloadName("avc", "course-description")).toBe("golden-datasets-prompt-avc-course-description.md");
  });
});
