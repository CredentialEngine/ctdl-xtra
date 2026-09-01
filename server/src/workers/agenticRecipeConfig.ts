import {
  AgenticRecipeConfigJob,
  AgenticRecipeConfigProgress,
  createProcessor,
} from ".";
import { RecipeDetectionStatus } from "../../../common/types";
import { inspectPagePrompt, runBrowserAgent } from "../agentic";
import { findRecipeById, updateRecipe } from "../data/recipes";
import { mergeJobProgress, publicLog } from "../jobWatching";
import getLogger from "../logging";

const logger = getLogger("workers.agenticRecipeConfig");

function statusLog(message: string): string {
  return `<status>${message}</status>`;
}

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

  const pageType = recipe.configuration?.pageType;
  if (!pageType) {
    throw new Error(`${logPrefix} Recipe seed configuration missing pageType`);
  }

  logger.info(`${logPrefix} Starting job ${job.id}`);
  await publicLog(job, logger, statusLog("Starting agentic configuration"));
  await updateRecipe(recipe.id, {
    status: RecipeDetectionStatus.IN_PROGRESS,
  });
  await mergeJobProgress(job, {
    message: "Starting agentic configuration",
    status: "info",
  });

  const pageLoadWaitTime = recipe.configuration?.pageLoadWaitTime;
  const pageSetup = recipe.configuration?.pageSetup;

  try {
    await publicLog(job, logger, statusLog("Running browser agent"));
    await mergeJobProgress(job, {
      message: "Running browser agent",
      status: "info",
    });

    const result = await runBrowserAgent({
      prompt: inspectPagePrompt({ url: recipe.url }),
      browser: {
        pageLoadWaitTime,
        pageSetup,
      },
      onEvent: (event) => {
        logger.info(`${logPrefix} ${event.message}`);
        if (event.type === "status") {
          void publicLog(job, logger, event.message);
        }
      },
    });

    await updateRecipe(recipe.id, {
      status: RecipeDetectionStatus.SUCCESS,
      detectionFailureReason: null,
    });
    await publicLog(
      job,
      logger,
      statusLog("Agent finished inspecting this recipe.")
    );
    await publicLog(job, logger, result.resultText);
    await mergeJobProgress(job, {
      status: "success",
      message: "Agent finished inspecting this recipe.",
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
    await publicLog(job, logger, failureMessage);
    await publicLog(job, logger, statusLog(failureMessage));
    await mergeJobProgress(job, {
      status: "failure",
      message: failureMessage,
    });
    logger.info(`${logPrefix} Job ${job.id} failed`);
    throw err instanceof Error
      ? err
      : new Error(`${logPrefix} ${failureMessage}`);
  }
});
