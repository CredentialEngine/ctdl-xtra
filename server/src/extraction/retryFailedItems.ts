import { ExtractionStatus } from "../../../common/types";
import { findExtractionDatasets } from "../data/datasets";
import {
  findExtractionById,
  findFailedAndNoDataPageIds,
  updateExtraction,
} from "../data/extractions";
import {
  Queues,
  REPEAT_UPDATE_COMPLETION_EVERY_MS,
  submitJobs,
  submitRepeatableJob,
} from "../workers";

export async function retryFailedItems(extractionId: number) {
  const extraction = await findExtractionById(extractionId);
  if (!extraction) {
    throw new Error(`Extraction with id ${extractionId} not found`);
  }
  if (extraction.status != ExtractionStatus.COMPLETE) {
    throw new Error(`Extraction ${extractionId} is not complete`);
  }

  const pageIds = (
    await Promise.all(
      extraction.crawlSteps.map((step) => findFailedAndNoDataPageIds(step.id))
    )
  ).flat();

  if (!pageIds.length) {
    throw new Error(
      `Couldn't find any failed pages for extraction ${extractionId}`
    );
  }

  await updateExtraction(extractionId, {
    status: ExtractionStatus.IN_PROGRESS,
    completionStats: {
      ...extraction.completionStats!,
      generatedAt: new Date().toISOString(),
    },
  });

  const datasets = await findExtractionDatasets(extraction.id);

  for (const dataset of datasets) {
    await submitJobs(
      Queues.FetchPage,
      pageIds.map((id) => ({
        data: { crawlPageId: id, extractionId, datasetId: dataset.id },
        options: { jobId: `fetchPage.${id}` },
      }))
    );
  }

  await submitRepeatableJob(
    Queues.UpdateExtractionCompletion,
    { extractionId: extraction.id },
    `updateExtractionCompletion.${extraction.id}`,
    { every: REPEAT_UPDATE_COMPLETION_EVERY_MS }
  );
  return;
}
