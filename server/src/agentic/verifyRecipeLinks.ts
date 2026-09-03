import type { ClickDiscoveryOptions, PageSetupConfig } from "../../../common/types";
import {
  BrowserFetchError,
  fetchBrowserPage,
  simplifiedMarkdown,
} from "../extraction/browser";
import { discoverDynamicLinks } from "../extraction/dynamicLinkDiscovery";
import { createUrlExtractor } from "../extraction/llm/detectUrlRegexp";
import type { SimplifiedMarkdown } from "../types";
import { normalizeUrl } from "../utils";

export interface VerifyRecipeLinksInput {
  url: string;
  linkRegexp?: string;
  clickSelector?: string;
  clickOptions?: ClickDiscoveryOptions;
  exactLinkPatternMatch?: boolean;
  pageLoadWaitTime?: number;
  pageSetup?: PageSetupConfig;
}

export interface VerifyRecipeLinksResult {
  url: string;
  linkRegexp?: string;
  matchCount: number;
  urls: string[];
  sampleUrls: string[];
  markdownPreview: string;
}

const MARKDOWN_PREVIEW_LENGTH = 2000;

export async function verifyRecipeLinks(
  input: VerifyRecipeLinksInput
): Promise<VerifyRecipeLinksResult> {
  const regexp = input.linkRegexp?.trim();
  let urls: string[];
  let markdownContent: string;

  try {
    if (input.clickSelector) {
      urls = await discoverDynamicLinks({
        rootUrl: input.url,
        selector: input.clickSelector,
        clickOptions: input.clickOptions,
        pageSetup: input.pageSetup,
      });

      if (regexp) {
        const testRegex = new RegExp(regexp, "g");
        const exactMatch = input.exactLinkPatternMatch ?? false;
        if (exactMatch) {
          urls = urls.flatMap((url) => {
            const matches = url.match(testRegex);
            return matches ?? [];
          });
        } else {
          urls = urls.filter((url) => testRegex.test(url));
        }
        testRegex.lastIndex = 0;
      }

      const { content } = await fetchBrowserPage({
        url: input.url,
        skipProxy: false,
        pageLoadWaitTime: input.pageLoadWaitTime,
        pageSetup: input.pageSetup,
      });
      markdownContent = await simplifiedMarkdown(content);
    } else {
      if (!regexp) {
        throw new Error(
          "linkRegexp is required when clickSelector is not provided"
        );
      }

      const { content } = await fetchBrowserPage({
        url: input.url,
        skipProxy: false,
        pageLoadWaitTime: input.pageLoadWaitTime,
        pageSetup: input.pageSetup,
      });
      markdownContent = await simplifiedMarkdown(content);

      const testRegex = new RegExp(regexp, "g");
      const extractor = createUrlExtractor(testRegex);
      const extractedUrls = await extractor(
        input.url,
        markdownContent as SimplifiedMarkdown,
        input.exactLinkPatternMatch ?? false
      );
      urls = extractedUrls.filter((url): url is string => url !== null);
    }
  } catch (error) {
    if (error instanceof BrowserFetchError) {
      throw new Error(error.uiMessage());
    }
    throw error;
  }

  const normalizedUrls = urls.map((url) => normalizeUrl(url, input.url));
  const uniqueUrls = [...new Set(normalizedUrls)];

  return {
    url: input.url,
    linkRegexp: regexp,
    matchCount: uniqueUrls.length,
    urls: uniqueUrls,
    sampleUrls: uniqueUrls.slice(0, 10),
    markdownPreview: markdownContent.slice(0, MARKDOWN_PREVIEW_LENGTH),
  };
}
