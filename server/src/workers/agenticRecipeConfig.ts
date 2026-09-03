import {
  AgenticRecipeConfigJob,
  AgenticRecipeConfigProgress,
  createProcessor,
  JobWithProgress,
} from ".";
import { CatalogueType, RecipeDetectionStatus } from "../../../common/types";
import {
  agenticRecipeConfigurationPrompt,
  runBrowserAgent,
} from "../agentic";
import {
  formatAgentEventForPublicLog,
  statusLog,
} from "../agentic/agenticRecipeEvents";
import type { AgentEvent } from "../agentic/types";
import { findRecipeById, updateRecipe } from "../data/recipes";
import { mergeJobProgress, publicLog } from "../jobWatching";
import type { PublicLoggableJob } from "../jobWatching/publicLog";
import getLogger from "../logging";

const logger = getLogger("workers.agenticRecipeConfig");

const XTRA_SUBMIT_TOOL = "mcp__xtra__xtra_submit_recipe_configuration";

function createPublicLogHandler(
  job: JobWithProgress<AgenticRecipeConfigJob, AgenticRecipeConfigProgress>,
  logPrefix: string
) {
  return (event: AgentEvent) => {
    logger.info(`${logPrefix} ${event.type}: ${event.message.slice(0, 200)}`);
    const formatted = formatAgentEventForPublicLog(event);
    if (!formatted) {
      return;
    }
    void publicLog(
      job as PublicLoggableJob,
      logger,
      formatted.isStatus ? statusLog(formatted.message) : formatted.message
    );
    if (formatted.isStatus) {
      void mergeJobProgress(job, {
        message: formatted.message,
        status: "info",
      });
    }
  };
}

function agentSubmittedRecipe(toolNames: string[]): boolean {
  return toolNames.includes(XTRA_SUBMIT_TOOL);
}

function extractFailureReason(resultText: string): string | null {
  const lowered = resultText.toLowerCase();
  if (
    lowered.includes("not recipe-compatible") ||
    lowered.includes("not compatible with a recipe") ||
    lowered.includes("cannot be crawled with a recipe")
  ) {
    return resultText.trim();
  }
  return null;
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
  const catalogueType = recipe.catalogue?.catalogueType as
    | CatalogueType
    | undefined;

  try {
    const result = await runBrowserAgent({
      prompt: agenticRecipeConfigurationPrompt({
        url: recipe.url,
        catalogueType,
      }),
      browser: {
        pageLoadWaitTime,
        pageSetup,
      },
      agenticRecipe: { recipeId: recipe.id },
      maxTurns: 200,
      onEvent: createPublicLogHandler(job, logPrefix),
    });

    const submitted = agentSubmittedRecipe(result.toolNames);
    const incompatibleReason = extractFailureReason(result.resultText);

    if (submitted) {
      await publicLog(
        job,
        logger,
        statusLog("Agent finished configuring this recipe.")
      );
      await mergeJobProgress(job, {
        status: "success",
        message: "Agent finished configuring this recipe.",
      });
      logger.info(
        `${logPrefix} Job ${job.id} completed tools=${result.toolNames.join(",")}`
      );
      return;
    }

    if (incompatibleReason) {
      await updateRecipe(recipe.id, {
        status: RecipeDetectionStatus.ERROR,
        detectionFailureReason: incompatibleReason,
      });
      await publicLog(job, logger, incompatibleReason);
      await publicLog(job, logger, statusLog("Catalogue is not recipe-compatible."));
      await mergeJobProgress(job, {
        status: "failure",
        message: "Catalogue is not recipe-compatible.",
      });
      logger.info(`${logPrefix} Job ${job.id} stopped: not recipe-compatible`);
      return;
    }

    const failureMessage =
      "Agent finished without submitting a recipe configuration.";
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
    throw new Error(`${logPrefix} ${failureMessage}`);
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
