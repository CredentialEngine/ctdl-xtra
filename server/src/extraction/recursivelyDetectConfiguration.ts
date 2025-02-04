import { PageType, RecipeConfiguration } from "@common/types";
import { inspect } from "util";
import { bestOutOf, exponentialRetry, unique } from "../utils";
import { fetchBrowserPage, simplifiedMarkdown } from "./browser";
import { detectPageType } from "./llm/detectPageType";
import { detectPagination } from "./llm/detectPagination";
import detectUrlRegexp, { createUrlExtractor } from "./llm/detectUrlRegexp";

const sample = <T>(arr: T[], sampleSize: number) =>
  arr.sort(() => 0.5 - Math.random()).slice(0, sampleSize);

const detectConfiguration = async (url: string) => {
  let { content, screenshot } = await fetchBrowserPage(url);
  const markdownContent = await simplifiedMarkdown(content);
  console.log(`Detecting page type for ${url}`);
  const pageType = await bestOutOf(
    5,
    () =>
      exponentialRetry(async () => {
        try {
          const pageType = await detectPageType({
            url,
            content: markdownContent,
            screenshot: screenshot,
          });
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
    5,
    () =>
      exponentialRetry(
        async () =>
          detectPagination(
            { url, content: markdownContent, screenshot: screenshot },
            pageType
          ),
        10
      ),
    (p) => inspect(p)
  );
  console.log(`Detected as: ${inspect(pagination)}`);
  let linkRegexp;
  if (
    pageType == PageType.CATEGORY_LINKS_PAGE ||
    pageType == PageType.COURSE_LINKS_PAGE
  ) {
    console.log(`Detecting regexp for ${url}`);
    linkRegexp = await bestOutOf(
      5,
      () =>
        exponentialRetry(
          async () =>
            detectUrlRegexp(
              { url, content: markdownContent, screenshot: screenshot },
              pageType
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
  depth: number = 1
) => {
  if (depth > 3) {
    throw new Error("Exceeded max category depth");
  }

  console.log("Detecting configuration for root page");
  const { content, linkRegexp, pageType, pagination } =
    await detectConfiguration(url);

  const configuration: RecipeConfiguration = {
    pageType,
    linkRegexp: linkRegexp?.source,
    pagination,
  };

  if (pageType == PageType.COURSE_DETAIL_PAGE) {
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
      sample(urls, 5).map(async (url) => detectConfiguration(url))
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
      pageType == PageType.COURSE_LINKS_PAGE &&
      childPage.pageType != PageType.COURSE_DETAIL_PAGE
    ) {
      throw new Error(
        `Detected course links page and expected course detail pages, but child pages are ${childPage.pageType}`
      );
    }

    if (childPage.pageType == PageType.COURSE_DETAIL_PAGE) {
      return configuration;
    }

    const childUrlExtractor = createUrlExtractor(childPage.linkRegexp!);
    const childUrls = await childUrlExtractor(childPage.url, childPage.content);

    console.log("Detecting configuration for sample child > child pages");
    const sampleChildPageConfigs = await Promise.all(
      sample(childUrls, 5).map(async (url) => detectConfiguration(url))
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

    if (childPage.pageType == PageType.COURSE_LINKS_PAGE) {
      if (childLinkPage.pageType != PageType.COURSE_DETAIL_PAGE) {
        throw new Error(
          `Detected course links page and expected course detail pages, but child pages are ${childLinkPage.pageType}`
        );
      }
      return configuration;
    } else if (childPage.pageType == PageType.CATEGORY_LINKS_PAGE) {
      configuration.links.links.links = await recursivelyDetectConfiguration(
        childLinkPage.url,
        depth + 1
      );
    }

    return configuration;
  }
};

export default recursivelyDetectConfiguration;
