import { CatalogueType, PageType } from "../../../common/types";
import { findCatalogueById } from "../data/catalogues";
import { startRecipe } from "../data/recipes";
import { findGetSettingJSON } from "../data/settings";
import { ProxySettings } from "../types";
import { bestOutOf } from "../utils";
import { Queues, submitJob } from "../workers";
import { fetchPageWithProxy, simplifiedMarkdown } from "./browser";
import { detectPageType } from "./llm/detectPageType";

export async function submitRecipeDetection(url: string, catalogueId: number) {
  const proxy = await findGetSettingJSON<ProxySettings>('PROXY');
  console.log(`Fetching ${url}${proxy?.enabled ? ` using proxy.` : ""}`);
  
  const { content, screenshot } = await fetchPageWithProxy(url);
  const markdownContent = await simplifiedMarkdown(content);
  console.log(`Downloaded ${url}.`);
  console.log(`Detecting page type`);
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
  console.log(`Detected page type: ${pageType}`);
  let message: string | null = null;
  if (!pageType) {
    message =
      "Page was not detected as a course catalogue index. Defaulting to home page type: course links.";
    pageType = PageType.DETAIL_LINKS;
  }
  console.log(`Creating recipe`);
  const result = await startRecipe(catalogueId, url, pageType);
  console.log(`Created recipe ${result.id}`);
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
