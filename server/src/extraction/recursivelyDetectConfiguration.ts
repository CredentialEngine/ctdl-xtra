import { inspect } from "util";
import {
  CatalogueType,
  PageType,
  RecipeConfiguration,
} from "../../../common/types";
import getLogger from "../logging";
import { SimplifiedMarkdown } from "../types";
import { bestOutOf, exponentialRetry, unique } from "../utils";
import { fetchBrowserPage, simplifiedMarkdown } from "./browser";
import { detectPageType } from "./llm/detectPageType";
import { detectPagination } from "./llm/detectPagination";
import detectUrlRegexp, {
  AdditionalPage,
  createUrlExtractor,
} from "./llm/detectUrlRegexp";
import { Probes } from "./vendor-probes";

const logger = getLogger("extraction.recursivelyDetectConfiguration");

const sample = <T>(arr: T[], sampleSize: number) =>
  arr.sort(() => 0.5 - Math.random()).slice(0, sampleSize);

const detectPageTypeWithRetry = async (
  url: string,
  markdownContent: SimplifiedMarkdown,
  screenshot: string,
  catalogueType: CatalogueType
) => {
  return bestOutOf(
    10,
    () =>
      exponentialRetry(async () => {
        try {
          const pageType = await detectPageType({
            url,
            content: markdownContent,
            screenshot: screenshot,
            catalogueType,
          });
          return pageType;
        } catch (e) {
          logger.error(`Error detecting page type for ${url}: ${inspect(e)}`);
          throw e;
        }
      }, 10),
    (t) => t as string
  );
};

const detectPaginationWithRetry = async (
  url: string,
  markdownContent: SimplifiedMarkdown,
  screenshot: string,
  catalogueType: CatalogueType,
  pageType: PageType
) => {
  return bestOutOf(
    10,
    () =>
      exponentialRetry(
        async () =>
          detectPagination(
            {
              url,
              content: markdownContent,
              screenshot: screenshot,
              catalogueType,
            },
            pageType
          ),
        10
      ),
    (p) => inspect(p)
  );
};

const detectUrlRegexpWithRetry = async (
  url: string,
  markdownContent: SimplifiedMarkdown,
  screenshot: string,
  catalogueType: CatalogueType,
  pageType: PageType,
  additionalPages?: AdditionalPage[]
) => {
  return bestOutOf(
    3,
    () =>
      exponentialRetry(
        async () =>
          detectUrlRegexp(
            {
              url,
              content: markdownContent,
              screenshot: screenshot,
              catalogueType,
            },
            pageType,
            additionalPages
          ),
        10
      ),
    (r) => r.source
  );
};

const detectConfiguration = async (
  url: string,
  catalogueType: CatalogueType,
  pageData?: { content: string; screenshot: string }
) => {
  let { content, screenshot } = pageData || (await fetchBrowserPage(url));
  const markdownContent = await simplifiedMarkdown(content);
  logger.info(`Detecting page type for ${url}`);
  const pageType = await detectPageTypeWithRetry(
    url,
    markdownContent,
    screenshot,
    catalogueType
  );
  logger.info(`Detected as ${pageType}`);
  if (!pageType) {
    throw new Error(`Couldn't detect page type for URL ${url}`);
  }
  logger.info(`Detecting pagination for ${url}`);
  const pagination = await detectPaginationWithRetry(
    url,
    markdownContent,
    screenshot,
    catalogueType,
    pageType
  );
  logger.info(`Detected as: ${inspect(pagination)}`);
  let linkRegexp;
  if (
    pageType == PageType.CATEGORY_LINKS ||
    pageType == PageType.DETAIL_LINKS
  ) {
    logger.info(`Detecting regexp for ${url}`);
    linkRegexp = await detectUrlRegexpWithRetry(
      url,
      markdownContent,
      screenshot,
      catalogueType,
      pageType
    );
    logger.info(`Detected as ${linkRegexp}`);
  }
  return {
    content: markdownContent,
    linkRegexp,
    pageType,
    pagination,
    screenshot,
    url,
  };
};

const recursivelyDetectConfiguration = async (
  url: string,
  catalogueType: CatalogueType,
  depth: number = 1
) => {
  if (depth > 3) {
    throw new Error("Exceeded max category depth");
  }

  let { content: pageContent, screenshot } = await fetchBrowserPage(url);
  const apiReceipe = await Probes.detectApiProviderRecipe({
    pageContent,
    pageUrl: url,
  });

  if (apiReceipe && catalogueType === CatalogueType.COURSES) {
    logger.info(
      `API provider identified ${apiReceipe.apiProvider}. Skipping page format detection.`
    );
    return apiReceipe;
  }

  logger.info("Detecting configuration for root page");
  const { content, linkRegexp, pageType, pagination } =
    await detectConfiguration(url, catalogueType, {
      content: pageContent,
      screenshot,
    });

  const configuration: RecipeConfiguration = {
    pageType,
    linkRegexp: linkRegexp?.source,
    pagination,
  };

  if (pageType == PageType.DETAIL) {
    // We are already at the course details page.
    return configuration;
  } else {
    // This is either a course links page or a course category links page.

    const urlExtractor = createUrlExtractor(linkRegexp!);
    const urls = await urlExtractor(url, content);

    // Extract some sample pages which we'll use to confirm the page type.
    logger.info("Detecting configuration for sample child pages");
    logger.info(`There are ${urls.length} URLs and we're sampling 5`);

    const sampleLinks = await Promise.all(
      sample(urls, 5).map(async (url) => {
        const { content, screenshot } = await fetchBrowserPage(url);
        const markdownContent = await simplifiedMarkdown(content);
        return { url, content: markdownContent, screenshot };
      })
    );

    const linkedPageTypes = await Promise.all(
      sampleLinks.map(async (page) => {
        return detectPageTypeWithRetry(
          page.url,
          page.content,
          page.screenshot,
          catalogueType
        );
      })
    );

    const mixedContent = unique(linkedPageTypes).length > 1;

    if (mixedContent) {
      // If the LLM detects mixed content in the child pages, something is probably off; abort.
      throw new Error("Couldn't determine page type for links - mixed results");
    }

    const linkedPageType = linkedPageTypes[0];

    if (!linkedPageType) {
      throw new Error("Couldn't determine page type for links - no results");
    }

    if (
      pageType == PageType.DETAIL_LINKS &&
      linkedPageType != PageType.DETAIL
    ) {
      throw new Error(
        `Detected course links page and expected course detail pages, but child pages are ${linkedPageType}`
      );
    }

    const childLinkRegexp =
      linkedPageType == PageType.DETAIL
        ? null
        : await detectUrlRegexpWithRetry(
            sampleLinks[0].url,
            sampleLinks[0].content,
            sampleLinks[0].screenshot,
            catalogueType,
            linkedPageType,
            sampleLinks.slice(1)
          );

    configuration.links = {
      pageType: linkedPageType,
      linkRegexp: childLinkRegexp?.source,
      pagination: pagination,
    };

    if (linkedPageType == PageType.DETAIL) {
      return configuration;
    }

    const childUrlExtractor = createUrlExtractor(childLinkRegexp!);
    const childUrls = await childUrlExtractor(
      sampleLinks[0].url,
      sampleLinks[0].content
    );

    logger.info("Detecting configuration for sample child > child pages");
    const sampleSubChildLinks = await Promise.all(
      sample(childUrls, 5).map(async (url) => {
        const { content, screenshot } = await fetchBrowserPage(url);
        const markdownContent = await simplifiedMarkdown(content);
        return { url, content: markdownContent, screenshot };
      })
    );
    const subChildPageTypes = await Promise.all(
      sampleSubChildLinks.map(async (page) =>
        detectPageTypeWithRetry(
          page.url,
          page.content,
          page.screenshot,
          catalogueType
        )
      )
    );

    const mixedSubChildContent = unique(subChildPageTypes).length > 1;

    if (mixedSubChildContent) {
      // If the LLM detects mixed content in the child pages, something is probably off; abort.
      throw new Error(
        "Couldn't determine page type for child links - mixed results"
      );
    }

    const subChildPageType = subChildPageTypes[0];

    if (!subChildPageType) {
      throw new Error(
        "Couldn't determine page type for child links - no results"
      );
    }

    if (
      linkedPageType == PageType.DETAIL_LINKS &&
      subChildPageType != PageType.DETAIL
    ) {
      throw new Error(
        `Detected course links page and expected course detail pages, but child pages are ${subChildPageType}`
      );
    }

    const subChildLinkRegexp =
      subChildPageType == PageType.DETAIL
        ? null
        : await detectUrlRegexpWithRetry(
            sampleSubChildLinks[0].url,
            sampleSubChildLinks[0].content,
            sampleSubChildLinks[0].screenshot,
            catalogueType,
            subChildPageType,
            sampleSubChildLinks.slice(1)
          );

    configuration.links.links = {
      pageType: subChildPageType,
      linkRegexp: subChildLinkRegexp?.source,
      pagination: pagination,
    };

    if (linkedPageType == PageType.DETAIL_LINKS) {
      return configuration;
    }

    if (linkedPageType == PageType.CATEGORY_LINKS) {
      configuration.links.links.links = await recursivelyDetectConfiguration(
        sampleSubChildLinks[0].url,
        catalogueType,
        depth + 1
      );
    }

    return configuration;
  }
};

export default recursivelyDetectConfiguration;
