import { PageType } from "../../../common/types";
import { findCatalogueById } from "../data/catalogues";
import { startRecipe } from "../data/recipes";
import { toWatchRef } from "../jobWatching";
import getLogger from "../logging";
import { Queues, submitJob } from "../workers";

const logger = getLogger("extraction.submitAgenticRecipeDetection");

export async function submitAgenticRecipeDetection(
  url: string,
  catalogueId: number,
  triggeredByUserId?: number | null
) {
  const catalogue = await findCatalogueById(catalogueId);
  if (!catalogue) {
    throw new Error(`Catalogue not found: ${catalogueId}`);
  }

  // Agentic configuration runs asynchronously in the worker; avoid blocking
  // recipe creation on a synchronous page fetch (proxy/network/LLM page-type detection).
  const pageType = PageType.DETAIL_LINKS;
  logger.info(`Creating recipe for agentic configuration`);
  const result = await startRecipe(catalogueId, url, pageType);
  logger.info(`Created recipe ${result.id}`);
  const id = result.id;
  const jobId = `agenticRecipeConfig.${id}`;
  await submitJob(
    Queues.AgenticRecipeConfig,
    { recipeId: id, triggeredByUserId: triggeredByUserId ?? null },
    jobId
  );
  return {
    id,
    pageType,
    message: null,
    ...toWatchRef(Queues.AgenticRecipeConfig, jobId),
  };
}
