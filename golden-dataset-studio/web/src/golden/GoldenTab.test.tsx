import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { CatalogDetail, GoldenResponse, GoldenVersion } from "../api/types";
import { parseRoute } from "../shell/router";

const golden = vi.fn();
const stems = vi.fn();
const pageJson = vi.fn();
vi.mock("../api/client", () => ({ api: {
  golden: (...a: unknown[]) => golden(...a), goldenStems: (...a: unknown[]) => stems(...a),
  goldenPageJson: (...a: unknown[]) => pageJson(...a) } }));
import GoldenTab from "./GoldenTab";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
const CAT = "avc-elumenapp-com-catalog-2026-27-welcome", CRAWL = "2026-10-12T20-59-13Z";
const version = (n: number, o: Partial<GoldenVersion> = {}): GoldenVersion => ({
  id: `ruleset-v${n}`, ruleset_version: n, latest: false, columns: ["inLanguage"], values: 1062, human: 14,
  published_at: "2026-10-27T16:52:20Z", created_at: null, published_by: "Eric via the Studio UI", extraction: `rs-000${n}`, score: null,
  where: { root: "/data/golden", version: `catalogs/${CAT}/versions/ruleset-v${n}/`,
           trees: { "rule-matched": { prefix: "x", pages: 1062 }, "human-reviewed": { prefix: "y", pages: 14 } },
           latest: null, studio: `${CAT}/${CRAWL}/golden-dataset-studio/golden/ruleset-v${n}/` }, ...o });
const RESP: GoldenResponse = { catalog: CAT, crawl: CRAWL, latest_output: "2026-10-26T20-36-03Z", running: null, versions: [
  version(3, { latest: true, columns: ["codedNotation", "inLanguage"], values: 2124, human: 45,
               score: { id: "sc-0009", status: "done", basis: "human", rate: 0.553, values: 56, match: 31 },
               where: { ...version(3).where, latest: `${CAT}/${CRAWL}/` } }),
  version(2)] };

let host: HTMLDivElement, root: Root;
const flush = () => act(async () => { await new Promise((r) => setTimeout(r, 0)); });
const render = async () => {
  await act(async () => root.render(<GoldenTab catalog={{ short: "avc" } as CatalogDetail} route={parseRoute("#/c/avc/golden")} reload={() => {}} />));
  await flush();
};
beforeEach(() => {
  golden.mockReset().mockResolvedValue(RESP);
  stems.mockReset().mockResolvedValue(["page-a", "page-b"]);
  pageJson.mockReset().mockResolvedValue({ text: "[]", records: 0 });
  host = document.createElement("div"); document.body.appendChild(host); root = createRoot(host);
});
afterEach(() => { act(() => root.unmount()); host.remove(); });

describe("Golden datasets tab", () => {
  it("lists each version read-only: columns without ceterms:, values with how many are human-reviewed, the latest score", async () => {
    await render();
    expect(host.querySelector("h1")?.textContent).toBe("Golden datasets");
    const rows = [...host.querySelectorAll(".gv-table tbody tr")].map((r) => [...r.querySelectorAll("td")].map((td) => td.textContent));
    expect(rows).toEqual([
      ["ruleset v3 latest", "codedNotation, inLanguage", "2,124 · 45 human-reviewed", "55% exact, human-reviewed (31 of 56)"],
      ["ruleset v2", "inLanguage", "1,062 · 14 human-reviewed", "not scored yet"]]);
    expect(host.textContent).not.toContain("ceterms:");
    expect(host.querySelector("input[type=checkbox]")).toBeNull();
    expect([...host.querySelectorAll("button")].some((b) => /Publish/.test(b.textContent ?? ""))).toBe(false);
  });

  it("shows where the chosen version is written: both trees, the latest location and the Studio's files, each a sample", async () => {
    await render();
    const tree = host.querySelector(".gv-tree")!.textContent!;
    expect(tree).toContain(`catalogs/${CAT}/versions/ruleset-v3/`);
    expect(tree).toContain(`rule-matched/${CAT}/${CRAWL}/`);
    expect(tree).toContain("# only the human-reviewed values (14 pages)");
    expect(tree).toContain("<page>.html");
    expect([...host.querySelectorAll(".gv-tree button.f")].map((b) => b.textContent)).toEqual(
      ["<page>.json", "<page>.json", "<page>.json", "<page>.html", "publication.json", "lineage.parquet", "golden.parquet"]);
    await act(async () => host.querySelector<HTMLButtonElement>(".gv-tree button.f")!.click());
    await flush();
    expect(stems).toHaveBeenCalledWith("avc", "ruleset-v3", "rule-matched");
    expect(pageJson).toHaveBeenCalledWith("avc", "ruleset-v3", "page-a", "rule-matched");

    // an older version: only its own folder, not the latest location
    await act(async () => host.querySelector<HTMLElement>("[data-version=ruleset-v2]")!.click());
    expect(host.querySelector(".gv-where")?.textContent).toContain("Where ruleset v2 is written");
    expect(host.querySelector(".gv-tree")!.textContent).not.toContain("<page>.html");
  });

  it("says how a golden dataset comes to be when there is none", async () => {
    golden.mockResolvedValue({ ...RESP, versions: [] });
    await render();
    expect(host.textContent).toContain("Approving a column's rule on the Rules tab publishes it");
  });
});
