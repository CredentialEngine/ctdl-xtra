import { inspect } from "util";
import {
  createProcessor,
  ExtractDataJob,
  ExtractDataProgress,
  Queues,
  submitJobs,
} from ".";
import { createDataItem, findDataset } from "../data/datasets";
import {
  countParentNodesOfCrawlSteps,
  createStepAndPages,
  findPageForJob,
  updatePage,
} from "../data/extractions";
import {
  getSqliteTimestamp,
  readMarkdownContent,
  readScreenshot,
} from "../data/schema";

import {
  CatalogueType,
  ExtractionStatus,
  PageType,
  Step,
} from "../../../common/types";
import { getCatalogueTypeDefinition } from "../extraction/catalogueTypes";
import { determinePresenceOfEntity } from "../extraction/llm/determinePresenceOfEntity";
import { exploreAdditionalPages } from "../extraction/llm/exploreAdditionalPages";
import { extractAndVerifyEntityData } from "../extraction/llm/extractAndVerifyEntityData";
import getLogger from "../logging";

const logger = getLogger("workers.extractData");

export default createProcessor<ExtractDataJob, ExtractDataProgress>(
  async function extractData(job) {
    let crawlPage = await findPageForJob(job.data.crawlPageId);

    if (crawlPage.extraction.status == ExtractionStatus.CANCELLED) {
      logger.info(
        `Extraction ${crawlPage.extractionId} was cancelled; aborting`
      );
      return;
    }

    await updatePage(crawlPage.id, {
      dataExtractionStartedAt: getSqliteTimestamp(),
    });
    try {
      const dataset = await findDataset(
        job.data.datasetId
      );

      if (!dataset) throw new Error("Could not find dataset");

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
      const entityDef = getCatalogueTypeDefinition(catalogueType);
      const extractionOptions = {
        url: crawlPage.url,
        content,
        screenshot,
        catalogueType,
        logApiCalls: { extractionId: crawlPage.extractionId, datasetId: dataset.id },
      };

      let skipExtraction = false,
        extractedEntityCount = 0;

      if (entityDef.presencePrompt) {
        const result = await determinePresenceOfEntity(
          extractionOptions,
          entityDef
        );
        if (!result.present) {
          skipExtraction = true;
        }
      }

      if (!skipExtraction) {
        for await (const {
          entity,
          textInclusion,
        } of extractAndVerifyEntityData(extractionOptions)) {
          if (entity.items) {
            for (const item of entity.items) {
              await createDataItem(
                crawlPage.id,
                dataset.id,
                item,
                textInclusion
              );
              extractedEntityCount++;
            }
          } else {
            await createDataItem(
              crawlPage.id,
              dataset.id,
              entity,
              textInclusion
            );
            extractedEntityCount++;
          }

          // If we're dealing with large amount of entities in the same doc,
          // check for cancelation every 2 entities
          if (extractedEntityCount % 2 === 0) {
            crawlPage = await findPageForJob(crawlPage.id);
            if (crawlPage.extraction.status == ExtractionStatus.CANCELLED) {
              logger.info(
                `Extraction ${crawlPage.extractionId} was cancelled; aborting`
              );
              return;
            }
          }
        }
      }

      if (extractedEntityCount > 0 && entityDef.exploreDuringExtraction) {
        const pageDepth = await countParentNodesOfCrawlSteps(
          crawlPage.crawlStepId
        );
        if (pageDepth > 8) {
          logger.info(
            `Not adding new pages, crawling new pages limited to 8 levels relative to catalogue root.`
          );
          return;
        }

        exploreAdditionalPages(extractionOptions, catalogueType)
          .then(async ({ data: urls }) => {
            if (!urls?.length) {
              return;
            }

            const stepAndPages = await createStepAndPages({
              extractionId: crawlPage.extractionId,
              step: Step.FETCH_LINKS,
              parentStepId: crawlPage.crawlStepId,
              configuration: {
                pageType: PageType.DETAIL,
              },
              pageType: PageType.DETAIL,
              pages: urls.map((url) => ({ url })),
            });

            await submitJobs(
              Queues.FetchPage,
              stepAndPages.pages.map((page) => ({
                data: {
                  crawlPageId: page.id,
                  extractionId: crawlPage.extractionId,
                  datasetId: job.data.datasetId
                },
                options: {
                  jobId: `fetchPage.${page.id}`,
                  lifo: true,
                  delay: 1500,
                },
              }))
            );
          })
          .catch(logger.error);
      }
    } catch (err) {
      logger.error(inspect(err));
      throw err;
    }
  }
);
