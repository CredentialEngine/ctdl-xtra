import { describe, expect, it } from "vitest";
import { shortPattern } from "./KeyCode";

describe("a page rule's URL pattern on the identifier card", () => {
  it("reads as a short path: each alternative's literal start, … where the pattern takes over", () => {
    expect(shortPattern("(/graduate/collegeofbusinessandeconomics/[a-z]+/|/undergraduate/minors/[a-z]+/)$"))
      .toBe("/graduate/collegeofbusinessandeconomics/…, and 1 more");
    expect(shortPattern("/(undergraduate|graduate)/")).toBe("/(undergraduate|graduate)/");
    expect(shortPattern("^/catalog/2026-27/program/.*$")).toBe("/catalog/2026-27/program/…");
    expect(shortPattern("/a/x|/b/y|/c/z|/d/w")).toBe("/a/x or /b/y, and 2 more");
    expect(shortPattern("/graduate/[a-z]+/|/minors/[a-z]+/")).toBe("/graduate/… or /minors/…");
    expect(shortPattern("courseleaf\\.wvu\\.edu/x")).toBe("courseleaf.wvu.edu/x");
  });
});
