import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { CatalogDetail } from "../api/types";
import { parseRoute } from "../shell/router";

const golden = vi.fn();
const publish = vi.fn();
vi.mock("../api/client", () => ({ api: { golden: (...a: unknown[]) => golden(...a), goldenPublish: (...a: unknown[]) => publish(...a) } }));
import GoldenTab from "./GoldenTab";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
const prop = (property: string, status: string, published: unknown = null) => ({ property, ctdl_property: `ceterms:${property}`,
  rule_id: `course-${property.toLowerCase()}`, version: 2, status, approved_by: status === "approved" ? "Jared" : null, published });
const RESP = (chosen: string[]) => ({ ready: true, all_rules_approved: false, chosen, extraction: "rs-0003", ruleset_version: 3,
  properties: [prop("Description", "approved"), prop("Language", "approved", { publication: "pub-1", published_at: "2026-10-27T10:00:00Z",
    published_by: "Eric", extraction: "rs-0003", rule_version: 1 }), prop("Name", "needs work")],
  rules: [{ rule_id: "course-page", title: "Course pages", subtitle: "", kind: "page", version: 1, status: "in review", approved_by: null }],
  target: "azure://x/xtra-golden-sets/avc/2026/", pages: 10, courses: 9, records: 9, fields: 9 * chosen.length,
  skipped_no_course_key: 0, collisions: [], page_stems: [], publications: [] });

let host: HTMLDivElement, root: Root;
const flush = () => act(async () => { await new Promise((r) => setTimeout(r, 0)); });
beforeEach(() => {
  golden.mockReset().mockImplementation(async (_c: string, props?: string[]) => RESP(props ?? ["Description", "Language"]));
  publish.mockReset().mockResolvedValue({ publication: "pub-2", path: "x", files: 10, properties: ["Description"] });
  host = document.createElement("div"); document.body.appendChild(host); root = createRoot(host);
});
afterEach(() => { act(() => root.unmount()); host.remove(); });

describe("Publish tab", () => {
  it("publishes one property: only approved properties can be chosen, the others say why", async () => {
    await act(async () => root.render(<GoldenTab catalog={{ short: "avc" } as CatalogDetail} route={parseRoute("#/c/avc/publish")} reload={() => {}} />));
    await flush();
    const box = (p: string) => host.querySelector<HTMLInputElement>(`[data-property="${p}"] input`)!;
    expect(box("Name").disabled).toBe(true);
    expect(host.querySelector("[data-property=Language]")!.textContent).toContain("published 2026-10-27 · v1");
    expect(host.querySelector("[data-property=Description]")!.textContent).toContain("not published yet");
    await act(async () => box("Language").click());
    await flush();
    expect(golden).toHaveBeenLastCalledWith("avc", ["Description"]);
    const btn = [...host.querySelectorAll<HTMLButtonElement>(".gate .btn")][0];
    expect(btn.textContent).toBe("Publish Description");
    await act(async () => btn.click());
    expect(publish).toHaveBeenCalledWith("avc", expect.objectContaining({ properties: ["Description"] }));
  });
});
