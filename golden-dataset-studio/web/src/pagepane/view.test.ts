import { describe, expect, it } from "vitest";
import { layoutFor, nextZoom, setPageCss, ZOOM_STEPS } from "./view";

describe("zoom", () => {
  it("steps up and down and stops at the ends", () => {
    expect(nextZoom(1, 1)).toBe(1.1);
    expect(nextZoom(1, -1)).toBe(0.9);
    expect(nextZoom(ZOOM_STEPS[ZOOM_STEPS.length - 1], 1)).toBe(3);
    expect(nextZoom(0.5, -1)).toBe(0.5);
  });
  it("reflows like browser zoom: narrower layout, larger scale, same on-screen width", () => {
    const fit = layoutFor(700, 1400, 1);
    expect(fit).toEqual({ width: 1400, scale: 0.5 });
    const z = layoutFor(700, 1400, 2);
    expect(z.scale).toBe(1);
    expect(z.width).toBe(700);
    expect(z.width * z.scale).toBe(fit.width * fit.scale);
  });
});

describe("page CSS off", () => {
  it("removes the page's inline styles without changing the DOM structure, keeps the Studio's, and restores them", () => {
    document.body.innerHTML = `<div style="color:red"><p style="display:none">x</p></div>`;
    const ov = document.createElement("div");
    ov.id = "gds-overlay";
    ov.innerHTML = `<i style="left:3px"></i>`;
    document.documentElement.appendChild(ov);
    const before = document.body.innerHTML.replace(/ style="[^"]*"/g, "");
    setPageCss(document, false);
    expect(document.querySelector("p")!.getAttribute("style")).toBeNull();
    expect(document.querySelector("#gds-overlay i")!.getAttribute("style")).toBe("left:3px");
    expect(document.body.innerHTML.replace(/ data-gds-style="[^"]*"/g, "")).toBe(before);
    setPageCss(document, true);
    expect(document.querySelector("p")!.getAttribute("style")).toBe("display:none");
    expect(document.querySelector("[data-gds-style]")).toBeNull();
    ov.remove();
  });
});
