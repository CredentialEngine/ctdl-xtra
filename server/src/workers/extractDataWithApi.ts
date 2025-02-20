import { inspect } from "util";
import { createProcessor, ExtractDataJob, ExtractDataProgress } from ".";
import { createDataItem, findOrCreateDataset } from "../data/datasets";
import { findPageForJob, updatePage } from "../data/extractions";
import {
  getSqliteTimestamp,
} from "../data/schema";

import { ExtractionStatus, TextInclusion } from "@common/types";
import { resolveExctractionService } from "@/extraction/services";

export default createProcessor<ExtractDataJob, ExtractDataProgress>(
  async function extractDataWithApi(job) {
    const crawlPage = await findPageForJob(job.data.crawlPageId);

    if (crawlPage.extraction.status == ExtractionStatus.CANCELLED) {
      console.log(
        `Extraction ${crawlPage.extractionId} was cancelled; aborting`
      );
      return;
    }

    await updatePage(crawlPage.id, {
      dataExtractionStartedAt: getSqliteTimestamp(),
    });
    try {
      const dataset = await findOrCreateDataset(
        crawlPage.extraction.recipe.catalogueId,
        crawlPage.extractionId
      );

      if (!dataset) throw new Error("Could not find or create dataset");

      const extractionService = resolveExctractionService(crawlPage.extraction.recipe);
      const extractedData = await extractionService.extractData(crawlPage.extraction.recipe);
      
      for (const course of extractedData) {
        const incl = { full: true };
        const fullTextInclusion: TextInclusion = {
          course_description: incl,
          course_id: incl,
          course_name: incl,
          course_ceu_credits: incl,
          course_credits_max: incl,
          course_credits_min: incl,
          course_credits_type: incl,
          course_prerequisites: incl,
        }
        await createDataItem(crawlPage.id, dataset.id, course, fullTextInclusion);
      }
    } catch (err) {
      console.log(inspect(err));
      throw err;
    }
  }
);
