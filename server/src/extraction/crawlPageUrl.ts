import { findPageForJob, findPages } from "../data/extractions";
import { normalizeUrl } from "../utils";

export type CrawlPageForUrl = Awaited<ReturnType<typeof findPageForJob>>;

export type CrawlPageUrlInput = Pick<CrawlPageForUrl, "url"> & {
  crawlStep: Pick<CrawlPageForUrl["crawlStep"], "parentStepId">;
  extraction: { recipe: { url: string } };
};

function ensureAbsoluteBaseUrl(baseUrl: string, recipeUrl: string): string {
  try {
    return new URL(baseUrl).href;
  } catch {
    try {
      return new URL(baseUrl, recipeUrl).href;
    } catch {
      return recipeUrl;
    }
  }
}

/** Absolute URL for resolving relative crawl pages (parent step page, else recipe URL). */
export async function resolveCrawlPageBaseUrl(
  crawlPage: CrawlPageUrlInput
): Promise<string> {
  const recipeUrl = crawlPage.extraction.recipe.url;
  let baseUrl: string | undefined;

  if (crawlPage.crawlStep.parentStepId) {
    const parentPages = await findPages(crawlPage.crawlStep.parentStepId);
    if (parentPages.length > 0) {
      baseUrl = parentPages[0].url;
    }
  }

  if (!baseUrl) {
    baseUrl = recipeUrl;
  }

  return ensureAbsoluteBaseUrl(baseUrl, recipeUrl);
}

/** Absolute URL for fetching, LLM extraction, and link exploration. */
export async function resolveCrawlPageUrl(
  crawlPage: CrawlPageUrlInput
): Promise<string> {
  try {
    return new URL(crawlPage.url).href;
  } catch {
    const baseUrl = await resolveCrawlPageBaseUrl(crawlPage);
    return normalizeUrl(crawlPage.url, baseUrl);
  }
}