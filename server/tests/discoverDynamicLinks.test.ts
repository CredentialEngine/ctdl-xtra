import { describe, expect, it, vi, vitest } from "vitest";
import { discoverDynamicLinks } from "../src/extraction/dynamicLinkDiscovery";

vitest.mock("../src/extraction/browser", async (importOriginal) => {
  const actual = (await importOriginal()) as typeof import("../src/extraction/browser");
  return {
    ...actual,
    findProxies: vi.fn().mockResolvedValue([
      "http://proxy.example.com:8080",
      "http://proxy.example.com:8081",
    ]),
  };
});

describe("discoverDynamicLinks", { timeout: 30 * 60 * 1000 }, () => {
  // Test disabled as the purpose is to speed up testing dynamic link discovery
  // during development.
  it.skip("should discover dynamic links", { timeout: 30 * 60 * 1000 }, async () => {

    // Comment out to stop Google Chrome from showing the window
    // and to go into headless mode.
    // process.env.SHOW_CHROME = "1";

    const urls = await discoverDynamicLinks({
      rootUrl: "https://rccd.curriqunet.com/catalog/alias/mvc-catalog/iq/3246/3546",
      selector: 'article',
    });

    expect(urls.length).toBeGreaterThan(0);
  });
});
