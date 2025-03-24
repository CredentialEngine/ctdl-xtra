import { inspect } from "util";
import { expect } from "vitest";
import {
  CatalogueType,
  CourseStructuredData,
  LearningProgramStructuredData,
  RecipeConfiguration,
} from "../../common/types";
import {
  fetchBrowserPage,
  simplifiedMarkdown,
} from "../src/extraction/browser";
import { getCatalogueTypeDefinition } from "../src/extraction/catalogueTypes";
import { extractAndVerifyEntityData } from "../src/extraction/llm/extractAndVerifyEntityData";
import recursivelyDetectConfiguration from "../src/extraction/recursivelyDetectConfiguration";

export const EXTRACTION_TIMEOUT = 1000 * 60 * 10;

// Recipes can take a long time, let's wait for up to 30mins.
export const RECIPE_TIMEOUT = 1000 * 60 * 30;

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
  console.log(inspect(actual));

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
  const page = await fetchBrowserPage(url);
  if (!page?.content) {
    throw new Error(`Page ${url} not found`);
  }

  const simplifiedContent = await simplifiedMarkdown(page.content);

  const extractions = await extractAndVerifyEntityData({
    content: simplifiedContent,
    url: page.url,
    screenshot: page.screenshot,
    catalogueType,
  });

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
      console.log(
        `Found entities: ${extractions
          .map((e) => inspect(e.entity))
          .join("\n")}`
      );
      throw new Error(
        `${typeDef.name} ${(expectedItem as any)[typeDef.identifierProperty]} not found`
      );
    }
    console.log(`Extracted entity: ${inspect(extraction.entity)}`);
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
          console.log(
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
}
