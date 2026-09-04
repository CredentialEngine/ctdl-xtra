import {
  AgenticRecipeConfigJob,
  AgenticRecipeConfigProgress,
  createProcessor,
  JobWithProgress,
} from ".";
import { AGENTIC_RECIPE_STAGE_LABELS } from "../../../common/recipe";
import { CatalogueType, RecipeDetectionStatus } from "../../../common/types";
import {
  agenticRecipeConfigurationPrompt,
  runBrowserAgent,
} from "../agentic";
import { AgenticRecipeRunTracker } from "../agentic/agenticRecipeRunTracker";
import { resolveAgentModel } from "../agentic/types";
import {
  formatAgentEventForPublicLog,
  stageLog,
  statusLog,
} from "../agentic/agenticRecipeEvents";
import type { AgentEvent } from "../agentic/types";
import { findRecipeById, updateRecipe } from "../data/recipes";
import { mergeJobProgress, publicLog } from "../jobWatching";
import type { PublicLoggableJob } from "../jobWatching/publicLog";
import getLogger from "../logging";

const logger = getLogger("workers.agenticRecipeConfig");

function createPublicLogHandler(
  job: JobWithProgress<AgenticRecipeConfigJob, AgenticRecipeConfigProgress>,
  logPrefix: string,
  tracker: AgenticRecipeRunTracker
) {
  return (event: AgentEvent) => {
    tracker.handleEvent(event);
    logger.info(`${logPrefix} ${event.type}: ${event.message.slice(0, 200)}`);
    const formatted = formatAgentEventForPublicLog(event);
    if (!formatted) {
      return;
    }
    if (formatted.kind === "stage") {
      void publicLog(
        job as PublicLoggableJob,
        logger,
        stageLog(formatted.stage)
      );
      void mergeJobProgress(job, {
        message: AGENTIC_RECIPE_STAGE_LABELS[formatted.stage],
        status: "info",
      });
      return;
    }
    void publicLog(
      job as PublicLoggableJob,
      logger,
      formatted.kind === "status"
        ? statusLog(formatted.message)
        : formatted.message
    );
    if (formatted.kind === "status") {
      void mergeJobProgress(job, {
        message: formatted.message,
        status: "info",
      });
    }
  };
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
  const model = resolveAgentModel(job.data.model);
  const catalogueType = recipe.catalogue?.catalogueType as
    | CatalogueType
    | undefined;

  let failureMessage: string | null = null;

  try {
    const tracker = new AgenticRecipeRunTracker();
    const result = await runBrowserAgent({
      prompt: agenticRecipeConfigurationPrompt({
        url: recipe.url,
        catalogueType,
      }),
      model,
      browser: {
        pageLoadWaitTime,
        pageSetup,
      },
      agenticRecipe: { recipeId: recipe.id },
      maxTurns: 200,
      onEvent: createPublicLogHandler(job, logPrefix, tracker),
    });

    if (tracker.giveUpMessage) {
      failureMessage = tracker.giveUpMessage;
    } else {
      const updatedRecipe = await findRecipeById(recipeId);
      if (updatedRecipe?.status === RecipeDetectionStatus.SUCCESS) {
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

      const incompatibleReason = extractFailureReason(result.resultText);
      if (incompatibleReason) {
        failureMessage = incompatibleReason;
        await updateRecipe(recipe.id, {
          status: RecipeDetectionStatus.ERROR,
          detectionFailureReason: incompatibleReason,
        });
        await publicLog(job, logger, incompatibleReason);
        await publicLog(
          job,
          logger,
          statusLog("Catalogue is not recipe-compatible.")
        );
        await mergeJobProgress(job, {
          status: "failure",
          message: "Catalogue is not recipe-compatible.",
        });
        logger.info(`${logPrefix} Job ${job.id} stopped: not recipe-compatible`);
        return;
      }

      failureMessage =
        "Agent finished without saving a recipe configuration.";
    }
  } catch (err: unknown) {
    failureMessage =
      err instanceof Error ? err.message : "Browser agent failed";
  }

  if (failureMessage) {
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
    throw new Error(`${logPrefix} ${failureMessage}`);
  }
});
