import { CatalogueType, PageType } from "../../../common/types";
import { findCatalogueById } from "../data/catalogues";
import { startRecipe } from "../data/recipes";
import getLogger from "../logging";
import { bestOutOf } from "../utils";
import { Queues, submitJob } from "../workers";
import { fetchBrowserPage, simplifiedMarkdown } from "./browser";
import { detectPageType } from "./llm/detectPageType";

const logger = getLogger("extraction.submitRecipeDetection");

export async function submitRecipeDetection(url: string, catalogueId: number) {
  const { content, screenshot } = await fetchBrowserPage(url);
  const markdownContent = await simplifiedMarkdown(content);
  logger.info(`Downloaded ${url}.`);
  logger.info(`Detecting page type`);
  const catalogue = await findCatalogueById(catalogueId);
  if (!catalogue) {
    throw new Error(`Catalogue not found: ${catalogueId}`);
  }
  let pageType = await bestOutOf(
    5,
    () =>
      detectPageType({
        url,
        content: markdownContent,
        screenshot,
        catalogueType: catalogue.catalogueType as CatalogueType,
      }),
    (p) => p as string
  );
  logger.info(`Detected page type: ${pageType}`);
  let message: string | null = null;
  if (!pageType) {
    message =
      "Page was not detected as a course catalogue index. Defaulting to home page type: course links.";
    pageType = PageType.DETAIL_LINKS;
  }
  logger.info(`Creating recipe`);
  const result = await startRecipe(catalogueId, url, pageType);
  logger.info(`Created recipe ${result.id}`);
  const id = result.id;
  await submitJob(
    Queues.DetectConfiguration,
    { recipeId: id },
    `detectConfiguration.${id}`
  );
  return {
    id,
    pageType,
    message,
  };
}
