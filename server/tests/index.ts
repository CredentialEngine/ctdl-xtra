import { inspect } from "util";
import { expect } from "vitest";
import {
  CatalogueType,
  CourseStructuredData,
  LearningProgramStructuredData,
  RecipeConfiguration,
} from "../../common/types";
import { findCrawlPageByUrl } from "../src/data/extractions";
import { readContent, readScreenshot } from "../src/data/schema";
import {
  fetchBrowserPage,
  simplifiedMarkdown,
} from "../src/extraction/browser";
import { getCatalogueTypeDefinition } from "../src/extraction/catalogueTypes";
import { determinePresenceOfEntity } from "../src/extraction/llm/determinePresenceOfEntity";
import { exploreAdditionalPages } from "../src/extraction/llm/exploreAdditionalPages";
import { extractAndVerifyEntityData } from "../src/extraction/llm/extractAndVerifyEntityData";
import recursivelyDetectConfiguration from "../src/extraction/recursivelyDetectConfiguration";
import getLogger from "../src/logging";

const logger = getLogger("tests.index");

export const EXTRACTION_TIMEOUT = 1000 * 60 * 10;

// Recipes can take a long time, let's wait for up to 30mins.
export const RECIPE_TIMEOUT = 1000 * 60 * 30;

/**
 * Get a page from the database or fetch it from the browser if it's not in the database.
 * @param url The URL of the page to get.
 * @returns The page content, URL, and screenshot.
 */
async function getPageWithFallback(url: string) {
  let page;

  try {
    page = await findCrawlPageByUrl(url);
  } catch (e) {
    logger.error(`Page ${url} not found in database, fetching from browser`, e);
  }

  if (page?.content) {
    return {
      content: await readContent(page.extractionId, page.crawlStepId, page.id),
      url,
      screenshot: page.screenshot
        ? await readScreenshot(page.extractionId, page.crawlStepId, page.id)
        : "",
    };
  }
  return fetchBrowserPage(url);
}

function matchesUrlPattern(expected: string, actual: string): boolean {
  const expectedUrl = new URL(expected);
  const actualUrl = new URL(actual);

  if (expectedUrl.origin !== actualUrl.origin) return false;

  if (expectedUrl.pathname !== actualUrl.pathname) return false;

  const expectedParams = Object.fromEntries(expectedUrl.searchParams.entries());
  const actualParams = Object.fromEntries(actualUrl.searchParams.entries());

  return Object.entries(expectedParams).every(([key, value]) => {
    return (
      actualParams[key] === value ||
      (value === "{page_num}" && actualParams[key]?.includes("{page_num}")) ||
      (value === "{offset}" && actualParams[key]?.includes("{offset}"))
    );
  });
}

export async function collectFromGenerator<T>(
  generator: AsyncGenerator<T>
): Promise<T[]> {
  const results: T[] = [];
  for await (const item of generator) {
    results.push(item);
  }
  return results;
}

export type RecipeConfigurationWithSampleLinks = RecipeConfiguration & {
  sampleLinks?: string[];
  links?: RecipeConfigurationWithSampleLinks;
};

export async function assertConfiguration(
  url: string,
  expected: RecipeConfigurationWithSampleLinks
): Promise<void> {
  const actual = await recursivelyDetectConfiguration(
    url,
    CatalogueType.COURSES
  );
  logger.info(inspect(actual));

  function compareConfigurations(
    actualConfig: any,
    expectedConfig: any,
    path: string = ""
  ): void {
    for (const key in expectedConfig) {
      const currentPath = path ? `${path}.${key}` : key;

      if (key === "pageType") {
        expect(actualConfig.pageType).toBe(expectedConfig.pageType);
      } else if (key === "sampleLinks" && actualConfig.linkRegexp) {
        const regexp = new RegExp(actualConfig.linkRegexp);
        for (const link of expectedConfig.sampleLinks || []) {
          expect(
            regexp.test(link),
            `Expected link ${link} to match regexp ${actualConfig.linkRegexp} at ${currentPath}`
          ).toBe(true);
        }
      } else if (key === "pagination") {
        if (expectedConfig.pagination) {
          expect(actualConfig.pagination).toBeDefined();
          if (actualConfig.pagination) {
            expect(actualConfig.pagination.urlPatternType).toBe(
              expectedConfig.pagination.urlPatternType
            );
            expect(actualConfig.pagination.totalPages).toBe(
              expectedConfig.pagination.totalPages
            );
            expect(
              matchesUrlPattern(
                expectedConfig.pagination.urlPattern,
                actualConfig.pagination.urlPattern
              ),
              `Expected URL pattern to match ${expectedConfig.pagination.urlPattern}, got ${actualConfig.pagination.urlPattern} at ${currentPath}`
            ).toBe(true);
          }
        } else {
          expect(actualConfig.pagination).toBeUndefined();
        }
      } else if (key === "links") {
        if (expectedConfig.links) {
          expect(actualConfig.links).toBeDefined();
          if (actualConfig.links) {
            compareConfigurations(
              actualConfig.links,
              expectedConfig.links,
              currentPath
            );
          }
        } else {
          expect(actualConfig.links).toBeUndefined();
        }
      }
    }
  }

  compareConfigurations(actual, expected);
}

export async function assertExtraction<
  T extends CourseStructuredData | LearningProgramStructuredData,
>(
  url: string,
  expected: T[],
  verified: boolean = false,
  catalogueType: CatalogueType = CatalogueType.COURSES
) {
  const typeDef = getCatalogueTypeDefinition(catalogueType);
  const page = await getPageWithFallback(url);
  if (!page?.content) {
    throw new Error(`Page ${url} not found`);
  }

  const simplifiedContent = await simplifiedMarkdown(page.content);

  const extractions = await collectFromGenerator(
    extractAndVerifyEntityData({
      content: simplifiedContent,
      url: page.url,
      screenshot: page.screenshot,
      catalogueType,
    })
  );

  for (const expectedItem of expected) {
    const extraction = extractions.find((item) =>
      item.entity[typeDef.identifierProperty]
        .toLowerCase()
        .replace(/[\W\s]+/g, "")
        .includes(
          (expectedItem as any)[typeDef.identifierProperty]
            .toLowerCase()
            .replace(/[\W\s]+/g, "")
        )
    );
    if (!extraction) {
      logger.info(
        `Found entities: ${extractions
          .map((e) => inspect(e.entity))
          .join("\n")}`
      );
      throw new Error(
        `${typeDef.name} ${(expectedItem as any)[typeDef.identifierProperty]} not found`
      );
    }
    logger.info(`Extracted entity: ${inspect(extraction.entity)}`);
    for (const key in expectedItem) {
      let expectedValue = expectedItem[key as keyof T];
      let extractedValue = (extraction.entity as any)[key as keyof T];

      if (
        typeof expectedValue === "string" &&
        typeof extractedValue === "string"
      ) {
        expect(extractedValue.toLowerCase().replace(/[\W\s]+/g, "")).toContain(
          expectedValue.toLowerCase().replace(/[\W\s]+/g, "")
        );
      } else {
        if (extractedValue != expectedValue) {
          logger.info(
            `Expected ${key} to be ${expectedValue}, got ${extractedValue}.`
          );
        }
        if (extractedValue === 0 && expectedValue === undefined) {
          (expectedValue as any) = 0;
        }
        expect(extractedValue).toEqual(expectedValue);
      }
    }
    if (verified) {
      if (catalogueType === CatalogueType.COURSES) {
        expect(extraction.textInclusion.course_id?.full).toBe(true);
        expect(extraction.textInclusion.course_description?.full).toBe(true);
        if (extraction.entity.course_prerequisites) {
          expect(extraction.textInclusion.course_prerequisites?.full).toBe(
            true
          );
        }
      } else if (catalogueType === CatalogueType.LEARNING_PROGRAMS) {
        expect(extraction.textInclusion.learning_program_id?.full).toBe(true);
        expect(
          extraction.textInclusion.learning_program_description?.full
        ).toBe(true);
      }
    }
  }
  return extractions;
}

export async function extractCompetencies(url: string) {
  const page = await fetchBrowserPage(url).then((page) =>
    page.content ? page : Promise.reject(new Error(`Page ${url} not found`))
  );
  const simplifiedContent = await simplifiedMarkdown(page.content);

  const extractionOptions = {
    content: simplifiedContent,
    url: page.url,
    screenshot: page.screenshot,
    catalogueType: CatalogueType.COMPETENCIES,
  };

  // Check if competencies are present on the page
  const entityDef = getCatalogueTypeDefinition(CatalogueType.COMPETENCIES);
  if (entityDef.presencePrompt) {
    const presenceResult = await determinePresenceOfEntity(
      extractionOptions,
      entityDef
    );
    if (!presenceResult.present) {
      return []; // Return empty array if no competencies are present
    }
  }

  const extractions = await collectFromGenerator(
    extractAndVerifyEntityData(extractionOptions)
  );
  return extractions.map((e) => e.entity);
}

export async function extractCredentials(
  url: string,
) {
  const page = await fetchBrowserPage(url)
    .then(page => page.content
      ? page
      : Promise.reject(new Error(`Page ${url} not found`))
    );
  const simplifiedContent = await simplifiedMarkdown(page.content);
  
  const extractionOptions = {
    content: simplifiedContent,
    url: page.url,
    screenshot: page.screenshot,
    catalogueType: CatalogueType.CREDENTIALS,
  };
  
  // Check if credentials are present on the page
  const entityDef = getCatalogueTypeDefinition(CatalogueType.CREDENTIALS);
  if (entityDef.presencePrompt) {
    const presenceResult = await determinePresenceOfEntity(extractionOptions, entityDef);
    if (!presenceResult.present) {
      return []; // Return empty array if no credentials are present
    }
  }
  
  const extractions = await collectFromGenerator(
    extractAndVerifyEntityData(extractionOptions)
  );
  return extractions.map(e => e.entity);
}

export async function detectExploratoryPages(
  url: string,
  catalogueType: CatalogueType = CatalogueType.COMPETENCIES
) {
  const page = await getPageWithFallback(url).then((page) =>
    page.content ? page : Promise.reject(new Error(`Page ${url} not found`))
  );
  const simplifiedContent = await simplifiedMarkdown(page.content);

  const { data: urls } = await exploreAdditionalPages(
    {
      url: page.url,
      content: simplifiedContent,
      screenshot: page.screenshot,
    },
    catalogueType
  );

  return urls;
}
