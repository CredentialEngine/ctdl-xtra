import { RecipeDetectionStatus, Step } from "@common/types";
import { findCatalogueById } from "../data/catalogues";
import { createExtraction, createPage, createStep } from "../data/extractions";
import { extractions, recipes } from "../data/schema";
import { Queues, submitJob, submitRepeatableJob } from "../workers";
import { Recipe } from "@/data/recipes";

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
    ? await launchAPIExtraction(extraction, recipe)
    : await launchLLMExtraction(extraction, recipe);

  return extraction;
}

async function launchLLMExtraction(extraction: typeof extractions.$inferSelect, recipe: typeof recipes.$inferSelect) {
  const step = await createStep({
    extractionId: extraction.id,
    step: Step.FETCH_ROOT,
    configuration: recipe.configuration,
  });
  const crawlPage = await createPage({
    crawlStepId: step.id,
    extractionId: extraction.id,
    url: recipe.url,
    dataType: recipe.configuration!.pageType,
  });
  submitJob(
    Queues.FetchPage,
    { crawlPageId: crawlPage.id },
    `fetchPage.${crawlPage.id}`
  );
  submitRepeatableJob(
    Queues.UpdateExtractionCompletion,
    { extractionId: extraction.id },
    `updateExtractionCompletion.${extraction.id}`,
    { every: 5 * 60 * 1000 }
  );
}

async function launchAPIExtraction(extraction: typeof extractions.$inferSelect, recipe: Recipe) {
  const step = await createStep({
    extractionId: extraction.id,
    step: Step.FETCH_VIA_API,
    configuration: recipe.configuration!,
  });
  const crawlPage = await createPage({
    crawlStepId: step.id,
    extractionId: extraction.id,
    url: recipe.url,
    dataType: recipe.configuration!.pageType,
  });
  submitJob(
    Queues.ExtractDataWithAPI,
    { crawlPageId: crawlPage.id },
    `extractWithApi.${crawlPage.id}`
  );
  submitRepeatableJob(
    Queues.UpdateExtractionCompletion,
    { extractionId: extraction.id },
    `updateExtractionCompletion.${extraction.id}`,
    { every: 5 * 60 * 1000 }
  );
}

