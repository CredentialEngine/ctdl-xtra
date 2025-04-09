import { inspect } from "util";
import { createProcessor, ExtractDataJob, ExtractDataProgress, Queues, submitJobs } from ".";
import { createDataItem, findOrCreateDataset } from "../data/datasets";
import { countParentNodesOfCrawlSteps, createStepAndPages, findPageForJob, updatePage } from "../data/extractions";
import {
  getSqliteTimestamp,
  readMarkdownContent,
  readScreenshot,
} from "../data/schema";

import { CatalogueType, ExtractionStatus, PageType, Step, TextInclusion } from "../../../common/types";
import { extractAndVerifyEntityData } from "../extraction/llm/extractAndVerifyEntityData";
import { getCatalogueTypeDefinition } from "../extraction/catalogueTypes";
import { exploreAdditionalPages } from "../extraction/llm/exploreAdditionalPages";
import { determinePresenceOfEntity } from "../extraction/llm/determinePresenceOfEntity";

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
      const entityDef = getCatalogueTypeDefinition(catalogueType);
      const extractionOptions = {
        url: crawlPage.url,
        content,
        screenshot,
        catalogueType,
        logApiCalls: { extractionId: crawlPage.extractionId },
      };

      let skipExtraction = false, extractedData: { entity: any, textInclusion: TextInclusion<any> }[] = [];

      if (entityDef.presencePrompt) {
        const result = await determinePresenceOfEntity(extractionOptions, entityDef);
        if (!result.present) {
          skipExtraction = true;
        }
      }

      if (!skipExtraction) {
        extractedData = await extractAndVerifyEntityData(extractionOptions);
        for (const { entity, textInclusion } of extractedData) {
          if (entity.items) {
            for (const item of entity.items) {
              await createDataItem(crawlPage.id, dataset.id, item, textInclusion);
            }
          } else {
            await createDataItem(crawlPage.id, dataset.id, entity, textInclusion);
          }
        }
      }

      if (extractedData?.length && entityDef.exploreDuringExtraction) {
        const pageDepth = await countParentNodesOfCrawlSteps(crawlPage.crawlStepId);
        if (pageDepth > 8) {
          console.log(`Not adding new pages, crawling new pages limited to 8 levels relative to catalogue root.`);
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
                data: { crawlPageId: page.id },
                options: {
                  jobId: `fetchPage.${page.id}`,
                  lifo: true,
                  delay: 1500,
                },
              }))
            );
          })
          .catch(console.log);

      }
    } catch (err) {
      console.log(inspect(err));
      throw err;
    }
  }
);
