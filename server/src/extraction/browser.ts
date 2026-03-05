import { isDeepStrictEqual } from 'node:util';
import * as cheerio from "cheerio";
import { Cluster} from "puppeteer-cluster";
import { addExtra, VanillaPuppeteer } from "puppeteer-extra";
import StealthPlugin from "puppeteer-extra-plugin-stealth";
import rebrowserPuppeteer, { HTTPResponse } from "rebrowser-puppeteer";
import TurndownService from "turndown";
import { URL } from "url";
import { findSetting } from "../data/settings";
import getLogger from "../logging";
import { SimplifiedMarkdown } from "../types";
import { httpCodeToMessage, isProxyError, resolveAbsoluteUrl } from "../utils";
import { detectCatalogueType } from "./llm/detectCatalogueType";

export interface BrowserTaskInput {
  url: string;
  pageLoadWaitTime?: number;
}

export interface BrowserTaskResult {
  url: string;
  content: string;
  screenshot: string;
  status: number;
}

export class BrowserFetchError extends Error {
  readonly status: number;
  readonly url: string;

  constructor(browserResult: BrowserTaskResult) {
    const statusMessage = httpCodeToMessage(browserResult?.status as any);
    super(statusMessage);

    this.status = browserResult?.status;
    this.url = browserResult?.url;
  }

  statusMessage() {
    return httpCodeToMessage(this.status as any);
  }

  toString() {
    return `BrowserFetchError: ${this.status}: ${this.statusMessage()} for ${this.url}\nStack: ${this.stack}`;
  }

  uiMessage() {
    return `Failed to fetch page - issue: ${this.statusMessage()} (HTTP ${this.status})`;
  }
}

const puppeteer = addExtra(rebrowserPuppeteer as unknown as VanillaPuppeteer);
puppeteer.use(StealthPlugin());

let cluster: Cluster<BrowserTaskInput, BrowserTaskResult> | undefined;
let clusterLaunchOptions: Record<string, unknown> | undefined;
let clusterClosed = false;

const PAGE_TIMEOUT = 5 * 60 * 1000;

const logger = getLogger("extraction.browser");

export async function getCluster(proxyUrl?: string) {
  if (clusterClosed) {
    throw new Error("Cluster has been closed");
  }
  let proxyBaseUrl = null;
  let proxyUsername = null;
  let proxyPassword = null;
  if (proxyUrl) {
    const url = new URL(proxyUrl);
    proxyBaseUrl = `${url.protocol}//${url.host}`;
    proxyUsername = url.username;
    proxyPassword = url.password;
  }

  const newClusterLaunchOptions = {
    concurrency: Cluster.CONCURRENCY_CONTEXT,
    maxConcurrency: 2,
    puppeteer: puppeteer,
    puppeteerOptions: {
      headless: true,
      ignoreHTTPSErrors: true,
      dumpio: true, // Pipe Chrome process stdout/stderr to console when DEBUG=1
      args: [
        "--font-render-hinting=none",
        "--force-gpu-mem-available-mb=4096",
        "--ignore-certificate-errors",
        proxyBaseUrl ? `--proxy-server=${proxyBaseUrl}` : "",
      ].filter(Boolean),
    },
    timeout: PAGE_TIMEOUT,
  };

  if (cluster && clusterLaunchOptions && isDeepStrictEqual(clusterLaunchOptions, newClusterLaunchOptions)) {
    return cluster;
  } else {
    await cluster?.close();
  }

  cluster = await Cluster.launch(newClusterLaunchOptions);
  clusterLaunchOptions = newClusterLaunchOptions;

  await cluster.task(async ({ page, data }): Promise<BrowserTaskResult> => {
    if (proxyUsername || proxyPassword) {
      await page.authenticate({
        username: proxyUsername || "",
        password: proxyPassword || "",
      });
    }

    page.setDefaultTimeout(PAGE_TIMEOUT);
    const { url, pageLoadWaitTime } = data;
    let response: HTTPResponse | null = null;

    response = await page.goto(url, {
      timeout: PAGE_TIMEOUT,
      waitUntil: "networkidle2",
    }) as unknown as HTTPResponse; // TODO: Remove when puppeteer-cluster is updated to return the same type of HTTPResponse as rebrowser-puppeteer    

    if (!response) {
      throw new Error(`Failed to load page ${url}, no response received.`);
    }
    
    // Wait for the specified time if provided
    if (pageLoadWaitTime && pageLoadWaitTime > 0) {
      logger.info(`Waiting ${pageLoadWaitTime} seconds for page scripts to complete at ${url}`);
      await new Promise(resolve => setTimeout(resolve, pageLoadWaitTime * 1000));
    }
    
    let content = await page.content();
    if (content.includes("kuali-catalog")) {
      logger.info(`Kuali detected at url ${url}; waiting for selector`);
      await page.waitForFunction(
        `document.querySelector("#kuali-catalog-main h3") || document.querySelector("#kuali-catalog-main ul li")`
      );
      content = await page.content();
    }
    const screenshot = await page.screenshot({
      type: "webp",
      fullPage: false,
      quality: 60,
      encoding: "base64",
    });
    return {
      url,
      content,
      screenshot,
      status: response.status(),
    };
  });
  return cluster;
}

export async function closeCluster() {
  if (!cluster) {
    return;
  }

  clusterClosed = true;
  await cluster.idle();
  await cluster.close();
}

export async function findProxies(): Promise<string[] | undefined> {
  // Prefer environment variable if provided, regardless of DB settings
  if (process.env.PROXY_URL && process.env.PROXY_URL.trim()) {
    return [process.env.PROXY_URL];
  }

  // Fall back to DB-driven settings
  const proxyEnabled = await findSetting<boolean>("PROXY_ENABLED");
  if (!proxyEnabled?.value) {
    return undefined;
  }
  const proxy = await findSetting<string | string[]>("PROXY", true);
  if (proxy?.value == null) {
    return undefined;
  }

  if (Array.isArray(proxy.value) && proxy.value.length > 0) {
    return proxy.value;
  }
  if (typeof proxy.value === "string" && proxy.value.trim()) {
    return [proxy.value];
  }
  return undefined;
}

/**
 * Checks if a URL is absolute (has protocol)
 */
function isAbsoluteUrl(url: string): boolean {
  try {
    new URL(url);
    return true;
  } catch {
    return false;
  }
}

/**
 * Resolves a relative URL against a base URL
 */
export function normalizeUrl(url: string, baseUrl?: string): string {
  // If URL is already absolute, return as-is
  if (isAbsoluteUrl(url)) {
    return url;
  }

  // If URL is relative and we have a base URL, resolve it
  if (baseUrl) {
    return resolveAbsoluteUrl(baseUrl, url);
  }

  // If URL is relative but no base URL provided, log warning and return as-is
  // (Puppeteer might handle it, but it's not ideal)
  logger.warn(`Relative URL "${url}" provided without baseUrl. Attempting to fetch as-is.`);
  return url;
}

export interface FetchBrowserPageOptions {
  /** The URL to fetch. May be relative when baseUrl is provided. */
  url: string;
  /** When true, bypass the configured proxy for this request. */
  skipProxy?: boolean;
  /** Seconds to wait after page load for scripts to complete before capturing content. */
  pageLoadWaitTime?: number;
  /** Base URL used to resolve relative URLs. */
  baseUrl?: string;

  /**
   * When true, it will attempt connections without proxy first and then rotate through the proxies. 
   * Unless specifically set to false, it will default to true.
  */
  rotateProxies?: boolean;
}

export async function fetchBrowserPage(options: FetchBrowserPageOptions) {
  const { url, skipProxy, baseUrl } = options;

  // Normalize relative URLs against the base URL
  const normalizedUrl = normalizeUrl(url, baseUrl);
  const proxyUrls = skipProxy ? undefined : await findProxies();

  if (!skipProxy && proxyUrls) {
    return await fetchBrowserPageWithProxies({
      rotateProxies: true,
      ...options,
      url: normalizedUrl,
    }, proxyUrls);
  }
  
  const cluster = await getCluster(proxyUrls?.[0]);
  const result = await cluster.execute({ ...options, url: normalizedUrl });
  if (result?.status > 399) {
    throw new BrowserFetchError(result);
  }
  return result;
}

export async function fetchBrowserPageWithProxies(options: FetchBrowserPageOptions, proxies: string[]): Promise<BrowserTaskResult> {
  const { url, rotateProxies } = options;

  let proxyList = [];
  if (rotateProxies) {
    proxyList = Array.isArray(proxies) && proxies.length > 0
      ? [undefined, ...proxies]
      : [undefined];
  } else {
    proxyList = proxies;
  }

  let result: BrowserTaskResult | undefined;
  let proxiesAttempted = 0;
  let lastError: unknown;
  for (const proxy of proxyList) {
    try {
      proxiesAttempted += proxy ? 1 : 0;

      const cluster = await getCluster(proxy);
      result = await cluster.execute(options);

      if (result && result.status < 399) {
        break;
      }

      if (!result || result.status > 399) {
        throw new BrowserFetchError(result);
      }
    } catch (error) {
      if (isProxyError(error as Error | BrowserFetchError | string)) {
        logger.error(`Error fetching page ${proxy ? `with proxy ${proxy}` : 'without proxy'}. Continuing with next proxy.`);
        logger.error(error + "\n" + (error as Error)?.stack);
        lastError = error;
        continue;
      } else {
        throw error;
      }
    }
  }

  if (result && result.status > 399) {
    throw new BrowserFetchError(result);
  }

  if (!result) {
    logger.error(lastError + "\n" + (lastError as Error)?.stack);
    throw new Error(`Failed to fetch page ${url} with any proxy after ${proxiesAttempted} proxies attempted. Last error: ${lastError}`);
    
  }

  return result;
}

export async function fetchPreview(url: string) {
  let { content, screenshot } = await fetchBrowserPage({ url });
  const $ = cheerio.load(content);
  const title = $("title").text() || $('meta[name="og:title"]').attr("content");
  const description = $('meta[name="og:description"]').attr("content");
  let thumbnailUrl = screenshot
    ? `data:image/webp;base64,${screenshot}`
    : $('meta[name="og:image"]').attr("content") ||
      $("img").first().attr("src");
  thumbnailUrl = thumbnailUrl
    ? resolveAbsoluteUrl(url, thumbnailUrl)
    : undefined;
  const simplifiedContent = await simplifiedMarkdown(content);
  const catalogueType = await detectCatalogueType({
    url,
    content: simplifiedContent,
    screenshot,
  });

  return { title, thumbnailUrl, description, catalogueType };
}

export async function simplifyHtml(html: string, contentSelector?: string) {
  const $ = cheerio.load(html);
  const root = contentSelector?.trim() ? $(contentSelector).first() : null;
  (root ?? $("html")).find("head").empty();
  const elms = root?.length
    ? root.find("*").addBack().toArray()
    : $("*").toArray();
  for (const elm of elms) {
    const $elm = $(elm);
    if (elm.type !== "tag" && elm.type !== "text") {
      $elm.remove();
      continue;
    }
    if (elm.type !== "tag") {
      continue;
    }
    if (elm.tagName == "link") {
      $elm.remove();
      continue;
    }
    if (["footer"].includes(elm.tagName)) {
      $elm.remove();
      continue;
    }
    if (elm.tagName === "iframe" && elm.children.length === 0) {
      $elm.remove();
      continue;
    }
    // CourseDog: convert buttons to links
    if (elm.tagName === "button" && $elm.attr("number")) {
      const pageNum = $elm.attr("number");
      if (pageNum !== "...") {
        const newLink = $("<a>")
          .attr("href", `/courses?page=${pageNum}`)
          .text($elm.text().trim());
        $elm.replaceWith(newLink);
      } else {
        $elm.remove();
      }
      continue;
    }
    for (var attribute in elm.attribs) {
      if (attribute == "href") {
        continue;
      }
      $elm.removeAttr(attribute);
    }
    if (elm.tagName !== "div") {
      continue;
    }
    let childElementCount = 0;
    let childTextFound = false;
    let divChildFound = false;
    for (const child of elm.children) {
      if (child.type === "text" && child.data.trim()) {
        childTextFound = true;
      } else if (child.type === "tag") {
        childElementCount++;
        if (childElementCount > 1) {
          break;
        }
        if (child.tagName === "div") {
          divChildFound = true;
        }
      }
    }
    if (!childTextFound && !childElementCount) {
      $elm.remove();
      continue;
    }
    if (childTextFound || childElementCount > 1 || !divChildFound) {
      continue;
    }
    // Remove redundant divs
    $elm.replaceWith($elm.children());
  }
  return root?.length ? $.html(root) : $.html();
}

export async function toMarkdown(html: string) {
  return new TurndownService({
    linkReferenceStyle: "full"
  }).turndown(html);
}

export async function simplifiedMarkdown(html: string, contentSelector?: string) {
  const simplified = await toMarkdown(await simplifyHtml(html, contentSelector));
  return simplified as SimplifiedMarkdown;
}
