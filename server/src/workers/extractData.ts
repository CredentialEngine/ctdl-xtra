import { inspect } from "util";
import { createProcessor, ExtractDataJob, ExtractDataProgress } from ".";
import { createDataItem, findOrCreateDataset } from "../data/datasets";
import { findPageForJob, updatePage } from "../data/extractions";
import {
  getSqliteTimestamp,
  readMarkdownContent,
  readScreenshot,
} from "../data/schema";

import { CatalogueType, ExtractionStatus } from "../../../common/types";
import { extractAndVerifyEntityData } from "../extraction/llm/extractAndVerifyEntityData";

export default createProcessor<ExtractDataJob, ExtractDataProgress>(
  async function extractData(job) {
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

      const content = await readMarkdownContent(
        crawlPage.extractionId,
        crawlPage.crawlStepId,
        crawlPage.id
      );
      const screenshot = await readScreenshot(
        crawlPage.extractionId,
        crawlPage.crawlStepId,
        crawlPage.id
      );

      const catalogueType = crawlPage.extraction.recipe.catalogue
        .catalogueType as CatalogueType;

      const extractedData = await extractAndVerifyEntityData({
        url: crawlPage.url,
        content,
        screenshot,
        catalogueType,
        logApiCalls: { extractionId: crawlPage.extractionId },
      });

      if (!extractedData) {
        console.log(`No data found for ${crawlPage.url}`);
        return;
      }

      //@ts-ignore
      for (const { entity, textInclusion } of extractedData) {
        if (!entity) {
          console.log(`No entity found for ${crawlPage.url}`);
          continue;
        }
        await createDataItem(crawlPage.id, dataset.id, entity, textInclusion);
      }
    } catch (err) {
      console.log(inspect(err));
      throw err;
    }
  }
);
