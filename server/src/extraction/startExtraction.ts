import { ExtractionStatus, RecipeDetectionStatus, Step } from "../../../common/types";
import { findCatalogueById } from "../data/catalogues";
import { createDataset } from "../data/datasets";
import { createExtraction, createPage, createStep, findExtractionById, findExtractionValidPages, updateExtraction } from "../data/extractions";
import { catalogues, extractions, recipes } from "../data/schema";
import getLogger from "../logging";
import {
  ExtractDataJob,
  Queues,
  REPEAT_UPDATE_COMPLETION_EVERY_MS,
  submitJob,
  submitJobs,
  SubmitJobsItem,
  submitRepeatableJob,
} from "../workers";

const logger = getLogger("extraction.startExtraction");

export async function startExtraction(catalogueId: number, recipeId: number) {
  const catalogue = await findCatalogueById(catalogueId);
  if (!catalogue) {
    throw new Error(`Catalogue ${catalogueId} not found`);
  }
  const recipe = catalogue.recipes.find((r) => r.id == recipeId);
  if (!recipe) {
    throw new Error(`Recipe ${recipeId} not found`);
  }
  if (recipe.status != RecipeDetectionStatus.SUCCESS) {
    throw new Error(`Recipe ${recipeId} hasn't been configured for extraction`);
  }
  const extraction = await createExtraction(recipe.id);

  recipe.configuration.apiProvider
    ? await launchAPIExtraction(catalogue, extraction, recipe)
    : await launchLLMExtraction(catalogue, extraction, recipe);

  return extraction;
}

export async function rerunDataExtraction(extractionId: number) {
  logger.info(`Rerunning data extraction for extraction ${extractionId}`);
  const extraction = await findExtractionById(extractionId);
  if (!extraction) {
    throw new Error("Extraction not found");
  }
  const dataset = await createDataset(extractionId);
  await updateExtraction(extractionId, {
    status: ExtractionStatus.IN_PROGRESS,
    completionStats: null
  });
  const limit = 20;
  let offset = 0;
  while (true) {
    const pages = await findExtractionValidPages(extractionId, limit, offset);

    const jobDefinitions: SubmitJobsItem<ExtractDataJob>[] = pages.map(page => ({
      data: {
        crawlPageId: page.id,
        datasetId: dataset.id,
        extractionId,
      },
      options: {
        jobId: `extractData.rerun.${dataset.id}.${page.id}`
      }
    }));

    await submitJobs(Queues.ExtractData, jobDefinitions);
    offset += limit;

    if (pages.length < limit) {
      break;
    }
  }
  await submitRepeatableJob(
    Queues.UpdateExtractionCompletion,
    { extractionId },
    `updateExtractionCompletion.${extractionId}`,
    { every: REPEAT_UPDATE_COMPLETION_EVERY_MS }
  );
}

async function launchLLMExtraction(
  _catalogue: typeof catalogues.$inferSelect,
  extraction: typeof extractions.$inferSelect,
  recipe: typeof recipes.$inferSelect
) {
  const step = await createStep({
    extractionId: extraction.id,
    step: Step.FETCH_ROOT,
    configuration: recipe.configuration,
  });
  const crawlPage = await createPage({
    crawlStepId: step.id,
    step: Step.FETCH_ROOT,
    extractionId: extraction.id,
    url: recipe.url,
    pageType: recipe.configuration!.pageType,
  });
  const dataset = await createDataset(extraction.id);
  submitJob(
    Queues.FetchPage,
    { crawlPageId: crawlPage.id, extractionId: extraction.id, datasetId: dataset.id },
    `fetchPage.${crawlPage.id}`
  );
  submitRepeatableJob(
    Queues.UpdateExtractionCompletion,
    { extractionId: extraction.id },
    `updateExtractionCompletion.${extraction.id}`,
    { every: REPEAT_UPDATE_COMPLETION_EVERY_MS }
  );
}

async function launchAPIExtraction(
  _catalogue: typeof catalogues.$inferSelect,
  extraction: typeof extractions.$inferSelect,
  recipe: typeof recipes.$inferSelect
) {
  const step = await createStep({
    extractionId: extraction.id,
    step: Step.FETCH_VIA_API,
    configuration: recipe.configuration!,
  });
  const crawlPage = await createPage({
    crawlStepId: step.id,
    step: Step.FETCH_VIA_API,
    extractionId: extraction.id,
    url: recipe.url,
    pageType: recipe.configuration!.pageType,
  });
  const dataset = await createDataset(extraction.id);
  submitJob(
    Queues.ExtractDataWithAPI,
    { crawlPageId: crawlPage.id, extractionId: extraction.id, datasetId: dataset.id },
    `extractWithApi.${crawlPage.id}`
  );
  submitRepeatableJob(
    Queues.UpdateExtractionCompletion,
    { extractionId: extraction.id },
    `updateExtractionCompletion.${extraction.id}`,
    { every: REPEAT_UPDATE_COMPLETION_EVERY_MS }
  );
}
