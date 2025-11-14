import * as cheerio from "cheerio";
import { Cluster } from "puppeteer-cluster";
import { addExtra, VanillaPuppeteer } from "puppeteer-extra";
import StealthPlugin from "puppeteer-extra-plugin-stealth";
import rebrowserPuppeteer from "rebrowser-puppeteer";
import TurndownService from "turndown";
import { URL } from "url";
import { findSetting } from "../data/settings";
import getLogger from "../logging";
import { SimplifiedMarkdown } from "../types";
import { httpCodeToMessage, resolveAbsoluteUrl } from "../utils";
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
let clusterClosed = false;

const PAGE_TIMEOUT = 5 * 60 * 1000;

const logger = getLogger("extraction.browser");

export async function getCluster(proxyUrl?: string) {
  if (clusterClosed) {
    throw new Error("Cluster has been closed");
  }
  if (cluster) {
    return cluster;
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

  cluster = await Cluster.launch({
    concurrency: Cluster.CONCURRENCY_CONTEXT,
    maxConcurrency: 2,
    puppeteer: puppeteer,
    puppeteerOptions: {
      ignoreHTTPSErrors: true,
      args: [
        "--font-render-hinting=none",
        "--force-gpu-mem-available-mb=4096",
        "--ignore-certificate-errors",
        proxyBaseUrl ? `--proxy-server=${proxyBaseUrl}` : "",
      ].filter(Boolean),
    },
    timeout: PAGE_TIMEOUT,
  });

  await cluster.task(async ({ page, data }) => {
    if (proxyUsername || proxyPassword) {
      await page.authenticate({
        username: proxyUsername || "",
        password: proxyPassword || "",
      });
    }

    page.setDefaultTimeout(PAGE_TIMEOUT);
    const { url, pageLoadWaitTime } = data;
    const response = await page.goto(url, {
      timeout: PAGE_TIMEOUT,
      waitUntil: "networkidle2",
    });
    if (!response) {
      throw new Error(`Failed to load page ${url}`);
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

export async function findProxy(): Promise<string | undefined> {
  const proxyEnabled = await findSetting<boolean>("PROXY_ENABLED");
  if (!proxyEnabled?.value) {
    return undefined;
  }
  const proxy = await findSetting<string>("PROXY", true);
  return proxy?.value || process.env.PROXY_URL;
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
function normalizeUrl(url: string, baseUrl?: string): string {
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

export async function fetchBrowserPage(
  url: string,
  skipProxy?: boolean,
  pageLoadWaitTime?: number,
  baseUrl?: string
) {
  // Normalize relative URLs against the base URL
  const normalizedUrl = normalizeUrl(url, baseUrl);
  
  const proxyUrl = skipProxy ? undefined : await findProxy();
  const cluster = await getCluster(proxyUrl);
  const result = await cluster.execute({ url: normalizedUrl, pageLoadWaitTime });
  if (result?.status > 399) {
    throw new BrowserFetchError(result);
  }
  return result;
}

export async function fetchPreview(url: string) {
  let { content, screenshot } = await fetchBrowserPage(url);
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

export async function simplifyHtml(html: string) {
  const $ = cheerio.load(html);
  $("head").empty();
  const elms = $("*").toArray();
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
  return $.html();
}

export async function toMarkdown(html: string) {
  return new TurndownService({
    linkReferenceStyle: "full"
  }).turndown(html);
}

export async function simplifiedMarkdown(html: string) {
  const simplified = await toMarkdown(await simplifyHtml(html));
  return simplified as SimplifiedMarkdown;
}
