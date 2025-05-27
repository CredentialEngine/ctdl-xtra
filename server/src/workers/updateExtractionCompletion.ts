import { deepEqual } from "fast-equals";
import {
  createProcessor,
  detectExtractionJobs,
  JobWithProgress,
  Queues,
  UpdateExtractionCompletionJob,
  UpdateExtractionCompletionProgress,
} from ".";
import {
  CompletionStats,
  CostCallSite,
  CostSummary,
  ExtractionStatus,
  PageStatus,
  ProviderModel,
  StepCompletionStats,
} from "../../../common/types";
import {
  findExtractionById,
  getApiCallSummary,
  getStepStats,
  updateExtraction,
} from "../data/extractions";
import { sendEmailToAll } from "../email";
import ExtractionComplete from "../emails/extractionComplete";
import getLogger from "../logging";
import { estimateCost } from "../openai";

const logger = getLogger("workers.updateExtractionCompletion");

async function getStepCompletionStats(
  extraction: NonNullable<Awaited<ReturnType<typeof findExtractionById>>>
) {
  const stats: StepCompletionStats[] = [];
  for (const step of extraction.crawlSteps || []) {
    const rawStepStats = await getStepStats(step.id);
    let downloadsTotal = 0,
      downloadsAttempted = 0,
      downloadsSucceeded = 0,
      extractionsAttempted = 0,
      extractionsSucceeded = 0,
      extractionsCourses = 0;
    for (const rawPageStats of rawStepStats) {
      downloadsTotal += 1;
      if (rawPageStats.status == PageStatus.SUCCESS) {
        downloadsAttempted += 1;
        downloadsSucceeded += 1;
      } else if (rawPageStats.status == PageStatus.ERROR) {
        downloadsAttempted += 1;
      }
      if (rawPageStats.dataExtractionStartedAt) {
        extractionsAttempted += 1;
        if (rawPageStats.dataItemCount > 0) {
          extractionsSucceeded += 1;
          extractionsCourses += rawPageStats.dataItemCount;
        }
      }
    }
    stats.push({
      downloads: {
        total: downloadsTotal,
        attempted: downloadsAttempted,
        succeeded: downloadsSucceeded,
      },
      extractions: {
        attempted: extractionsAttempted,
        succeeded: extractionsSucceeded,
        courses: extractionsCourses,
      },
    });
  }
  return stats;
}

async function removeSelf(
  job: JobWithProgress<
    UpdateExtractionCompletionJob,
    UpdateExtractionCompletionProgress
  >
) {
  logger.info(`Removing repeatable job ${job.repeatJobKey}`);
  return Queues.UpdateExtractionCompletion.removeRepeatableByKey(
    job.repeatJobKey!
  );
}

async function computeCosts(
  extraction: NonNullable<Awaited<ReturnType<typeof findExtractionById>>>
) {
  const apiCallSummary = await getApiCallSummary(extraction.id);

  let totalInputTokens = 0;
  let totalOutputTokens = 0;
  const callSites: CostCallSite[] = [];

  for (const summary of apiCallSummary) {
    totalInputTokens += summary.totalInputTokens;
    totalOutputTokens += summary.totalOutputTokens;
    callSites.push({
      callSite: summary.callSite,
      totalInputTokens: summary.totalInputTokens,
      totalOutputTokens: summary.totalOutputTokens,
      estimatedCost: estimateCost(
        summary.model as ProviderModel,
        summary.totalInputTokens,
        summary.totalOutputTokens
      ),
    });
  }

  const costSummary: CostSummary = {
    totalInputTokens,
    totalOutputTokens,
    callSites,
    estimatedCost: callSites.reduce((sum, site) => sum + site.estimatedCost, 0),
  };

  return costSummary;
}

async function afterExtractionComplete(
  job: JobWithProgress<
    UpdateExtractionCompletionJob,
    UpdateExtractionCompletionProgress
  >,
  extraction: NonNullable<Awaited<ReturnType<typeof findExtractionById>>>
) {
  await removeSelf(job);
  await sendEmailToAll(
    ExtractionComplete,
    {
      extractionId: extraction.id,
      recipeId: extraction.recipeId,
      catalogueId: extraction.recipe.catalogueId,
      catalogueName: extraction.recipe.catalogue.name,
      url: extraction.recipe.url,
      completionStats: extraction.completionStats!,
      createdAt: extraction.createdAt.toISOString(),
      stale: extraction.status == ExtractionStatus.STALE,
    },
    `Extraction #${extraction.id} has finished`
  );
}

async function handleStaleExtraction(
  job: JobWithProgress<
    UpdateExtractionCompletionJob,
    UpdateExtractionCompletionProgress
  >,
  extraction: NonNullable<Awaited<ReturnType<typeof findExtractionById>>>,
  staleMs: number
) {
  const allStepsCompleted = extraction.completionStats!.steps.every(
    (s) =>
      s.downloads.attempted == s.downloads.total &&
      s.extractions.attempted == s.downloads.succeeded
  );
  const status = allStepsCompleted
    ? ExtractionStatus.COMPLETE
    : ExtractionStatus.STALE;

  const waitForCompletionMs = 5 * 60 * 1000;
  const waitForStaleMs = 4 * 60 * 60 * 1000;

  if (status == ExtractionStatus.COMPLETE) {
    if (staleMs < waitForCompletionMs) {
      const remainingTime = (waitForCompletionMs - staleMs) / 1000;
      logger.info(
        `No changes for extraction ${extraction.id}, looks complete; waiting ${remainingTime}s`
      );
      return;
    } else {
      const shouldKeepWaiting = await detectExtractionJobs(extraction.id);
      if (shouldKeepWaiting) {
        logger.info(
          `No changes for extraction ${extraction.id}, there are pending jobs; waiting`
        );
        return;
      }
      logger.info(`Found no pending jobs for extraction ${extraction.id}`);
    }
  } else if (status == ExtractionStatus.STALE && staleMs < waitForStaleMs) {
    const remainingTime = (waitForStaleMs - staleMs) / 1000;
    logger.info(
      `No changes for extraction ${extraction.id}, looks incomplete; waiting ${remainingTime}s`
    );
    return;
  }

  logger.info(`Marking extraction ${extraction.id} as ${status}`);
  extraction.status = status;
  await updateExtraction(extraction.id, {
    status,
  });
  return afterExtractionComplete(job, extraction);
}

export default createProcessor<
  UpdateExtractionCompletionJob,
  UpdateExtractionCompletionProgress
>(async function updateExtractionCompletion(job) {
  const extraction = await findExtractionById(job.data.extractionId);
  if (
    !extraction ||
    extraction.status == ExtractionStatus.COMPLETE ||
    extraction.status == ExtractionStatus.CANCELLED
  ) {
    await removeSelf(job);
    return;
  }
  logger.info(`Updating completion for extraction ${extraction.id}`);

  const stepStats = await getStepCompletionStats(extraction);
  const costStats = await computeCosts(extraction);
  const currentDate = new Date();
  const completionStats: CompletionStats = {
    generatedAt: currentDate.toISOString(),
    steps: stepStats,
    costs: costStats,
  };

  // If there's a preexisting completionStats value, check if it changed
  if (extraction.completionStats) {
    const stale = deepEqual(stepStats, extraction.completionStats.steps);
    if (stale) {
      const timeDiff = Math.abs(
        currentDate.getTime() -
          new Date(extraction.completionStats.generatedAt).getTime()
      );
      await handleStaleExtraction(job, extraction, timeDiff);
      return;
    }
  }

  logger.info(`Detected changes for extraction ${extraction.id}; updating`);
  await updateExtraction(extraction.id, { completionStats });
  return;
});
