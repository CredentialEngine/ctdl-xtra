import type { CatalogueType, PageSetupConfig } from "../../../common/types";
import { findRecipeById } from "../data/recipes";
import {
  BrowserFetchError,
  fetchBrowserPage,
  simplifiedMarkdown,
} from "../extraction/browser";
import { runEntityExtraction } from "../extraction/runEntityExtraction";
import type { SimplifiedMarkdown } from "../types";

export const MAX_TEST_EXTRACTIONS_PER_RECIPE = 10;

export const TEST_EXTRACTION_LIMIT_MESSAGE =
  `Tried too many times. xtra_test_extraction is limited to ${MAX_TEST_EXTRACTIONS_PER_RECIPE} calls for this recipe.`;

export class TestExtractionLimitError extends Error {
  constructor() {
    super(TEST_EXTRACTION_LIMIT_MESSAGE);
    this.name = "TestExtractionLimitError";
  }
}

const attemptsByRecipeId = new Map<number, number>();

export function claimTestExtractionAttempt(recipeId: number): {
  attempt: number;
  remaining: number;
} {
  const used = attemptsByRecipeId.get(recipeId) ?? 0;
  if (used >= MAX_TEST_EXTRACTIONS_PER_RECIPE) {
    throw new TestExtractionLimitError();
  }
  const attempt = used + 1;
  attemptsByRecipeId.set(recipeId, attempt);
  return {
    attempt,
    remaining: MAX_TEST_EXTRACTIONS_PER_RECIPE - attempt,
  };
}

export function resetTestExtractionAttempts(): void {
  attemptsByRecipeId.clear();
}

export interface TestExtractionInput {
  url: string;
  recipeId: number;
  pageLoadWaitTime?: number;
  pageSetup?: PageSetupConfig;
}

export interface TestExtractionResult {
  url: string;
  extracted: boolean;
  entryCount: number;
  attempt: number;
  remaining: number;
}

export async function testExtraction(
  input: TestExtractionInput
): Promise<TestExtractionResult> {
  const { attempt, remaining } = claimTestExtractionAttempt(input.recipeId);

  const recipe = await findRecipeById(input.recipeId);
  if (!recipe) {
    throw new Error(`Recipe ${input.recipeId} not found`);
  }

  const catalogueType = recipe.catalogue?.catalogueType as
    | CatalogueType
    | undefined;
  if (!catalogueType) {
    throw new Error(`Recipe ${input.recipeId} has no catalogue type`);
  }

  const configuration = recipe.configuration;
  let markdownContent: SimplifiedMarkdown;
  let screenshot: string;

  try {
    const page = await fetchBrowserPage({
      url: input.url,
      skipProxy: false,
      pageLoadWaitTime:
        input.pageLoadWaitTime ?? configuration?.pageLoadWaitTime,
      pageSetup: input.pageSetup ?? configuration?.pageSetup,
    });
    markdownContent = await simplifiedMarkdown(
      page.content,
      configuration?.contentSelector
    );
    screenshot = page.screenshot ?? "";
  } catch (error) {
    if (error instanceof BrowserFetchError) {
      throw new Error(error.uiMessage());
    }
    throw error;
  }

  let entryCount = 0;
  for await (const _entry of runEntityExtraction({
    url: input.url,
    content: markdownContent,
    screenshot,
    catalogueType,
  })) {
    entryCount++;
  }

  return {
    url: input.url,
    extracted: entryCount > 0,
    entryCount,
    attempt,
    remaining,
  };
}
