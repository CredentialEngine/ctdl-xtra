import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { CatalogCard } from "../api/types";

const CARD: CatalogCard = { catalog: "catalog-citruscollege-edu", short: "catalog-citruscollege-edu", name: "Citruscollege",
  institution: "Citruscollege", platform: "", logo: null, pages: 1875, crawl: "2026-10-06T15-01-09Z", ruleset_version: null,
  rules_total: 0, rules_approved: 0, status: "not imported" };
vi.mock("../api/client", () => ({ api: {
  catalogs: () => Promise.resolve([CARD]),
  firstRulesPrompt: () => Promise.resolve({ text: "# Write the first rules — Citruscollege catalog\n\nStart from marshall.\n",
    chars: 60, tokens: 15, template: "marshall", template_name: "Marshall", root: "azure://x", studio_root: "azure://x", warning: null }),
} }));
import CatalogPicker from "./CatalogPicker";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
let host: HTMLDivElement, root: Root;
beforeEach(() => {
  try { localStorage.setItem("studio.loop.hidden", "1"); } catch { /* no storage */ }
  host = document.createElement("div"); document.body.appendChild(host); root = createRoot(host);
});
afterEach(() => { act(() => root.unmount()); host.remove(); });

describe("Generate rules", () => {
  it("a catalog without rules offers Generate rules, which shows the first-rules prompt to copy", async () => {
    await act(async () => root.render(<CatalogPicker />));
    const gotIt = [...host.querySelectorAll("button")].find((b) => b.textContent === "Got it");
    if (gotIt) await act(async () => gotIt.click());  // the loop modal, when the browser can't remember it was seen
    const btn = [...host.querySelectorAll("button")].find((b) => b.textContent === "Generate rules");
    expect(btn).toBeTruthy();
    await act(async () => btn!.click());
    const dlg = host.querySelector("[role=dialog]")!;
    expect(dlg.querySelector("#gr-h")!.textContent).toBe("Generate rules for Citruscollege");
    expect(dlg.textContent).toContain("starting from Marshall's");
    expect(dlg.querySelector("[data-testid=first-rules-prompt]")!.textContent).toContain("Write the first rules");
    expect([...dlg.querySelectorAll("button")].some((b) => b.textContent?.includes("Copy prompt"))).toBe(true);
  });
});
