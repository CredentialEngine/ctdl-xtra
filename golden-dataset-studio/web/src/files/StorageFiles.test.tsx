import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { shortPath, StorageFiles } from "./StorageFiles";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
const C = "avc-x", K = "2026";
const LIST = { root: "azure://https://a.blob.core.windows.net/c/p", catalog: C, crawl: K,
  portal: { browser: "https://portal.azure.com/#@/resource/x/storagebrowser", container: "c", prefix: "p" },
  files: [
    { path: `${C}/golden-dataset-studio/annotations.jsonl`, size: 2048, group: "Annotations", about: "The log", portal: "https://portal/log" },
    { path: `${C}/${K}/golden-dataset-studio/extractions/rs-0001/matches.parquet`, size: 9000, group: "Extractions", about: "Values" },
  ] };
const json = (b: unknown) => Promise.resolve(new Response(JSON.stringify(b), { status: 200 }));
let host: HTMLDivElement, root: Root;
const flush = () => act(async () => { await new Promise((r) => setTimeout(r, 0)); });
beforeEach(() => {
  vi.stubGlobal("fetch", vi.fn((url: string) => {
    if (url.endsWith("/files")) return json(LIST);
    const p = new URL(url, "http://x").searchParams.get("path")!;
    if (p.endsWith(".jsonl")) return json({ path: p, uri: "u", size: 2048, about: "The log", portal: "https://portal/log", kind: "jsonl",
      total: 2, matched: 2, offset: 0, rows: [{ line: 2, event: { type: "comment", author: "Eric" } }, { line: 1, event: { type: "verdict" } }] });
    return json({ path: p, uri: "u2", size: 9000, about: "Values", portal: null, kind: "table", total: 1, matched: 1, offset: 0,
      columns: ["rule_id", "value"], rows: [["course-code", "GEOG 222"]] });
  }));
  host = document.createElement("div"); document.body.appendChild(host); root = createRoot(host);
});
afterEach(() => { act(() => root.unmount()); host.remove(); vi.unstubAllGlobals(); });

describe("StorageFiles", () => {
  it("lists the files by group, opens the log first (newest first), links to the Azure portal, and shows a table", async () => {
    const close = vi.fn();
    await act(async () => root.render(<StorageFiles catalog="avc" onClose={close} />));
    await flush(); await flush();
    expect([...host.querySelectorAll(".sf-gh")].map((g) => g.textContent)).toEqual(["Annotations", "Extractions"]);
    expect(host.querySelector(".sf-item.on .sf-name")!.textContent).toBe("annotations.jsonl");
    expect([...host.querySelectorAll(".sf-line")].map((l) => l.textContent)).toEqual(["2", "1"]);
    expect(host.querySelector(".sf-root a")!.getAttribute("href")).toContain("storagebrowser");
    expect(host.querySelector(".sf-portal")!.getAttribute("href")).toBe("https://portal/log");
    await act(async () => host.querySelectorAll<HTMLButtonElement>(".sf-item")[1].click());
    await flush();
    expect(host.querySelector(".gfp-table td")!.textContent).toBe("course-code");
    expect(host.querySelector(".sf-portal")).toBeNull();
    await act(async () => window.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape" })));
    expect(close).toHaveBeenCalled();
  });
  it("shortens paths to the catalog or crawl folder", () => {
    expect(shortPath(`${C}/${K}/golden-dataset-studio/extractions/rs-0001/x.parquet`, C, K)).toBe("extractions/rs-0001/x.parquet");
    expect(shortPath(`${C}/golden-dataset-studio/rules/a/v0001.json`, C, K)).toBe("rules/a/v0001.json");
    expect(shortPath(`${C}/${K}/crawl.json`, C, K)).toBe("crawl.json");
  });
});
