import {
  AgenticRecipeConfigJob,
  AgenticRecipeConfigProgress,
  createProcessor,
} from ".";
import { RecipeDetectionStatus } from "../../../common/types";
import { findRecipeById, updateRecipe } from "../data/recipes";
import getLogger from "../logging";

const logger = getLogger("workers.agenticRecipeConfig");

const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

export default createProcessor<
  AgenticRecipeConfigJob,
  AgenticRecipeConfigProgress
>(async function agenticRecipeConfig(job) {
  const recipeId = job.data.recipeId;
  const logPrefix = `[agenticRecipeConfig.${recipeId}]`;

  const recipe = await findRecipeById(recipeId);
  if (!recipe) {
    throw new Error(`${logPrefix} Recipe with ID ${recipeId} not found`);
  }

  logger.info(`${logPrefix} Starting job ${job.id}`);
  await updateRecipe(recipe.id, {
    status: RecipeDetectionStatus.IN_PROGRESS,
  });

  for (let step = 1; step <= 6; step++) {
    await sleep(10_000);
    const elapsedSeconds = step * 10;
    await job.updateProgress({
      message: `Bogus agent working… (${elapsedSeconds}s)`,
      status: "info",
      elapsedSeconds,
      step,
    });
    logger.info(`${logPrefix} Job ${job.id} progress step ${step}/6`);
  }

  const succeeded = Math.random() < 0.5;

  if (succeeded) {
    const pageType = recipe.configuration?.pageType;
    if (!pageType) {
      throw new Error(`${logPrefix} Recipe seed configuration missing pageType`);
    }
    await updateRecipe(recipe.id, {
      configuration: { pageType, linkRegexp: ".*" },
      status: RecipeDetectionStatus.SUCCESS,
      detectionFailureReason: null,
    });
    await job.updateProgress({
      status: "success",
      message: "Bogus agent completed",
    });
    logger.info(`${logPrefix} Job ${job.id} completed successfully`);
    return;
  }

  const failureMessage = "Bogus agent failed (random)";
  await updateRecipe(recipe.id, {
    status: RecipeDetectionStatus.ERROR,
    detectionFailureReason: failureMessage,
  });
  await job.updateProgress({
    status: "failure",
    message: failureMessage,
  });
  logger.info(`${logPrefix} Job ${job.id} failed (random)`);
  throw new Error(`${logPrefix} ${failureMessage}`);
});
