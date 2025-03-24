import * as cheerio from "cheerio";
import { Cluster } from "puppeteer-cluster";
import TurndownService from "turndown";
import { SimplifiedMarkdown } from "../types";
import { resolveAbsoluteUrl } from "../utils";
import { detectCatalogueType } from "./llm/detectCatalogueType";

import { addExtra, VanillaPuppeteer } from "puppeteer-extra";
import StealthPlugin from "puppeteer-extra-plugin-stealth";
import rebrowserPuppeteer from "rebrowser-puppeteer";

export interface BrowserTaskInput {
  url: string;
}

export interface BrowserTaskResult {
  url: string;
  content: string;
  screenshot: string;
  status: number;
}

const puppeteer = addExtra(rebrowserPuppeteer as unknown as VanillaPuppeteer);
puppeteer.use(StealthPlugin());

let cluster: Cluster<BrowserTaskInput, BrowserTaskResult> | undefined;
let clusterClosed = false;

const PAGE_TIMEOUT = 5 * 60 * 1000;

export async function getCluster() {
  if (clusterClosed) {
    throw new Error("Cluster has been closed");
  }
  if (cluster) {
    return cluster;
  }
  cluster = await Cluster.launch({
    concurrency: Cluster.CONCURRENCY_CONTEXT,
    maxConcurrency: 2,
    puppeteer: puppeteer,
    puppeteerOptions: {
      args: ["--font-render-hinting=none", "--force-gpu-mem-available-mb=4096"],
    },
    timeout: PAGE_TIMEOUT,
  });
  await cluster.task(async ({ page, data }) => {
    page.setDefaultTimeout(PAGE_TIMEOUT);
    const { url } = data;
    const response = await page.goto(url, {
      timeout: PAGE_TIMEOUT,
      waitUntil: "networkidle2",
    });
    if (!response) {
      throw new Error(`Failed to load page ${url}`);
    }
    let content = await page.content();
    if (content.includes("kuali-catalog")) {
      console.log(`Kuali detected at url ${url}; waiting for selector`);
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

export async function fetchBrowserPage(url: string) {
  const cluster = await getCluster();
  return cluster.execute({ url });
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
    if (["header", "footer"].includes(elm.tagName)) {
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
  return new TurndownService().turndown(html);
}

export async function simplifiedMarkdown(html: string) {
  const simplified = await toMarkdown(await simplifyHtml(html));
  return simplified as SimplifiedMarkdown;
}
