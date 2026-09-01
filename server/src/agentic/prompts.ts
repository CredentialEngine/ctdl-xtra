import type { CatalogueType } from "../../../common/types";

export function inspectPagePrompt(input: { url: string }): string {
  return `Call puppeteer_navigate with url "${input.url}". Look at the first entry in the page and output what it is.`;
}

export function recipeConfigurationPrompt(input: {
  url: string;
  catalogueType?: CatalogueType;
}): string {
  const context = [
    `You are configuring a crawl recipe for ${input.url}.`,
    input.catalogueType
      ? `The catalogue type is ${input.catalogueType}.`
      : null,
    "Use Puppeteer MCP tools to load and inspect the page.",
    "Further recipe-authoring instructions will be supplied by the configuration task.",
  ].filter(Boolean);
  return context.join(" ");
}
