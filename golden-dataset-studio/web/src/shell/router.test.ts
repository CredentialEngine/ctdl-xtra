import { describe, expect, it } from "vitest";
import { href, parseRoute } from "./router";

describe("routes", () => {
  it("parses the picker and tabs", () => {
    expect(parseRoute("").catalog).toBeNull();
    const r = parseRoute("#/c/avc/rules/course-description?row=a%40b");
    expect([r.catalog, r.tab, r.id, r.params.get("row")]).toEqual(["avc", "rules", "course-description", "a@b"]);
    expect(parseRoute("#/c/avc").tab).toBe("rules");
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
