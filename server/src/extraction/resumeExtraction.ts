import { ExtractionStatus, LogLevel } from "../../../common/types";
import { findLatestDataset } from "../data/datasets";
import {
  createExtractionAuditLog,
  createExtractionLog,
  findApiExtractionRootPage,
  findExtractionById,
  findInProgressPagesWithoutJobs,
  findPagesNeedingExtractData,
  findPagesNeedingFetch,
  resetInProgressPagesToWaiting,
  updateExtraction,
} from "../data/extractions";
import getLogger from "../logging";
import {
  getPageIdsWithExistingJobs,
  Queues,
  REPEAT_UPDATE_COMPLETION_EVERY_MS,
  submitJob,
  submitJobs,
  submitRepeatableJob,
} from "../workers";
const logger = getLogger("extraction.resumeExtraction");

export async function resumeExtraction(
  extractionId: number,
  userId?: number
) {
  const extraction = await findExtractionById(extractionId);
  if (!extraction) {
    throw new Error(`Extraction ${extractionId} not found`);
  }
  if (
    extraction.status !== ExtractionStatus.STALE &&
    extraction.status !== ExtractionStatus.CANCELLED
  ) {
    throw new Error(
      `Extraction ${extractionId} can only be resumed when status is STALE or CANCELLED (current: ${extraction.status})`
    );
  }

  const recipe = extraction.recipe;
  const isApiExtraction = !!recipe.configuration?.apiProvider;

  const existingJobs = await getPageIdsWithExistingJobs(extractionId);
  const fetchPageCount = existingJobs.fetchPageIds.size;
  const extractDataCount = existingJobs.extractDataPageIds.size;

  if (isApiExtraction) {
    throw new Error("API extractions are not resumable yet.");
  }

  const inProgressWithoutJobs = await findInProgressPagesWithoutJobs(
    extractionId,
    existingJobs.fetchPageIds
  );
  const pageIdsToReset = inProgressWithoutJobs.map((p) => p.id);

  if (pageIdsToReset.length > 0) {
    await resetInProgressPagesToWaiting(extractionId, pageIdsToReset);
    logger.info(
      `Reset ${pageIdsToReset.length} IN_PROGRESS page(s) to WAITING for extraction ${extractionId}`
    );
  }

  await updateExtraction(extractionId, {
    status: ExtractionStatus.IN_PROGRESS,
  });

  const dataset = await findLatestDataset(extractionId);
  if (!dataset) {
    throw new Error(`Extraction ${extractionId} has no dataset`);
  }

  const pagesNeedingFetch = await findPagesNeedingFetch(extractionId);
  const pagesNeedingExtractData = await findPagesNeedingExtractData(extractionId);

  const fetchPagesToEnqueue = pagesNeedingFetch.filter(
    (p) => !existingJobs.fetchPageIds.has(p.id)
  );
  const extractPagesToEnqueue = pagesNeedingExtractData.filter(
    (p) => !existingJobs.extractDataPageIds.has(p.id)
  );

  let enqueuedFetch = 0;
  let enqueuedExtract = 0;

  if (fetchPagesToEnqueue.length > 0) {
    await submitJobs(
      Queues.FetchPage,
      fetchPagesToEnqueue.map((page) => ({
        data: {
          crawlPageId: page.id,
          extractionId,
          datasetId: dataset.id,
        },
        options: { jobId: `fetchPage.${page.id}`, lifo: true },
      }))
    );
    enqueuedFetch = fetchPagesToEnqueue.length;
  }

  if (extractPagesToEnqueue.length > 0) {
    await submitJobs(
      Queues.ExtractData,
      extractPagesToEnqueue.map((page) => ({
        data: {
          crawlPageId: page.id,
          extractionId,
          datasetId: dataset.id,
        },
        options: { jobId: `extractData.${page.id}` },
      }))
    );
    enqueuedExtract = extractPagesToEnqueue.length;
  }

  await submitRepeatableJob(
    Queues.UpdateExtractionCompletion,
    { extractionId },
    `updateExtractionCompletion.${extractionId}`,
    { every: REPEAT_UPDATE_COMPLETION_EVERY_MS }
  );

  if (userId) {
    await createExtractionAuditLog(extractionId, userId, "RESUME", null);
  }

  const logMessage =
    `Resumed extraction. Skipped ${fetchPageCount} page(s) with existing FetchPage jobs, ` +
    `${extractDataCount} with ExtractData jobs. ` +
    `Enqueued ${enqueuedFetch} FetchPage and ${enqueuedExtract} ExtractData jobs.`;

  await createExtractionLog(extractionId, logMessage, LogLevel.INFO);

  logger.info(
    `Resumed extraction ${extractionId}. ${logMessage}`
  );
}
