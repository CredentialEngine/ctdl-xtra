import { addExtra, VanillaPuppeteer } from "puppeteer-extra";
import StealthPlugin from "puppeteer-extra-plugin-stealth";
import rebrowserPuppeteer, { ElementHandle } from "rebrowser-puppeteer";
import { findProxy } from "./browser";
import getLogger from "../logging";
import { readFileSync } from "fs";

const puppeteer = addExtra(rebrowserPuppeteer as unknown as VanillaPuppeteer);
puppeteer.use(StealthPlugin());

type Clickable = {
  handle: ElementHandle<Element>;
  selector: string;
};

export interface ClickDiscoveryOptions {
  limit?: number;
  waitMs?: number;
}

type Browser = Awaited<ReturnType<typeof puppeteer.launch>>;
type Page = Awaited<ReturnType<Browser["newPage"]>>;
type NavigateWithProxyResult = { page: Page; browser: Browser };

export async function navigateWithProxy(
  url: string
): Promise<NavigateWithProxyResult> {
  const proxyUrl = await findProxy();
  const args = [
    proxyUrl ? `--proxy-server=${new URL(proxyUrl).origin}` : "",
    "--ignore-certificate-errors",
    "--allow-insecure-localhost",
  ].filter(Boolean);

  const browser = await puppeteer.launch({
    ignoreHTTPSErrors: true,
    args,
  });

  const page = await browser.newPage();
  if (proxyUrl) {
    const parsed = new URL(proxyUrl);
    if (parsed.username || parsed.password) {
      await page.authenticate({
        username: parsed.username,
        password: parsed.password,
      });
    }
  }

  await page.goto(url);

  return { page, browser };
}

/**
 * Using the given rootUrl and the selector, we look for all elements
 * that look clickable and we collect their selectors. We then click 
 * on each and wait for the page URL to change. If the URL changes
 * to a different page (via classic web navigation or SPA style pushState)
 * we record the new URL. We then go back to the root URL and repeat the process.
 * 
 * TODO: This can be a slow process especially if the page has a lot of links
 * and is slow. Performance can be improved by parallelizing the clicks via
 * multiple tabs or browser instances.
 */
export async function discoverDynamicLinks(
  rootUrl: string,
  selector?: string,
  opts: ClickDiscoveryOptions = {}
): Promise<string[]> {
  const pageMaxWaitMs = opts?.waitMs ?? 30 * 1000; // 30 seconds
  const logger = getLogger("extraction.dynamicLinkDiscovery");
  const urls: string[] = [];
  let browser: Browser | undefined;
  let page: Page;

  try {
    const navResult = await navigateWithProxy(rootUrl);
    page = navResult.page;
    browser = navResult.browser;

    await page.setRequestInterception(true);

    page.on('request', (request) => {
      if (request.isNavigationRequest()) {
        urls.push(request.url());
        request.abort();
      } else {
        request.continue();
      }
    });

    await page.waitForNetworkIdle({ idleTime: 1000, timeout: pageMaxWaitMs });
    if (selector) {
      await page.waitForSelector(selector, { timeout: pageMaxWaitMs });
    }
    await page.waitForNetworkIdle({ idleTime: 1000, timeout: pageMaxWaitMs });
    await page.evaluate(() => {
      // @ts-ignore
      window.scrollTo(0, window.document.body.scrollHeight);
    });

    const clickables = await findClickables(page, selector);
    const uniqueIds = new Set<string>(clickables.map(c => c.selector));
    if (uniqueIds.size !== clickables.length) {
      throw new Error('Duplicate clickable selectors found');
    }

    // Apply click limit if specified
    const clickLimit = opts?.limit;
    const clickablesCount = clickables.length;
    
    if (Number.isFinite(clickLimit) && clickablesCount > clickLimit!) {
      throw new Error(`Total clickable elements found (${clickablesCount}) exceeds the limit of ${clickLimit}`);
    }

    const capturedUrls: string[] = [];
    for (const clickable of clickables) {
      const url = await captureClickableUrl(page, clickable);
      if (url) {
        urls.push(url);
      }

      let currentUrl = await page.url();
      if (currentUrl !== rootUrl) {
        await page.goBack();
        await page.waitForSelector(selector!, { timeout: pageMaxWaitMs });
        await page.waitForNetworkIdle({ idleTime: 1000, timeout: pageMaxWaitMs });

        currentUrl = await page.url();
        if (currentUrl !== rootUrl) {
          await browser?.close();
          const navResult = await navigateWithProxy(rootUrl);
          page = navResult.page;
          browser = navResult.browser;
          
          await page.waitForNetworkIdle({ idleTime: 1000, timeout: pageMaxWaitMs });
          
          await page.waitForSelector(selector!, { timeout: pageMaxWaitMs });
          
          await page.waitForNetworkIdle({ idleTime: 1000, timeout: pageMaxWaitMs });
          await page.evaluate(() => {
            // @ts-ignore
            window.scrollTo(0, window.document.body.scrollHeight);
          });
        }
      }
    }
    
    urls.push(...capturedUrls);
    return Array.from(new Set(urls));
  } catch (error) {
    logger.error(`Error clicking link: ${error}`);
    throw error;
  } finally {
    await browser?.close();
  }
}

/**
 * Waits until the page URL changes from the given current URL.
 * Works for SPAs (pushState, hash changes) or normal navigation.
 * @param {Page} page - Puppeteer page instance
 * @param {string} oldUrl - URL to compare against
 * @param {number} timeout - max wait time in ms
 */
async function waitForUrlChange(page: Page, oldUrl: string, timeout = 15000, pollInterval = 100): Promise<string> {
  const waitForUrlChangeScript = readFileSync("./src/extraction/scripts/waitForUrlChange.js", "utf8");
  await page.evaluate(waitForUrlChangeScript);
  return await page.evaluate( // @ts-ignore
    obj => window.__xtra__waitForUrlChangeScript(obj),
    { oldUrl, timeout, pollInterval }
  ) as Awaited<string>;
}


async function findClickables(page: Page, selector: string = "body"): Promise<Clickable[]> {
  const [root] = await page.$$(selector);
  if (!root) {
    throw new Error(`No element found for selector: ${selector}`);
  }

  const findClickablesScript = readFileSync("./src/extraction/scripts/findClickables.js", "utf8");
  await root.evaluate(findClickablesScript); // @ts-ignore
  await root.evaluate(el => window.__xtra__findClickablesScript(el));

  const clickables = await Promise.all((await page.$$('[data-xtra-clickable]')).map(async el => {
    return {
      handle: el, // @ts-ignore
      selector: await el.evaluate((el) => el.getAttribute('data-xtra-clickable-id')) as string,
    };
  }));

  // @ts-ignore
  return clickables;
}

async function captureClickableUrl(page: Page, clickable: Clickable) {
  const oldUrl = await page.url();
  try {
    let element = clickable.handle;
    let error: unknown;
    let url: string | null = null;
    try {
      await element.click();
      url = await waitForUrlChange(page, oldUrl);
    } catch (e) {
      error = e;
    }

    if (isDetachedError(error)) {
      const elements = await page.$$(clickable.selector);
      if (elements.length > 0) {
        element = elements[0] as unknown as ElementHandle<Element>;
      }
    }

    if (url) {
      return url;
    }

    if (element) {
      await element.click();
      url = await waitForUrlChange(page, oldUrl);
    } else {
      throw new Error(`Element '${clickable.selector}' not found`);
    }

    return url;
  } catch (error) {
    if ((error as Error)?.message?.startsWith('Node is either not clickable')) {
      console.error(`Element '${clickable.selector}' is not clickable`);
      return null;
    }
    
    console.error(`Error capturing clickable URL: ${error}`);
    throw error;
  }
}

const isDetachedError = (error: unknown): error is Error => {
  return (error as Error)?.message?.startsWith('Node is detached');
};