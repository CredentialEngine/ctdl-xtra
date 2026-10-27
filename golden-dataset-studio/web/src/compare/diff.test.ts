import { describe, expect, it } from "vitest";
import { compactDiff, delta, outcomeLabel, unchanged } from "./diff";

const long = (w: string, n: number) => Array.from({ length: n }, () => w).join(" ");

describe("compactDiff", () => {
  it("keeps short diffs as they are", () => {
    const parts = [{ op: "del" as const, text: "Prerequisite: X. " }, { op: "same" as const, text: "Short text." }];
    expect(compactDiff(parts)).toEqual(parts);
  });
  it("cuts the long unchanged tail after a change, keeping every change", () => {
    const tail = long("word", 60);
    const out = compactDiff([{ op: "del", text: "Prerequisite: X. " }, { op: "same", text: tail }]);
    expect(out[0]).toEqual({ op: "del", text: "Prerequisite: X. " });
    expect(out[1].op).toBe("same");
    expect(out[1].text.length).toBeLessThanOrEqual(50);
    expect(tail.startsWith(out[1].text)).toBe(true);
    expect(out[2]).toEqual({ op: "gap", text: " …" });
  });
  it("keeps context on both sides of a long stretch between two changes", () => {
    const mid = long("mid", 80);
    const out = compactDiff([{ op: "add", text: "A" }, { op: "same", text: mid }, { op: "del", text: "B" }]);
    expect(out.map((p) => p.op)).toEqual(["add", "same", "gap", "same", "del"]);
    expect(mid.endsWith(out[3].text)).toBe(true);
  });
  it("cuts a long unchanged head before the first change", () => {
    const out = compactDiff([{ op: "same", text: long("head", 60) }, { op: "add", text: "X" }]);
    expect(out.map((p) => p.op)).toEqual(["gap", "same", "add"]);
  });
});

describe("labels", () => {
  it("names outcomes as screen 08 does", () => {
    expect(outcomeLabel({ verdict: "correct", outcome: "unchanged" })).toEqual({ label: "still correct", cls: "still-correct" });
    expect(outcomeLabel({ verdict: "wrong", outcome: "fixed" })).toEqual({ label: "fixed", cls: "fixed" });
    expect(outcomeLabel({ verdict: "correct", outcome: "newly wrong" }).cls).toBe("newly-wrong");
  });
  it("formats deltas and detects unchanged diffs", () => {
    expect(delta(547, 273)).toBe("-274");
    expect(delta(35, 37)).toBe("+2");
    expect(delta(5, 5)).toBe("–");
    expect(unchanged([{ op: "same", text: "x" }])).toBe(true);
    expect(unchanged([{ op: "same", text: "x" }, { op: "add", text: "y" }])).toBe(false);
  });
});
