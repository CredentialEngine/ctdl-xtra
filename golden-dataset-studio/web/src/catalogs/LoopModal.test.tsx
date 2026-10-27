import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../api/client", () => ({ api: { catalogs: () => Promise.resolve([]) } }));
import CatalogPicker from "./CatalogPicker";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
let host: HTMLDivElement, root: Root;
beforeEach(() => { host = document.createElement("div"); document.body.appendChild(host); root = createRoot(host); });
afterEach(() => { act(() => root.unmount()); host.remove(); });

describe("the loop modal on the catalog picker", () => {
  it("opens with the three steps and the repeat condition, closes, and opens again from the link", async () => {
    await act(async () => root.render(<CatalogPicker />));
    const dlg = host.querySelector("[role=dialog]")!;
    expect([...dlg.querySelectorAll(".loop-node b")].map((b) => b.textContent)).toEqual(
      ["Annotate records", "Generate better rules", "Apply new rules"]);
    expect(dlg.querySelectorAll(".loop-arc").length).toBe(3);
    expect(dlg.textContent).toContain("until every rule is 100% correct for that catalog");
    await act(async () => [...dlg.querySelectorAll("button")].find((b) => b.textContent === "Got it")!.click());
    expect(host.querySelector("[role=dialog]")).toBeNull();
    await act(async () => host.querySelector<HTMLButtonElement>(".loop-again")!.click());
    expect(host.querySelector("[role=dialog]")).not.toBeNull();
    await act(async () => window.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape" })));
    expect(host.querySelector("[role=dialog]")).toBeNull();
  });
});

import { edgeGap } from "./LoopModal";

describe("edgeGap", () => {
  it("finds where the ring leaves a box: wider boxes need a wider gap", () => {
    const narrow = edgeGap(-90, 40, 30, 1), wide = edgeGap(-90, 80, 30, 1);
    expect(narrow).toBeGreaterThan(10);
    expect(wide).toBeGreaterThan(narrow);
    expect(edgeGap(-90, 80, 30, -1)).toBe(wide); // the top box is symmetric
  });
});

import { fired } from "./LoopModal";

describe("fired", () => {
  it("launches fast and is still moving when it arrives (no stall at the end of the arrow)", () => {
    expect(fired(0)).toBe(0);
    expect(fired(1)).toBeCloseTo(1, 10);
    expect(fired(0.1)).toBeGreaterThan(0.15);            // fast off the box
    expect(1 - fired(0.9)).toBeGreaterThan(0.03);         // the last tenth still covers ground
  });
});
