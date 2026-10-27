import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { CatalogDetail, PromptResponse, RulesResponse } from "../api/types";
import { parseRoute } from "../shell/router";

const prompt = vi.fn();
const rules = vi.fn();
vi.mock("../api/client", () => ({ api: { prompt: (...a: unknown[]) => prompt(...a), rules: (...a: unknown[]) => rules(...a) } }));

import PromptTab from "./PromptTab";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const catalog = { catalog: "avc-elumenapp-com-catalog-2026-27-welcome", short: "avc", name: "AVC", ruleset_version: 1,
                  extraction: "rs-0001" } as unknown as CatalogDetail;
const rule = (rule_id: string, status: string) => ({ rule_id, status, version: 1, kind: "field" });
const RULES = { extraction: "rs-0001", ruleset_version: 1, groups: [
  { kind: "page", label: "Page rules", approved: 0, rules: [rule("program-page-with-courses", "needs work")] },
  { kind: "field", label: "Field rules", approved: 0, rules: [rule("course-code", "in review"), rule("course-description", "needs work")] },
] } as unknown as RulesResponse;
const TEXT = "# Improve rule `course-description` — AVC catalog\n\n## Context\n- run `golden-datasets rule show course-description`\n";
const RESP: PromptResponse = { scope: { rule: "course-description", needs_work: false }, text: TEXT, chars: TEXT.length,
                               tokens: Math.round(TEXT.length / 4), page_refs: 5, rules: ["course-description"], annotations: 5 };

let host: HTMLDivElement;
let root: Root;
const flush = () => act(async () => { await new Promise((r) => setTimeout(r, 0)); });

beforeEach(() => {
  prompt.mockReset().mockResolvedValue(RESP);
  rules.mockReset().mockResolvedValue(RULES);
  host = document.createElement("div");
  document.body.appendChild(host);
  root = createRoot(host);
});
afterEach(() => { act(() => root.unmount()); host.remove(); });

async function render(hash: string) {
  act(() => root.render(<PromptTab catalog={catalog} route={parseRoute(hash)} reload={() => {}} />));
  await flush();
}

describe("PromptTab", () => {
  it("asks for the rule in the route and shows the text, size and page references", async () => {
    await render("#/c/avc/prompt?rule=course-description&from=rules");
    expect(prompt).toHaveBeenCalledWith(catalog.catalog, { rule: "course-description" });
    const pre = host.querySelector("[data-testid=prompt-text]")!;
    expect(pre.textContent).toBe(TEXT);
    expect(pre.querySelector(".h1")?.textContent).toContain("Improve rule");
    expect(pre.querySelector(".cmd")?.textContent).toBe("`golden-datasets rule show course-description`");
    expect(host.textContent).toContain("Opened from the Rules tab with course-description selected.");
    const facts = host.querySelector(".facts")!.textContent!;
    expect(facts).toContain(`Characters${TEXT.length}`);
    expect(facts).toContain("Page references5");
    expect((host.querySelector("select") as HTMLSelectElement).value).toBe("course-description");
  });

  it("defaults to all rules needing work and lists them", async () => {
    await render("#/c/avc/prompt");
    expect(prompt).toHaveBeenCalledWith(catalog.catalog, { needs_work: true });
    const card = host.querySelector("[data-testid=scope-needs-work]")!;
    expect(card.className).toContain("on");
    expect(card.textContent).toContain("program-page-with-courses, course-description");
  });

  it("copies the exact text", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.assign(navigator, { clipboard: { writeText } });
    await render("#/c/avc/prompt?rule=course-description");
    const copy = [...host.querySelectorAll("button")].find((b) => b.textContent?.includes("Copy prompt"))!;
    await act(async () => { copy.click(); });
    expect(writeText).toHaveBeenCalledWith(TEXT);
  });

  it("switching the rule changes the route", async () => {
    await render("#/c/avc/prompt?rule=course-description");
    const sel = host.querySelector("select") as HTMLSelectElement;
    act(() => { sel.value = "course-code"; sel.dispatchEvent(new Event("change", { bubbles: true })); });
    expect(location.hash).toBe("#/c/avc/prompt?rule=course-code");
  });
});
