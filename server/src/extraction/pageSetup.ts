import { PageSetupConfig, PageSetupStep } from "../../../common/types";

/**
 * Minimal page surface for running setup steps (Puppeteer Page or compatible).
 */
export type PageSetupPage = {
  waitForSelector(selector: string, options?: { timeout?: number }): Promise<unknown>;
  click(selector: string, options?: { delay?: number }): Promise<void>;
};

/** Per–step-type handlers keyed by `PageSetupStep["type"]` for static correlation. */
export type PageSetupStepHandlers = {
  [K in PageSetupStep["type"]]: (
    page: PageSetupPage,
    step: Extract<PageSetupStep, { type: K }>
  ) => Promise<void>;
};

const Steps = {
  click: async (page, step) => {
    const selector = step.selector?.trim();
    if (!selector) {
      throw new Error(
        `Click step selector is empty/falsey. Please check the recipe configuration.`
      );
    }
    await page.waitForSelector(selector);
    await page.click(selector);
  },
  wait: async (_page, step) => {
    const sec = step.seconds;
    if (!Number.isFinite(sec) || sec <= 0) {
      throw new Error(
        `Wait step seconds is invalid/falsey. Please check the recipe configuration.`
      );
    }
    await new Promise((r) => setTimeout(r, sec * 1000));
  },
} satisfies PageSetupStepHandlers;

async function runPageSetupStep(page: PageSetupPage, step: PageSetupStep): Promise<void> {
  switch (step.type) {
    case "click":
      await Steps.click(page, step);
      return;
    case "wait":
      await Steps.wait(page, step);
      return;
    default: {
      const unhandledStep = (step as unknown as { type: string })?.type;
      throw new Error(`Unknown step type: ${String(unhandledStep)}`);
    }
  }
}

/**
 * Runs recipe page setup steps in order. Safe to call after any navigation
 * or whenever the page should be brought into a known state before further
 * automation (e.g. cookie banners, waits).
 *
 * No-ops when `pageSetup` is missing, disabled, or has no steps.
 */
export async function applyPageSetupSteps(
  page: PageSetupPage,
  urlForLogging: string,
  pageSetup: PageSetupConfig | undefined
): Promise<void> {
  if (!pageSetup?.enabled || !pageSetup.steps?.length) {
    return;
  }

  for (const [index, step] of pageSetup.steps.entries()) {
    try {
      await runPageSetupStep(page, step);
    } catch (error) {
      const wrapped = new Error(
        `Error applying page setup step ${index + 1} (step type: ${step.type}) for page ${urlForLogging}`
      );
      (wrapped as Error & { cause?: unknown }).cause = error;
      throw wrapped;
    }
  }
}
