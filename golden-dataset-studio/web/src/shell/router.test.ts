import { describe, expect, it } from "vitest";
import { href, parseRoute } from "./router";

describe("routes", () => {
  it("parses the picker and tabs", () => {
    expect(parseRoute("").catalog).toBeNull();
    const r = parseRoute("#/c/avc/rules/course-description?row=a%40b");
    expect([r.catalog, r.tab, r.id, r.params.get("row")]).toEqual(["avc", "rules", "course-description", "a@b"]);
    expect(parseRoute("#/c/avc").tab).toBe("rules");
  });
  it("opens an old Prompt tab link as the prompt modal over the Rules tab", () => {
    const r = parseRoute("#/c/avc/prompt?rule=course-description&k2err=K2%20down");
    expect([r.catalog, r.tab, r.id, r.params.get("prompt"), r.params.get("rule"), r.params.get("k2err")])
      .toEqual(["avc", "rules", null, "1", null, "K2 down"]);
  });
  it("builds hrefs that parse back", () => {
    const h = href("avc", "compare", null, { a: 1, b: 2, rule: "course-description" });
    const r = parseRoute(h);
    expect([r.tab, r.params.get("a"), r.params.get("rule")]).toEqual(["compare", "1", "course-description"]);
  });
});

describe("renamed tabs", () => {
  it("opens the Publish tab from an old Golden link", () => {
    expect(parseRoute("#/c/avc/golden").tab).toBe("publish");
    expect(parseRoute("#/c/avc/publish").tab).toBe("publish");
  });
});
