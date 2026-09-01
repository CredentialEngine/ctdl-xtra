import {
  AgenticRecipeConfigJob,
  AgenticRecipeConfigProgress,
  createProcessor,
} from ".";
import { RecipeDetectionStatus } from "../../../common/types";
import {
  AGENT_SMOKE_URL,
  inspectPagePrompt,
  runBrowserAgent,
} from "../agentic";
import { findRecipeById, updateRecipe } from "../data/recipes";
import getLogger from "../logging";

const logger = getLogger("workers.agenticRecipeConfig");

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
  await job.updateProgress({
    message: "Running browser agent",
    status: "info",
  });

  const pageLoadWaitTime = recipe.configuration?.pageLoadWaitTime;
  const pageSetup = recipe.configuration?.pageSetup;

  try {
    const result = await runBrowserAgent({
      prompt: inspectPagePrompt({
        url: 'https://www.reddit.com',
        pageLoadWaitTime,
        pageSetup,
      }),
      browser: {
        pageLoadWaitTime,
        pageSetup,
      },
      onEvent: (event) => logger.info(`${logPrefix} ${event.message}`),
    });

    const pageType = recipe.configuration?.pageType;
    if (!pageType) {
      throw new Error(
        `${logPrefix} Recipe seed configuration missing pageType`
      );
    }
    await updateRecipe(recipe.id, {
      configuration: { pageType, linkRegexp: ".*" },
      status: RecipeDetectionStatus.SUCCESS,
      detectionFailureReason: null,
    });
    await job.updateProgress({
      status: "success",
      message: result.resultText.slice(0, 1000),
    });
    logger.info(
      `${logPrefix} Job ${job.id} completed tools=${result.toolNames.join(",")}`
    );
  } catch (err: unknown) {
    const failureMessage =
      err instanceof Error ? err.message : "Browser agent failed";
    await updateRecipe(recipe.id, {
      status: RecipeDetectionStatus.ERROR,
      detectionFailureReason: failureMessage,
    });
    await job.updateProgress({
      status: "failure",
      message: failureMessage,
    });
    logger.info(`${logPrefix} Job ${job.id} failed`);
    throw err instanceof Error
      ? err
      : new Error(`${logPrefix} ${failureMessage}`);
  }
});
