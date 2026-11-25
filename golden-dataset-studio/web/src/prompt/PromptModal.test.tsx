import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const prompt = vi.fn((_catalog: string, _opts: { needs_work?: boolean; rule?: string }) => Promise.resolve({
  scope: { rule: null, needs_work: true }, text: "# Improve 2 rules that need work — AVC catalog\n\n## Setup\n",
  chars: 60, tokens: 15, page_refs: 3, rules: ["course-description", "course-code"], annotations: 7, target: "azure",
  root: "azure://x", studio_root: "azure://x", warning: null }));
vi.mock("../api/client", () => ({ api: { prompt: (c: string, o: { needs_work?: boolean }) => prompt(c, o) } }));
import { PromptModal } from "./PromptModal";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
let host: HTMLDivElement, root: Root;
beforeEach(() => { prompt.mockClear(); host = document.createElement("div"); document.body.appendChild(host); root = createRoot(host); });
afterEach(() => { act(() => root.unmount()); host.remove(); });
const flush = () => act(async () => { for (let i = 0; i < 5; i++) await Promise.resolve(); });

describe("PromptModal", () => {
  it("shows the prompt for every rule that needs work, never one rule", async () => {
    await act(async () => root.render(<PromptModal catalog="avc-x" short="avc" version={6} warning={null} onClose={() => {}} />));
    await flush();
    expect(prompt).toHaveBeenCalledWith("avc-x", { needs_work: true });
    expect(host.querySelector("#pm-h")!.textContent).toBe("The prompt for Claude Code");
    expect(host.querySelector(".pm-lead")!.textContent).toContain("Every rule that needs work (2)");
    expect(host.querySelector("[data-testid=prompt-text]")!.textContent).toContain("Improve 2 rules that need work");
    expect(host.querySelector("[data-testid=k2-warning]")).toBeNull();
    expect([...host.querySelectorAll("button")].some((b) => b.textContent?.includes("Copy prompt"))).toBe(true);
  });

  it("says the Remote AI rule generator couldn't be reached when it opens as the fallback", async () => {
    await act(async () => root.render(<PromptModal catalog="avc-x" short="avc" version={6} warning="K2 didn't answer in 15 s" onClose={() => {}} />));
    await flush();
    expect(host.querySelector("[data-testid=k2-warning]")!.textContent).toBe(
      "⚠ We couldn't connect to the Remote AI rule generator (K2 didn't answer in 15 s).Copy this prompt and ask an engineer to run it in their own Claude Code.");
  });
});
