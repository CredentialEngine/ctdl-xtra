import { inspect } from "util";
import { createProcessor, ExtractDataJob, ExtractDataProgress } from ".";
import { createDataItem, findDataset } from "../data/datasets";
import {
  findPageForJob,
  updateExtraction,
  updatePage,
} from "../data/extractions";
import { crawlPages, getSqliteTimestamp } from "../data/schema";

import {
  CourseStructuredData,
  ExtractionStatus,
  PageStatus,
  TextInclusion,
} from "../../../common/types";
import { resolveExtractionService } from "../extraction/services";
import getLogger from "../logging";

const logger = getLogger("workers.extractDataWithApi");

function updatePageAndExtractionInProgress(
  page: typeof crawlPages.$inferSelect
) {
  return Promise.all([
    updatePage(page.id, {
      status: PageStatus.IN_PROGRESS,
      dataExtractionStartedAt: getSqliteTimestamp(),
    }),
    updateExtraction(page.extractionId, {
      status: ExtractionStatus.IN_PROGRESS,
    }),
  ]);
}

function updatePageAndExtractionAsComplete(
  page: typeof crawlPages.$inferSelect,
  courseCount: number
) {
  return Promise.all([
    updatePage(page.id, {
      status: PageStatus.SUCCESS,
    }),
    updateExtraction(page.extractionId, {
      status: ExtractionStatus.COMPLETE,
      completionStats: {
        generatedAt: String(getSqliteTimestamp()),
        steps: [
          {
            extractions: {
              attempted: 1,
              succeeded: 1,
              courses: courseCount,
            },
            downloads: {
              attempted: 1,
              succeeded: 1,
              total: 1,
            },
          },
        ],
      },
    }),
  ]);
}

function updatePageAndExtractionWithError(
  page: typeof crawlPages.$inferSelect,
  error: any
) {
  return Promise.all([
    updatePage(page.id, {
      status: PageStatus.ERROR,
      fetchFailureReason: {
        reason: String(error),
        responseStatus: 1,
      },
    }),
    updateExtraction(page.extractionId, {
      status: ExtractionStatus.CANCELLED,
    }),
  ]);
}

export default createProcessor<ExtractDataJob, ExtractDataProgress>(
  async function extractDataWithApi(job) {
    const crawlPage = await findPageForJob(job.data.crawlPageId);

    if (crawlPage.extraction.status == ExtractionStatus.CANCELLED) {
      logger.info(
        `Extraction ${crawlPage.extractionId} was cancelled; aborting`
      );
      return;
    }

    try {
      await updatePageAndExtractionInProgress(crawlPage);
      const dataset = await findDataset(
        job.data.datasetId
      );

      if (!dataset) throw new Error("Could not find or create dataset");

      let totalCourses = 0;
      const extractionService = resolveExtractionService(
        crawlPage.extraction.recipe
      );

      const incl = { full: true };
      const fullTextInclusion: TextInclusion<CourseStructuredData> = {
        course_description: incl,
        course_id: incl,
        course_name: incl,
        course_ceu_credits: incl,
        course_credits_max: incl,
        course_credits_min: incl,
        course_credits_type: incl,
        course_prerequisites: incl,
      };

      await extractionService.extractData(
        crawlPage.extraction.recipe,
        async (resultBatch) => {
          for (const course of resultBatch) {
            await createDataItem(
              crawlPage.id,
              dataset.id,
              course,
              fullTextInclusion
            );
            totalCourses++;
          }
          return true; // continue supplying batches
        }
      );

      await updatePageAndExtractionAsComplete(crawlPage, totalCourses);
    } catch (err) {
      logger.error(inspect(err));
      await updatePageAndExtractionWithError(crawlPage, err);

      throw err;
    }
  }
);
