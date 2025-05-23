import { readFile } from "fs/promises";
import path from "path";
import { describe, expect, it } from "vitest";
import { simplifiedMarkdown, simplifyHtml } from "../src/extraction/browser";
import getLogger from "../src/logging";

const logger = getLogger("tests.browser");

describe("simplifiedMarkdown", () => {
  it("should simplify the html", async () => {
    // read test/fixtures/doc.html
    const rawHtml = await readFile(
      path.join(__dirname, "fixtures", "doc.html"),
      "utf8"
    );
    const markdown = await readFile(
      path.join(__dirname, "fixtures", "doc_simplified.md"),
      "utf8"
    );
    const simplifiedHtml = await simplifyHtml(rawHtml);
    logger.info(simplifiedHtml);
    const simplified = await simplifiedMarkdown(rawHtml);
    expect(simplified).toBe(markdown);
  });
});
