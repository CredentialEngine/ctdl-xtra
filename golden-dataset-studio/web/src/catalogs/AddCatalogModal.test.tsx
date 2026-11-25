import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { CrawledCatalog } from "../api/types";

const run = (crawl: string, pages: number, status: CrawledCatalog["status"] = "complete") =>
  ({ crawl, seed_url: "https://cuesta.curriqunet.com/catalog/iq/27137", finished_at: `${crawl.slice(0, 10)}T12:00:00Z`, pages, status });
const ITEMS: CrawledCatalog[] = [
  { ...run("2026-10-21T10-00-00Z", 2104), catalog: "cuesta-curriqunet-com-catalog-iq-27137", name: "Cuesta",
    crawls: [run("2026-10-21T10-00-00Z", 2104), run("2026-10-03T10-00-00Z", 1998, "limit_reached")], added: false, adding: false },
  { ...run("2026-10-01T16-02-34Z", 521, "incomplete"), seed_url: "https://ccsf.curricunet.com/catalog/",
    catalog: "ccsf-curricunet-com-catalog", name: "CCSF", crawls: [], added: true, adding: false },
];
const addCatalog = vi.fn(() => Promise.resolve({}));
vi.mock("../api/client", () => ({ api: { crawls: () => Promise.resolve({ crawls_root: "x", items: ITEMS }),
  addCatalog: (...a: unknown[]) => (addCatalog as (...a: unknown[]) => Promise<unknown>)(...a) } }));
import { AddCatalogModal, matches } from "./AddCatalogModal";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
let host: HTMLDivElement, root: Root;
beforeEach(() => { host = document.createElement("div"); document.body.appendChild(host); root = createRoot(host); });
afterEach(() => { act(() => root.unmount()); host.remove(); });

const type = async (el: HTMLInputElement, v: string) => {
  const set = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")!.set!;
  await act(async () => { set.call(el, v); el.dispatchEvent(new Event("input", { bubbles: true })); });
};

describe("Add a catalog", () => {
  it("matches on name, folder and URL words", () => {
    expect(matches(ITEMS[0], "cuesta 27137")).toBe(true);
    expect(matches(ITEMS[0], "ualr")).toBe(false);
  });

  it("explains where catalogs come from, searches, and adds the chosen crawl", async () => {
    const onAdded = vi.fn(), onClose = vi.fn();
    await act(async () => root.render(<AddCatalogModal onClose={onClose} onAdded={onAdded} />));
    const dlg = host.querySelector("[role=dialog]")!;
    await act(async () => dlg.querySelector<HTMLButtonElement>(".ac-info")!.click());
    expect(dlg.querySelector("[role=tooltip]")!.textContent).toContain("ask engineering to crawl it");
    expect([...dlg.querySelectorAll(".ac-t th")].map((t) => t.textContent)).toEqual(["Catalog", "Last crawled", "Pages", "Crawl"]);
    const rows = [...dlg.querySelectorAll(".ac-t tbody tr")];
    expect(rows.length).toBe(2);
    expect(rows[1].textContent).toContain("Already added");
    expect(rows[0].className).toContain("sel");

    await type(dlg.querySelector<HTMLInputElement>(".ac-search")!, "ccsf");
    expect(dlg.querySelectorAll(".ac-t tbody tr").length).toBe(1);
    await type(dlg.querySelector<HTMLInputElement>(".ac-search")!, "cue");
    await act(async () => dlg.querySelector<HTMLInputElement>(".ac-search")!
      .dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true })));
    expect(dlg.querySelector("#ac-h")!.textContent).toBe("Add Cuesta");
    expect([...dlg.querySelectorAll(".ac-found th")].map((t) => t.textContent)).toEqual(["Name", "Catalog URL", "Crawl", "Pages", "Status"]);
    expect(dlg.querySelector(".ac-warn")).toBeNull();
    const sel = dlg.querySelector<HTMLSelectElement>("select")!;
    await act(async () => { sel.value = "2026-10-03T10-00-00Z"; sel.dispatchEvent(new Event("change", { bubbles: true })); });
    expect(dlg.querySelector(".ac-warn")!.textContent).toContain("isn't complete");
    await act(async () => [...dlg.querySelectorAll("button")].find((b) => b.textContent === "Add catalog")!.click());
    expect(addCatalog).toHaveBeenCalledWith("cuesta-curriqunet-com-catalog-iq-27137", expect.objectContaining({ crawl: "2026-10-03T10-00-00Z" }));
    expect(onAdded).toHaveBeenCalled();
    expect(onClose).toHaveBeenCalled();
  });
});
