import { describe, expect, it } from "vitest";
import {
  type CrawlPageUrlInput,
  resolveCrawlPageUrl,
} from "../src/extraction/crawlPageUrl";

describe("resolveCrawlPageUrl", () => {
  it("resolves relative crawl page URLs against the recipe when there is no parent page", async () => {
    const page: CrawlPageUrlInput = {
      url: "preview_program.php?catoid=13&poid=2266&returnto=664",
      crawlStep: { parentStepId: null },
      extraction: {
        recipe: { url: "https://catalog.bergen.edu/content.php?catoid=13" },
      },
    };

    await expect(resolveCrawlPageUrl(page)).resolves.toBe(
      "https://catalog.bergen.edu/preview_program.php?catoid=13&poid=2266&returnto=664"
    );
  });
});