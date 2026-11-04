import { describe, expect, it } from "vitest";
import { href, parseRoute, replaceParam } from "./router";

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
  it("opens the Datasets tab from its own link, and from the old Golden datasets and Publish links", () => {
    expect(parseRoute("#/c/avc/datasets").tab).toBe("datasets");
    expect(parseRoute("#/c/avc/golden").tab).toBe("datasets");
    expect(parseRoute("#/c/avc/publish").tab).toBe("datasets");
  });
  it("replaceParam sets one parameter with history.replaceState, keeping the others, without a hashchange", () => {
    history.replaceState(null, "", "#/c/avc/rules/course-description?by=Jared&row=old");
    let changes = 0;
    const on = () => { changes++; };
    window.addEventListener("hashchange", on);
    const before = history.length;
    replaceParam("row", "p1@html");
    expect(location.hash).toBe("#/c/avc/rules/course-description?by=Jared&row=p1%40html");
    replaceParam("row", null);
    expect(location.hash).toBe("#/c/avc/rules/course-description?by=Jared");
    expect(history.length).toBe(before);
    expect(changes).toBe(0);
    window.removeEventListener("hashchange", on);
  });
});
