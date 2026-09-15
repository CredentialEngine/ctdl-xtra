import { afterEach, describe, expect, it, vi } from "vitest";
import { verifyRecipeLinks } from "../src/agentic/verifyRecipeLinks";

vi.mock("../src/extraction/browser", () => ({
  BrowserFetchError: class BrowserFetchError extends Error {},
  fetchBrowserPage: vi.fn(),
  simplifiedMarkdown: vi.fn(),
}));

import { fetchBrowserPage, simplifiedMarkdown } from "../src/extraction/browser";

const fetchBrowserPageMock = vi.mocked(fetchBrowserPage);
const simplifiedMarkdownMock = vi.mocked(simplifiedMarkdown);

describe("verifyRecipeLinks", () => {
  afterEach(() => {
    vi.clearAllMocks();
  });

  it("passes pageLoadWaitTime through to the page fetch", async () => {
    fetchBrowserPageMock.mockResolvedValue({
      url: "https://example.edu/catalog",
      content: "<html></html>",
      screenshot: "",
      status: 200,
    });
    simplifiedMarkdownMock.mockResolvedValue(
      "[Course](https://example.edu/content.php?catoid=13&navoid=664)" as never
    );

    await verifyRecipeLinks({
      url: "https://example.edu/catalog",
      linkRegexp: "content\\.php\\?catoid=13&navoid=664",
      pageLoadWaitTime: 10,
    });

    expect(fetchBrowserPageMock).toHaveBeenCalledWith(
      expect.objectContaining({
        url: "https://example.edu/catalog",
        pageLoadWaitTime: 10,
      })
    );
  });
});
