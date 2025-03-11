import {
  createProcessor,
  FetchPageJob,
  FetchPageProgress,
  Queues,
  submitJob,
  submitJobs,
} from ".";
import {
  CatalogueType,
  ExtractionStatus,
  FetchFailureReason,
  PageStatus,
  PageType,
  PaginationConfiguration,
  RecipeConfiguration,
  Step,
} from "../../../common/types";
import {
  createStepAndPages,
  findPageByUrl,
  findPageForJob,
  updateExtraction,
  updatePage,
} from "../data/extractions";
import {
  readMarkdownContent,
  readScreenshot,
  storeContent,
  storeScreenshot,
} from "../data/schema";
import { fetchBrowserPage, simplifiedMarkdown } from "../extraction/browser";
import { detectPageCount } from "../extraction/llm/detectPageCount";
import { createUrlExtractor } from "../extraction/llm/detectUrlRegexp";

const constructPaginatedUrls = (configuration: PaginationConfiguration) => {
  const urls = [];
  if (configuration.urlPatternType == "offset") {
    // TODO: implement offset logic
    return [];
  } else if (configuration.urlPatternType == "page_num") {
    for (let i = 1; i <= configuration.totalPages; i++) {
      urls.push(configuration.urlPattern.replace("{page_num}", i.toString()));
    }
    return urls;
  } else {
    throw new Error("Unknown pagination pattern type");
  }
};

async function enqueueExtraction(
  crawlPage: Awaited<ReturnType<typeof findPageForJob>>
) {
  console.log(`Enqueuing extraction for page ${crawlPage.url}`);
  return submitJob(
    Queues.ExtractData,
    { crawlPageId: crawlPage.id },
    `extractData.${crawlPage.id}`
  );
}

async function enqueuePages(
  configuration: RecipeConfiguration,
  crawlPage: Awaited<ReturnType<typeof findPageForJob>>,
  catalogueType: CatalogueType
) {
  console.log(`Enqueuing page fetches for page ${crawlPage.url}`);

  const pageCount = await detectPageCount(
    {
      content: await readMarkdownContent(
        crawlPage.extractionId,
        crawlPage.crawlStepId,
        crawlPage.id
      ),
      screenshot: await readScreenshot(
        crawlPage.extractionId,
        crawlPage.crawlStepId,
        crawlPage.id
      ),
      logApiCalls: { extractionId: crawlPage.extractionId },
      url: crawlPage.url,
      catalogueType,
    },
    configuration.pagination!.urlPattern,
    configuration.pagination!.urlPatternType
  );

  if (!pageCount) {
    throw new Error("Couldn't determine page count for paginated page");
  }

  const updatedPagination = {
    ...configuration.pagination!,
    totalPages: pageCount.totalPages,
  };

  const pageUrls = constructPaginatedUrls(updatedPagination);

  if (!pageUrls.length) {
    console.log(`No paginated pages found for page ${crawlPage.url}`);
    return;
  }

  const stepAndPages = await createStepAndPages({
    extractionId: crawlPage.extractionId,
    step: Step.FETCH_PAGINATED,
    parentStepId: crawlPage.crawlStepId,
    configuration,
    pageType: configuration.pageType,
    pages: pageUrls.map((url) => ({ url })),
  });

  await submitJobs(
    Queues.FetchPage,
    stepAndPages.pages.map((page) => ({
      data: { crawlPageId: page.id },
      options: { jobId: `fetchPage.${page.id}`, lifo: true, delay: 1500 },
    }))
  );
}

async function processLinks(
  configuration: RecipeConfiguration,
  crawlPage: Awaited<ReturnType<typeof findPageForJob>>
) {
  console.log(`Processing links for page ${crawlPage.url}`);

  const regexp = new RegExp(configuration.linkRegexp!, "g");
  const extractor = createUrlExtractor(regexp);
  const content = await readMarkdownContent(
    crawlPage.extractionId,
    crawlPage.crawlStepId,
    crawlPage.id
  );
  const extractedUrls = await extractor(crawlPage.url, content);
  let urls = [];

  for (const url of extractedUrls) {
    const page = await findPageByUrl(crawlPage.extractionId, url);
    if (!page) {
      urls.push(url);
    } else {
      console.log(`Skipping ${url} because it has already been fetched`);
    }
  }

  if (!urls.length) {
    console.log(`No URLs found for page ${crawlPage.url}`);
    return;
  }

  const stepAndPages = await createStepAndPages({
    extractionId: crawlPage.extractionId,
    step: Step.FETCH_LINKS,
    parentStepId: crawlPage.crawlStepId,
    configuration: configuration.links!,
    pageType: configuration.links!.pageType,
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
}

const processNextStep = async (
  crawlPage: Awaited<ReturnType<typeof findPageForJob>>
) => {
  const configuration = crawlPage.crawlStep
    .configuration as RecipeConfiguration;
  const currentStep = crawlPage.crawlStep.step;
  const catalogueType = crawlPage.extraction.recipe.catalogue
    .catalogueType as CatalogueType;

  if (configuration.pagination && currentStep != Step.FETCH_PAGINATED) {
    return enqueuePages(configuration, crawlPage, catalogueType);
  }

  if (configuration.pageType == PageType.DETAIL) {
    return enqueueExtraction(crawlPage);
  }

  if (!configuration.links) {
    throw new Error(
      "Don't know what to do - no links and no matching page type"
    );
  }

  processLinks(configuration, crawlPage);
};

export default createProcessor<FetchPageJob, FetchPageProgress>(
  async function fetchPage(job) {
    const crawlPage = await findPageForJob(job.data.crawlPageId);

    if (crawlPage.extraction.status == ExtractionStatus.CANCELLED) {
      console.log(
        `Extraction ${crawlPage.extractionId} was cancelled; aborting`
      );
      return;
    }

    if (crawlPage.crawlStep.step == Step.FETCH_ROOT) {
      await updateExtraction(crawlPage.extractionId, {
        status: ExtractionStatus.IN_PROGRESS,
      });
    }

    try {
      console.log(`Loading ${crawlPage.url} for page ${crawlPage.url}`);
      await updatePage(crawlPage.id, { status: PageStatus.IN_PROGRESS });
      const page = await fetchBrowserPage(crawlPage.url);
      if (page.status == 404) {
        await updatePage(crawlPage.id, {
          status: PageStatus.ERROR,
          fetchFailureReason: {
            responseStatus: page.status,
            reason: "404 Not found",
          },
        });
        return;
      }
      if (!page.content) {
        throw new Error(`Could not fetch URL ${crawlPage.url}`);
      }
      const markdownContent = await simplifiedMarkdown(page.content);
      crawlPage.content = await storeContent(
        crawlPage.extractionId,
        crawlPage.crawlStepId,
        crawlPage.id,
        page.content,
        markdownContent
      );
      crawlPage.screenshot = await storeScreenshot(
        crawlPage.extractionId,
        crawlPage.crawlStepId,
        crawlPage.id,
        page.screenshot
      );
      await updatePage(crawlPage.id, {
        content: crawlPage.content,
        screenshot: crawlPage.screenshot,
      });
      await processNextStep(crawlPage);
      await updatePage(crawlPage.id, {
        status: PageStatus.SUCCESS,
      });
    } catch (err) {
      const failureReason: FetchFailureReason = {
        reason:
          err instanceof Error
            ? err.message || `Generic failure: ${err.constructor.name}`
            : `Unknown error: ${String(err)}`,
      };
      await updatePage(crawlPage.id, {
        status: PageStatus.ERROR,
        fetchFailureReason: failureReason,
      });
      throw err;
    }
  }
);
