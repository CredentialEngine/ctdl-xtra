import { describe, expect, it } from "vitest";
import { termUrl } from "./ui";

describe("termUrl", () => {
  it("links a term to its CTDL definition", () => {
    expect(termUrl("ceterms:description")).toBe("https://credreg.net/ctdl/terms/description");
    expect(termUrl(null)).toBeNull();
  });
  it("links a child path to its leaf term, the part after the last >", () => {
    expect(termUrl("ceterms:creditValue>schema:minValue")).toBe("https://credreg.net/ctdl/terms/minValue");
    expect(termUrl("ceterms:prerequisite>ceterms:targetLearningOpportunity"))
      .toBe("https://credreg.net/ctdl/terms/targetLearningOpportunity");
  });
});
