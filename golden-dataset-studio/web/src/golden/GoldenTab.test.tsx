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
// a version's trees: the latest versions are stored as silver/ and golden/, older ones under their first names
const version = (n: number, o: Partial<GoldenVersion> = {}): GoldenVersion => {
  const base = `catalogs/${CAT}/versions/ruleset-v${n}/`;
  return {
    id: `ruleset-v${n}`, ruleset_version: n, latest: false, columns: ["inLanguage"], values: 1062, human: 14,
    published_at: "2026-10-27T16:52:20Z", created_at: null, published_by: "Eric via the Studio UI", extraction: `rs-000${n}`, score: null,
    where: { root: "/data/golden", version: base,
             trees: { "rule-matched": { prefix: `${base}silver/${CAT}/${CRAWL}/`, pages: 1062 },
                      "human-reviewed": { prefix: `${base}golden/${CAT}/${CRAWL}/`, pages: 14 } },
             latest: null, studio: `${CAT}/${CRAWL}/golden-dataset-studio/golden/ruleset-v${n}/` }, ...o };
};
const RESP: GoldenResponse = { catalog: CAT, crawl: CRAWL, latest_output: "2026-10-26T20-36-03Z", running: null,
  golden: { human: 45, by_property: [
    { property: "Coded Notation", rule_id: "codedNotation", path_shown: "ceterms:codedNotation", human: 31 },
    { property: "Credit Unit Min Value", rule_id: "creditUnitMinValue", path_shown: "ceterms:creditValue → schema:minValue", human: 6 },
    { property: "Description", rule_id: "course-description", path_shown: "ceterms:description", human: 8 }] },
  versions: [
    version(3, { latest: true, columns: ["codedNotation", "inLanguage"], values: 2124, human: 45,
                 score: { id: "sc-0009", status: "done", basis: "human", rate: 0.553, values: 56, match: 31 },
                 where: { ...version(3).where, latest: `${CAT}/${CRAWL}/` } }),
    version(2, { where: { ...version(2).where, trees: {
      "rule-matched": { prefix: `catalogs/${CAT}/versions/ruleset-v2/rule-matched/${CAT}/${CRAWL}/`, pages: 1062 },
      "human-reviewed": { prefix: `catalogs/${CAT}/versions/ruleset-v2/human-reviewed/${CAT}/${CRAWL}/`, pages: 14 } } } })] };

let host: HTMLDivElement, root: Root;
const flush = () => act(async () => { await new Promise((r) => setTimeout(r, 0)); });
const render = async () => {
  await act(async () => root.render(<GoldenTab catalog={{ short: "avc" } as CatalogDetail} route={parseRoute("#/c/avc/datasets")} reload={() => {}} />));
  await flush();
};
beforeEach(() => {
  golden.mockReset().mockResolvedValue(RESP);
  stems.mockReset().mockResolvedValue(["page-a", "page-b"]);
  pageJson.mockReset().mockResolvedValue({ text: "[]", records: 0 });
  host = document.createElement("div"); document.body.appendChild(host); root = createRoot(host);
});
afterEach(() => { act(() => root.unmount()); host.remove(); });

describe("Datasets tab", () => {
  it("is the Datasets tab: a Golden section (human-reviewed values by property) and a Silver section", async () => {
    await render();
    expect(host.querySelector("h1")?.textContent).toBe("Datasets");
    expect([...host.querySelectorAll("h2")].map((h) => h.textContent)).toEqual(["Golden dataset", "Silver datasets"]);
    expect(host.textContent).toContain("Approving a rule publishes its silver dataset. The golden dataset changes only when an expert gives a verdict.");
  });

  it("the golden dataset: only the values an expert reviewed, by property, with the path shown with arrows", async () => {
    await render();
    const rows = [...host.querySelectorAll("[data-testid=golden] tbody tr")].map((r) => [...r.querySelectorAll("td")].map((td) => td.textContent));
    expect(rows).toEqual([
      ["Coded Notation", "ceterms:codedNotation", "31"],
      ["Credit Unit Min Value", "ceterms:creditValue → schema:minValue", "6"],
      ["Description", "ceterms:description", "8"]]);
    expect(host.querySelector("[data-testid=golden] tfoot")!.textContent).toContain("45");
    expect(host.querySelector("[data-testid=golden] td.mono")!.textContent).toBe("ceterms:codedNotation");
  });

  it("the silver datasets: one row per ruleset version, named Silver dataset ruleset-vN, with its columns and values", async () => {
    await render();
    const rows = [...host.querySelectorAll(".gv-table tbody tr")].map((r) => [...r.querySelectorAll("td")].map((td) => td.textContent));
    expect(rows).toEqual([
      ["Silver dataset ruleset-v3 latest", "codedNotation, inLanguage", "45", "2,124"],
      ["Silver dataset ruleset-v2", "inLanguage", "14", "1,062"]]);
    expect([...host.querySelectorAll(".gv-table th")].map((th) => th.textContent)).toEqual(
      ["Silver dataset", "Columns", "Human-reviewed values", "Rule-matched values"]);
    expect(host.querySelector(".gv-table")!.textContent).not.toContain("ceterms:");  // the silver table lists columns without their prefix
    expect(host.textContent).toContain("xtra's scorer reads by default");
    expect(host.querySelector(".gv-tree")).toBeNull();  // the file tree waits behind "Where these files are"
    expect(host.querySelector("input[type=checkbox]")).toBeNull();
    expect([...host.querySelectorAll("button")].some((b) => /Publish/.test(b.textContent ?? ""))).toBe(false);
  });

  it("shows where the chosen version is written: both trees, the latest location and the Studio's files, each a sample", async () => {
    await render();
    const help = () => [...host.querySelectorAll<HTMLButtonElement>("button")].find((b) => b.textContent?.includes("Where these files are"))!;
    await act(async () => help().click());
    const tree = host.querySelector(".gv-tree")!.textContent!;
    expect(tree).toContain(`catalogs/${CAT}/versions/ruleset-v3/`);
    expect(tree).toContain(`silver/${CAT}/${CRAWL}/`);
    expect(tree).toContain(`golden/${CAT}/${CRAWL}/`);
    expect(tree).toContain("# only the human-reviewed values (14 pages)");
    expect(tree).toContain("<page>.html");
    expect([...host.querySelectorAll(".gv-tree button.f")].map((b) => b.textContent)).toEqual(
      ["<page>.json", "<page>.json", "<page>.json", "<page>.html", "publication.json", "lineage.parquet", "golden.parquet"]);
    await act(async () => host.querySelector<HTMLButtonElement>(".gv-tree button.f")!.click());
    await flush();
    expect(stems).toHaveBeenCalledWith("avc", "ruleset-v3", "rule-matched");
    expect(pageJson).toHaveBeenCalledWith("avc", "ruleset-v3", "page-a", "rule-matched");

    // an older version: only its own folder, not the latest location; its folders keep their first names
    await act(async () => host.querySelector<HTMLElement>(".gv-back")!.click());
    expect(host.querySelector(".gv-tree")).toBeNull();
    await act(async () => host.querySelector<HTMLElement>("[data-version=ruleset-v2]")!.click());
    await act(async () => help().click());
    expect(host.querySelector(".gv-modal h2")?.textContent).toBe("Where Silver dataset ruleset-v2 is written");
    expect(host.querySelector(".gv-tree")!.textContent).not.toContain("<page>.html");
    expect(host.querySelector(".gv-tree")!.textContent).toContain(`rule-matched/${CAT}/${CRAWL}/`);
  });

  it("says how a silver dataset comes to be when there is none", async () => {
    golden.mockResolvedValue({ ...RESP, versions: [] });
    await render();
    expect(host.textContent).toContain("Approving a rule on the Rules tab publishes its silver dataset");
  });
});
