import { addExtra, VanillaPuppeteer } from "puppeteer-extra";
import StealthPlugin from "puppeteer-extra-plugin-stealth";
import rebrowserPuppeteer, { ElementHandle, KnownDevices } from "rebrowser-puppeteer";
import { BrowserFetchError, findProxies } from "./browser";
import getLogger from "../logging";
import { readFileSync } from "fs";
import { isProxyError } from "../utils";

const logger = getLogger("extraction.dynamicLinkDiscovery");
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

export interface DiscoverDynamicLinksOptions {
  /** Root URL to navigate to and discover links from. */
  rootUrl: string;
  /** CSS selector for the container of clickable elements. Defaults to "body" when omitted. */
  selector?: string;
  /** Options for the click discovery process (limit, wait timeout). */
  clickOptions?: ClickDiscoveryOptions;
}

type Browser = Awaited<ReturnType<typeof puppeteer.launch>>;
type Page = Awaited<ReturnType<Browser["newPage"]>>;
type NavigateWithProxyResult = { page: Page; browser: Browser };

const DOM_SETTLE_MS = 300;
const BLOCKED_STATUS_CODES = [403, 429];

class ProxyBlockedError extends Error {
  readonly status: number;
  readonly blockedUrl: string;

  constructor(status: number, url: string) {
    super(`Request blocked with HTTP ${status} for ${url}`);
    this.status = status;
    this.blockedUrl = url;
  }
}

async function scrollAndSettle(page: Page, timeoutMs: number) {
  await page.waitForNetworkIdle({ idleTime: 1000, timeout: timeoutMs }).catch(() => {});
  await page.evaluate(() => {
    // @ts-ignore
    window.scrollTo(0, window.document.body.scrollHeight);
  });
  await page.waitForNetworkIdle({ idleTime: 1000, timeout: timeoutMs }).catch(() => {});
  // Allow the DOM to finish rendering after lazy-loaded content arrives
  await new Promise(r => setTimeout(r, DOM_SETTLE_MS));
}

interface NavigateWithProxyOptions {
  loadCompletedCallback?: (page: Page) => Promise<void>;
  /** Called after the page is created but before navigation starts. Use to attach listeners early. */
  beforeNavigation?: (page: Page) => void | Promise<void>;
}

export async function navigateWithProxy(
  url: string,
  proxyUrl?: string,
  options?: NavigateWithProxyOptions | ((page: Page) => Promise<void>)
): Promise<NavigateWithProxyResult> {
  const opts: NavigateWithProxyOptions =
    typeof options === 'function' ? { loadCompletedCallback: options } : (options ?? {});

  const args = [
    proxyUrl ? `--proxy-server=${new URL(proxyUrl).origin}` : "",
    "--ignore-certificate-errors",
    "--allow-insecure-localhost",
    '--no-sandbox', 
    '--disable-setuid-sandbox'
  ].filter(Boolean);

  const browser = await puppeteer.launch({
    ignoreHTTPSErrors: true,
    headless: process.env.SHOW_CHROME ? false : 'shell',
    protocolTimeout: 1 * 60 * 1000,
    dumpio: true,
    args,
  });

  let settlementTimer: ReturnType<typeof setTimeout> | undefined;

  try {
    const pageSettlementTimeout = new Promise<void>((_, reject) => {
      settlementTimer = setTimeout(() => {
        reject(new Error('Waiting for page handler timed out after 1 minute.'));
      }, 1 * 60 * 1000);
    });

    const page = (await browser.pages()).length > 0 ? (await browser.pages())[0] : await browser.newPage();

    if (proxyUrl) {
      const parsed = new URL(proxyUrl);
      if (parsed.username || parsed.password) {
        await page.authenticate({
          username: parsed.username,
          password: parsed.password,
        });
      }
    }

    if (opts.beforeNavigation) {
      await opts.beforeNavigation(page);
    }

    // Decreases bot detection scores
    await page.emulate(KnownDevices["iPad Pro 11 landscape"]);

    await page.goto(url, { timeout: 30 * 60 * 1000 });

    await Promise.race([
      opts.loadCompletedCallback ? opts.loadCompletedCallback(page) : Promise.resolve(),
      pageSettlementTimeout,
    ]);

    return { page, browser };
  } catch (error) {
    await browser.close().catch(() => {});
    throw error;
  } finally {
    if (settlementTimer) clearTimeout(settlementTimer);
  }
}

/**
 * Using the given rootUrl and the selector, we look for all elements
 * that look clickable and we collect their selectors. We then click
 * on each and wait for the page URL to change. If the URL changes
 * to a different page (via classic web navigation or SPA style pushState)
 * we record the new URL. We then go back to the root URL and repeat the process.
 *
 * Rotates through available proxies when the server responds with a
 * blocked status (403 / 429) or a proxy-level error.
 *
 * @param options - Configuration for dynamic link discovery
 * @param options.rootUrl - Root URL to navigate to and discover links from
 * @param options.selector - CSS selector for the container of clickable elements (defaults to "body")
 * @param options.clickOptions - Options for the click discovery process (limit, wait timeout)
 */
export async function discoverDynamicLinks(
  options: DiscoverDynamicLinksOptions
): Promise<string[]> {
  const proxyUrls = await findProxies();
  const proxiesToTry: Array<string | undefined> = [undefined, ...(proxyUrls ?? [])];
  let lastError: unknown;

  for (let idx = 0; idx < proxiesToTry.length; idx++) {
    const proxyUrl = proxiesToTry[idx];
    try {
      return await runDiscoveryWithProxy(options, proxyUrl);
    } catch (error) {
      const retriable =
        error instanceof ProxyBlockedError ||
        isProxyError(error as Error | BrowserFetchError | string) ||
        (error as Error)?.message?.includes('Waiting for page handler timed out');

      if (retriable) {
        const hasMore = idx < proxiesToTry.length - 1;
        logger.error(
          `Attempt ${idx + 1} failed: ${error}. ` +
          (hasMore ? `Rotating to next proxy.` : `No more proxies to try.`)
        );
        lastError = error;
        continue;
      }

      throw error;
    }
  }

  throw new Error(`Failed to discover dynamic links after ${proxiesToTry.length} attempts. Last error: ${lastError}`);
}

interface PageListenerState {
  blockedError: ProxyBlockedError | null;
  urls: string[];
}

function attachPageListeners(page: Page, rootOrigin: string, state: PageListenerState) {
  page.on('response', (response) => {
    if (state.blockedError) return;
    if (!BLOCKED_STATUS_CODES.includes(response.status())) return;
    try {
      if (new URL(response.url()).origin === rootOrigin) {
        state.blockedError = new ProxyBlockedError(response.status(), response.url());
        logger.error(`Blocked: HTTP ${response.status()} response from ${response.url()}`);
      }
    } catch { /* invalid URL, ignore */ }
  });

  page.on('requestfailed', (request) => {
    if (state.blockedError) return;
    const response = request.response();
    const status = response?.status();
    if (status && BLOCKED_STATUS_CODES.includes(status)) {
      try {
        if (new URL(request.url()).origin === rootOrigin) {
          state.blockedError = new ProxyBlockedError(status, request.url());
          logger.error(`Blocked: HTTP ${status} on failed request ${request.url()}`);
        }
      } catch { /* invalid URL, ignore */ }
    }
    const reason = request.failure()?.errorText ?? 'unknown';
    console.error(`Request failed: ${request.url()} (${reason})`);
  });
}

function attachRequestInterception(page: Page, state: PageListenerState) {
  page.on('request', (request) => {
    if (request.isNavigationRequest()) {
      state.urls.push(request.url());
      request.abort();
    } else {
      request.continue();
    }
  });
}

async function runDiscoveryWithProxy(
  options: DiscoverDynamicLinksOptions,
  proxyUrl?: string
): Promise<string[]> {
  const { rootUrl, selector, clickOptions = {} } = options;
  const pageMaxWaitMs = Number.isFinite(clickOptions.waitMs) && clickOptions.waitMs! > 0
    ? clickOptions.waitMs!
    : 30 * 1000;
  let browser: Browser | undefined;
  let page: Page;

  const rootOrigin = new URL(rootUrl).origin;
  const state: PageListenerState = { blockedError: null, urls: [] };

  try {
    const navResult = await navigateWithProxy(rootUrl, proxyUrl, {
      beforeNavigation: (p) => attachPageListeners(p, rootOrigin, state),
      loadCompletedCallback: async (webpage) => {
        if (state.blockedError) throw state.blockedError;
        await webpage.waitForNetworkIdle({ idleTime: 1000, timeout: pageMaxWaitMs });
        if (selector) {
          await webpage.waitForSelector(selector, { timeout: pageMaxWaitMs });
        }
      },
    });
    page = navResult.page;
    browser = navResult.browser;

    if (state.blockedError) throw state.blockedError;

    await page.setRequestInterception(true);
    attachRequestInterception(page, state);

    await page.waitForNetworkIdle({ idleTime: 1000, timeout: pageMaxWaitMs });
    if (selector) {
      await page.waitForSelector(selector, { timeout: pageMaxWaitMs });
    }

    if (state.blockedError) throw state.blockedError;

    await scrollAndSettle(page, pageMaxWaitMs);

    const clickables = await findClickables(page, selector);
    const uniqueIds = new Set<string>(clickables.map(c => c.selector));
    if (uniqueIds.size !== clickables.length) {
      throw new Error('Duplicate clickable selectors found');
    }

    const clickLimit = clickOptions.limit;
    const clickablesCount = clickables.length;

    if (Number.isFinite(clickLimit) && clickablesCount > clickLimit!) {
      throw new Error(`Total clickable elements found (${clickablesCount}) exceeds the limit of ${clickLimit}`);
    }

    const clickableSelectors = clickables.map(c => c.selector);

    for (let i = 0; i < clickableSelectors.length; i++) {
      if (state.blockedError) throw state.blockedError;

      const selectorId = clickableSelectors[i];

      const escapedId = selectorId.replace(/"/g, '\\"');
      const elements = await page.$$(`[data-xtra-clickable-id="${escapedId}"]`).catch((error) => {
        logger.error(`Error finding clickable element ${selectorId}: ${error}`);
        return [];
      });
      const freshHandle = elements[0] as unknown as ElementHandle<Element> | undefined;
      if (!freshHandle) {
        const fallback = await page.$$(selectorId).catch(() => []);
        if (!fallback[0]) {
          console.error(`Element '${selectorId}' could not be re-resolved, skipping`);
          continue;
        }
      }

      const clickable: Clickable = {
        handle: freshHandle ?? (await page.$$(selectorId))[0] as unknown as ElementHandle<Element>,
        selector: selectorId,
      };

      const url = await captureClickableUrl(page, clickable);
      if (url) {
        state.urls.push(url);
      }

      if (state.blockedError) throw state.blockedError;

      let currentUrl = page.url();
      if (currentUrl !== rootUrl) {
        await page.goBack({ waitUntil: "networkidle0", timeout: pageMaxWaitMs }).catch(async () => {
          await page.goto(rootUrl, { waitUntil: "networkidle0", timeout: pageMaxWaitMs });
        });
        await page.waitForNetworkIdle({ idleTime: 500, timeout: pageMaxWaitMs }).catch(() => {});

        if (selector) {
          try {
            await page.waitForSelector(selector, { timeout: pageMaxWaitMs });
          } catch (error) {
            await page.screenshot({ path: `/tmp/screenshot-${Date.now()}.webp` });
            throw error;
          }
        }

        if (state.blockedError) throw state.blockedError;

        currentUrl = page.url();
        if (currentUrl !== rootUrl) {
          await browser?.close();
          const navResult = await navigateWithProxy(rootUrl, proxyUrl, {
            beforeNavigation: (p) => attachPageListeners(p, rootOrigin, state),
          });
          page = navResult.page;
          browser = navResult.browser;

          if (state.blockedError) throw state.blockedError;

          await page.setRequestInterception(true);
          attachRequestInterception(page, state);

          await page.waitForNetworkIdle({ idleTime: 1000, timeout: pageMaxWaitMs });
          if (selector) {
            await page.waitForSelector(selector, { timeout: pageMaxWaitMs });
          }
          await scrollAndSettle(page, pageMaxWaitMs);
        }

        await findClickables(page, selector);
      }
    }

    return Array.from(new Set(state.urls));
  } catch (error) {
    if (error instanceof ProxyBlockedError) throw error;
    logger.error(`Error during discovery: ${error}`);
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
async function waitForUrlChange(page: Page, oldUrl: string, timeout = 15000, pollInterval = 100): Promise<string | null> {
  const waitForUrlChangeScript = readFileSync("./src/extraction/scripts/waitForUrlChange.js", "utf8");
  await page.evaluate(waitForUrlChangeScript);
  return await page.evaluate( // @ts-ignore
    obj => window.__xtra__waitForUrlChangeScript(obj),
    { oldUrl, timeout, pollInterval }
  ) as Awaited<string | null>;
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

async function clickAndWaitForUrl(page: Page, element: ElementHandle<Element>, oldUrl: string): Promise<string | null> {
  let navigationUrl: string | null = null;

  // Race: classic navigation (caught by waitForNavigation) vs SPA pushState (caught by polling)
  try {
    const [navResponse] = await Promise.all([
      page.waitForNavigation({ waitUntil: "networkidle0", timeout: 5000 }).catch(() => null),
      element.click(),
    ]);

    if (navResponse) {
      const newUrl = page.url();
      if (newUrl !== oldUrl) return newUrl;
    }
  } catch {
    // click may throw if element is removed mid-navigation; fall through to URL check
  }

  // Give SPAs time to settle after the click
  await page.waitForNetworkIdle({ idleTime: 500, timeout: 10_000 }).catch(() => {});
  navigationUrl = await waitForUrlChange(page, oldUrl, 5000);

  return navigationUrl;
}

async function resolveClickableElement(page: Page, clickable: Clickable): Promise<ElementHandle<Element> | null> {
  try {
    const isAttached = await clickable.handle.evaluate(() => true).catch(() => false);
    if (isAttached) return clickable.handle;
  } catch { /* detached */ }

  const elements = await page.$$(clickable.selector);
  return (elements[0] as unknown as ElementHandle<Element>) ?? null;
}

async function captureClickableUrl(page: Page, clickable: Clickable) {
  const oldUrl = page.url();
  try {
    let element = await resolveClickableElement(page, clickable);
    if (!element) {
      console.error(`Element '${clickable.selector}' not found, skipping`);
      return null;
    }

    let url = await clickAndWaitForUrl(page, element, oldUrl);
    if (url) return url;

    // Retry once: re-resolve in case the first click caused a partial DOM update
    element = await resolveClickableElement(page, clickable);
    if (!element) {
      console.error(`Element '${clickable.selector}' not found on retry, skipping`);
      return null;
    }

    url = await clickAndWaitForUrl(page, element, oldUrl);
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