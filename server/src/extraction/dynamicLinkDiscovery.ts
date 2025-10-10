import { addExtra, VanillaPuppeteer } from "puppeteer-extra";
import StealthPlugin from "puppeteer-extra-plugin-stealth";
import rebrowserPuppeteer from "rebrowser-puppeteer";
import { findProxy } from "./browser";
import getLogger from "../logging";

const puppeteer = addExtra(rebrowserPuppeteer as unknown as VanillaPuppeteer);
puppeteer.use(StealthPlugin());

export interface ClickDiscoveryOptions {
  limit?: number;
  waitMs?: number;
}

export async function discoverDynamicLinks(
  url: string,
  selector: string,
  opts: ClickDiscoveryOptions = {}
): Promise<string[]> {
  const logger = getLogger("extraction.dynamicLinkDiscovery");
  const proxyUrl = await findProxy();
  const args = [proxyUrl ? `--proxy-server=${new URL(proxyUrl).origin}` : ""].filter(Boolean);

  const browser = await puppeteer.launch({
    ignoreHTTPSErrors: true,
    args,
  });
  try {
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

    await page.goto(url, { waitUntil: "networkidle2" });

    // Count elements first to cap iterations
    const elementCount = await page.$$eval(selector, (els) => els.length);
    const max = Math.min(elementCount, opts.limit ?? elementCount);
    const discovered = new Set<string>();
    const originalUrl = page.url();

    for (let i = 0; i < max; i++) {
      // Reload original page to reset state before each click
      if (page.url() !== originalUrl) {
        await page.goto(originalUrl, { waitUntil: "networkidle2" });
      }

      // Get fresh handles each iteration
      const handles = await page.$$(selector);
      const handle = handles[i];
      if (!handle) {
        continue;
      }

      await handle.evaluate((el) => (el as any)?.scrollIntoView?.({ block: "center" }));

      const beforeUrl = page.url();

      // Watch for new tab/window
      const targetPromise = page
        .browserContext()
        .waitForTarget((t) => t.opener() === page.target(), { timeout: 3000 })
        .catch(() => null);

      // Click and race between same-tab URL change and new target
      await Promise.race([
        (async () => {
          await handle.click({ delay: 20 });
          await page.waitForFunction(
            'document.location.href !== arguments[0]',
            { timeout: 10000 },
            beforeUrl
          );
          discovered.add(page.url());
        })(),
        (async () => {
          const newTarget = await targetPromise;
          if (!newTarget) return;
          const newPage = await newTarget.page();
          if (!newPage) return;
          await newPage.bringToFront();
          try {
            await newPage.waitForNavigation({ waitUntil: "load", timeout: 10000 });
          } catch (_) {}
          discovered.add(newTarget.url());
          await newPage.close();
        })(),
      ]);

      if (opts.waitMs) {
        await new Promise((r) => setTimeout(r, opts.waitMs));
      }
    }

    logger.info(`Discovered ${discovered.size} dynamic URLs using selector ${selector}`);
    return Array.from(discovered);
  } finally {
    await browser.close();
  }
}


