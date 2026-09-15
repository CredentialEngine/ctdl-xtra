import { afterEach, describe, expect, it, vi } from "vitest";
import { CatalogueType } from "../../common/types";
import {
  MAX_TEST_EXTRACTIONS_PER_RECIPE,
  TEST_EXTRACTION_LIMIT_MESSAGE,
  TestExtractionLimitError,
  claimTestExtractionAttempt,
  resetTestExtractionAttempts,
  testExtraction,
} from "../src/agentic/testExtraction";

vi.mock("../src/data/recipes", () => ({
  findRecipeById: vi.fn(),
}));

vi.mock("../src/extraction/browser", () => ({
  BrowserFetchError: class BrowserFetchError extends Error {},
  fetchBrowserPage: vi.fn(),
  simplifiedMarkdown: vi.fn(),
}));

vi.mock("../src/extraction/runEntityExtraction", () => ({
  runEntityExtraction: vi.fn(),
}));

import { findRecipeById } from "../src/data/recipes";
import { fetchBrowserPage, simplifiedMarkdown } from "../src/extraction/browser";
import { runEntityExtraction } from "../src/extraction/runEntityExtraction";

const findRecipeByIdMock = vi.mocked(findRecipeById);
const fetchBrowserPageMock = vi.mocked(fetchBrowserPage);
const simplifiedMarkdownMock = vi.mocked(simplifiedMarkdown);
const runEntityExtractionMock = vi.mocked(runEntityExtraction);

async function* yieldEntries(count: number) {
  for (let i = 0; i < count; i++) {
    yield {
      entity: { course_id: `COURSE-${i}` },
      textInclusion: {},
    };
  }
}

describe("claimTestExtractionAttempt", () => {
  afterEach(() => {
    resetTestExtractionAttempts();
  });

  it("allows 10 calls for a recipe and rejects the 11th", () => {
    const recipeId = 42;
    for (let i = 1; i <= MAX_TEST_EXTRACTIONS_PER_RECIPE; i++) {
      expect(claimTestExtractionAttempt(recipeId)).toEqual({
        attempt: i,
        remaining: MAX_TEST_EXTRACTIONS_PER_RECIPE - i,
      });
    }
    expect(() => claimTestExtractionAttempt(recipeId)).toThrow(
      TestExtractionLimitError
    );
    expect(() => claimTestExtractionAttempt(recipeId)).toThrow(
      TEST_EXTRACTION_LIMIT_MESSAGE
    );
  });

  it("tracks limits per recipe ID", () => {
    expect(claimTestExtractionAttempt(1).attempt).toBe(1);
    expect(claimTestExtractionAttempt(2).attempt).toBe(1);
  });
});

describe("testExtraction", () => {
  afterEach(() => {
    resetTestExtractionAttempts();
    vi.clearAllMocks();
  });

  function mockRecipePage() {
    findRecipeByIdMock.mockResolvedValue({
      id: 7,
      catalogue: { catalogueType: CatalogueType.COURSES },
      configuration: {},
    } as Awaited<ReturnType<typeof findRecipeById>>);
    fetchBrowserPageMock.mockResolvedValue({
      url: "https://example.edu/course/101",
      content: "<html></html>",
      screenshot: "",
      status: 200,
    });
    simplifiedMarkdownMock.mockResolvedValue("# Course 101" as never);
  }

  it("returns extracted true when extraction generates entries", async () => {
    mockRecipePage();
    runEntityExtractionMock.mockReturnValue(yieldEntries(2));

    await expect(
      testExtraction({
        url: "https://example.edu/course/101",
        recipeId: 7,
      })
    ).resolves.toEqual({
      url: "https://example.edu/course/101",
      extracted: true,
      entryCount: 2,
      attempt: 1,
      remaining: MAX_TEST_EXTRACTIONS_PER_RECIPE - 1,
    });
  });

  it("returns extracted false when extraction generates no entries", async () => {
    mockRecipePage();
    runEntityExtractionMock.mockReturnValue(yieldEntries(0));

    await expect(
      testExtraction({
        url: "https://example.edu/course/101",
        recipeId: 7,
      })
    ).resolves.toEqual({
      url: "https://example.edu/course/101",
      extracted: false,
      entryCount: 0,
      attempt: 1,
      remaining: MAX_TEST_EXTRACTIONS_PER_RECIPE - 1,
    });
  });

  it("uses the provided pageLoadWaitTime when fetching the page", async () => {
    mockRecipePage();
    findRecipeByIdMock.mockResolvedValue({
      id: 7,
      catalogue: { catalogueType: CatalogueType.COURSES },
      configuration: { pageLoadWaitTime: 3 },
    } as Awaited<ReturnType<typeof findRecipeById>>);
    runEntityExtractionMock.mockReturnValue(yieldEntries(1));

    await testExtraction({
      url: "https://example.edu/course/101",
      recipeId: 7,
      pageLoadWaitTime: 10,
    });

    expect(fetchBrowserPageMock).toHaveBeenCalledWith(
      expect.objectContaining({
        url: "https://example.edu/course/101",
        pageLoadWaitTime: 10,
      })
    );
  });

  it("falls back to the saved recipe pageLoadWaitTime", async () => {
    mockRecipePage();
    findRecipeByIdMock.mockResolvedValue({
      id: 7,
      catalogue: { catalogueType: CatalogueType.COURSES },
      configuration: { pageLoadWaitTime: 3 },
    } as Awaited<ReturnType<typeof findRecipeById>>);
    runEntityExtractionMock.mockReturnValue(yieldEntries(1));

    await testExtraction({
      url: "https://example.edu/course/101",
      recipeId: 7,
    });

    expect(fetchBrowserPageMock).toHaveBeenCalledWith(
      expect.objectContaining({ pageLoadWaitTime: 3 })
    );
  });

  it("tells the agent it tried too many times after 10 calls", async () => {
    mockRecipePage();
    runEntityExtractionMock.mockReturnValue(yieldEntries(1));

    for (let i = 0; i < MAX_TEST_EXTRACTIONS_PER_RECIPE; i++) {
      await testExtraction({
        url: `https://example.edu/course/${i}`,
        recipeId: 7,
      });
    }

    await expect(
      testExtraction({
        url: "https://example.edu/course/overflow",
        recipeId: 7,
      })
    ).rejects.toThrow(TEST_EXTRACTION_LIMIT_MESSAGE);
  });
});
