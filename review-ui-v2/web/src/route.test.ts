import { describe, expect, it } from "vitest";
import { buildHash, parseHash } from "./route";

describe("route", () => {
  it("treats an empty hash as the landing page", () => {
    expect(parseHash("")).toEqual({ cid: null, stem: null });
    expect(parseHash("#")).toEqual({ cid: null, stem: null });
  });

  it("reads the catalog and the page", () => {
    expect(parseHash("#ccsf-2026/course-3-10-abc")).toEqual({ cid: "ccsf-2026", stem: "course-3-10-abc" });
  });

  it("reads a catalog with no page yet", () => {
    expect(parseHash("#ccsf-2026")).toEqual({ cid: "ccsf-2026", stem: null });
  });

  it("round-trips", () => {
    expect(parseHash(buildHash("c", "s"))).toEqual({ cid: "c", stem: "s" });
    expect(buildHash("c")).toBe("#c");
    expect(buildHash(null, "s")).toBe("");
  });
});
