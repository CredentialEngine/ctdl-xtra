import type { CatalogueType, PageSetupConfig } from "../../../common/types";

export function describePageSetup(pageSetup: PageSetupConfig): string | null {
  if (!pageSetup.enabled || pageSetup.steps.length === 0) {
    return null;
  }
  const steps = pageSetup.steps.map((step, index) => {
    if (step.type === "click") {
      return `${index + 1}. click ${step.selector}`;
    }
    return `${index + 1}. wait ${step.seconds}s`;
  });
  return `After the page loads, perform these setup steps in order: ${steps.join("; ")}.`;
}

export function inspectPagePrompt(input: {
  url: string;
  pageLoadWaitTime?: number;
  pageSetup?: PageSetupConfig;
}): string {
  const parts = [
    `Call puppeteer_navigate with url "${input.url}" and do not pass launchOptions.`,
  ];
  const setup = input.pageSetup ? describePageSetup(input.pageSetup) : null;
  if (setup) {
    parts.push(setup);
  }
  if (input.pageLoadWaitTime && input.pageLoadWaitTime > 0) {
    parts.push(
      `Then wait ${input.pageLoadWaitTime} seconds for page scripts to finish.`
    );
  }
  parts.push(
    'Look at the first entry in the page and output what it is.'
  );
  return parts.join(" ");
}

export function recipeConfigurationPrompt(input: {
  url: string;
  catalogueType?: CatalogueType;
  pageLoadWaitTime?: number;
  pageSetup?: PageSetupConfig;
}): string {
  const context = [
    `You are configuring a crawl recipe for ${input.url}.`,
    input.catalogueType
      ? `The catalogue type is ${input.catalogueType}.`
      : null,
    describePageSetup(input.pageSetup ?? { enabled: false, steps: [] }),
    input.pageLoadWaitTime && input.pageLoadWaitTime > 0
      ? `After navigation, wait ${input.pageLoadWaitTime} seconds before inspecting the page.`
      : null,
    "Use Puppeteer MCP tools to load and inspect the page.",
    "Do not pass launchOptions to puppeteer_navigate.",
    "Further recipe-authoring instructions will be supplied by the configuration task.",
  ].filter(Boolean);
  return context.join(" ");
}
