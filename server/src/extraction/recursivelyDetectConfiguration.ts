import { inspect } from "util";
import {
  CatalogueType,
  PageType,
  RecipeConfiguration,
} from "../../../common/types";
import { bestOutOf, exponentialRetry, unique } from "../utils";
import { fetchBrowserPage, simplifiedMarkdown } from "./browser";
import { detectPageType } from "./llm/detectPageType";
import { detectPagination } from "./llm/detectPagination";
import detectUrlRegexp, { createUrlExtractor } from "./llm/detectUrlRegexp";
import { Probes } from "./vendor-probes";

const sample = <T>(arr: T[], sampleSize: number) =>
  arr.sort(() => 0.5 - Math.random()).slice(0, sampleSize);

const detectConfiguration = async (
  url: string,
  catalogueType: CatalogueType,
  pageData?: { content: string; screenshot: string },
  currentConfiguration?: RecipeConfiguration
) => {
  let { content, screenshot } = pageData || (await fetchBrowserPage(url));
  const markdownContent = await simplifiedMarkdown(content);
  console.log(`Detecting page type for ${url}`);
  const pageType = await bestOutOf(
    10,
    () =>
      exponentialRetry(async () => {
        try {
          const pageType = await detectPageType(
            {
              url,
              content: markdownContent,
              screenshot: screenshot,
              catalogueType,
            },
            currentConfiguration
          );
          return pageType;
        } catch (e) {
          console.log(`Error detecting page type for ${url}: ${inspect(e)}`);
          throw e;
        }
      }, 10),
    (t) => t as string
  );
  console.log(`Detected as ${pageType}`);
  if (!pageType) {
    throw new Error(`Couldn't detect page type for URL ${url}`);
  }
  console.log(`Detecting pagination for ${url}`);
  const pagination = await bestOutOf(
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
            pageType,
            currentConfiguration
          ),
        10
      ),
    (p) => inspect(p)
  );
  console.log(`Detected as: ${inspect(pagination)}`);
  let linkRegexp;
  if (
    pageType == PageType.CATEGORY_LINKS ||
    pageType == PageType.DETAIL_LINKS
  ) {
    console.log(`Detecting regexp for ${url}`);
    linkRegexp = await bestOutOf(
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
              currentConfiguration
            ),
          10
        ),
      (r) => r.source
    );
    console.log(`Detect as ${linkRegexp}`);
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
  depth: number = 1,
  currentConfiguration?: RecipeConfiguration
) => {
  if (depth > 3) {
    throw new Error("Exceeded max category depth");
  }

  let { content: pageContent, screenshot } = await fetchBrowserPage(url);
  const apiReceipe = await Probes.detectApiProviderRecipe({
    pageContent,
    pageUrl: url,
  });

  if (apiReceipe) {
    console.log(
      `API provider identified ${apiReceipe.apiProvider}. Skipping page format detection.`
    );
    return apiReceipe;
  }

  console.log("Detecting configuration for root page");
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
    console.log("Detecting configuration for sample child pages");
    console.log(`There are ${urls.length} URLs and we're sampling 5`);
    const samplePageConfigs = await Promise.all(
      sample(urls, 5).map(async (url) =>
        detectConfiguration(url, catalogueType, undefined, currentConfiguration)
      )
    );

    const mixedContent =
      unique(samplePageConfigs.map((spc) => spc.pageType)).length > 1;

    if (mixedContent) {
      // If the LLM detects mixed content in the child pages, something is probably off; abort.
      throw new Error("Couldn't determine page type for links");
    }

    const childPage = samplePageConfigs[0];

    configuration.links = {
      pageType: childPage.pageType,
      linkRegexp: childPage.linkRegexp?.source,
      pagination: childPage.pagination,
    };

    if (
      pageType == PageType.DETAIL_LINKS &&
      childPage.pageType != PageType.DETAIL
    ) {
      throw new Error(
        `Detected course links page and expected course detail pages, but child pages are ${childPage.pageType}`
      );
    }

    if (childPage.pageType == PageType.DETAIL) {
      return configuration;
    }

    const childUrlExtractor = createUrlExtractor(childPage.linkRegexp!);
    const childUrls = await childUrlExtractor(childPage.url, childPage.content);

    console.log("Detecting configuration for sample child > child pages");
    const sampleChildPageConfigs = await Promise.all(
      sample(childUrls, 5).map(async (url) =>
        detectConfiguration(url, catalogueType, undefined, currentConfiguration)
      )
    );

    const mixedChildContent =
      unique(sampleChildPageConfigs.map((spc) => spc.pageType)).length > 1;

    if (mixedChildContent) {
      // If the LLM detects mixed content in the child pages, something is probably off; abort.
      throw new Error("Couldn't determine page type for child links");
    }

    const childLinkPage = sampleChildPageConfigs[0];

    configuration.links.links = {
      pageType: childLinkPage.pageType,
      linkRegexp: childLinkPage.linkRegexp?.source,
      pagination: childLinkPage.pagination,
    };

    if (childPage.pageType == PageType.DETAIL_LINKS) {
      if (childLinkPage.pageType != PageType.DETAIL) {
        throw new Error(
          `Detected course links page and expected course detail pages, but child pages are ${childLinkPage.pageType}`
        );
      }
      return configuration;
    } else if (childPage.pageType == PageType.CATEGORY_LINKS) {
      configuration.links.links.links = await recursivelyDetectConfiguration(
        childLinkPage.url,
        catalogueType,
        depth + 1,
        configuration
      );
    }

    return configuration;
  }
};

export default recursivelyDetectConfiguration;
