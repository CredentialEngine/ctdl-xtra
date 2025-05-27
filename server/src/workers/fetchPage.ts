import { v4 as uuidv4 } from "uuid";
import {
  createProcessor,
  DelayOptions,
  FetchPageJob,
  FetchPageProgress,
  getRedisConnection,
  JobWithProgress,
  Queues,
  submitJob,
  submitJobs,
  submitJobWithOpts,
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
import { findRule, isUrlAllowedForRule } from "../extraction/robotsParser";
import getLogger from "../logging";

const logger = getLogger("workers.fetchPage");
const redis = getRedisConnection();

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
  logger.info(`Enqueuing extraction for page ${crawlPage.url}`);
  return submitJob(
    Queues.ExtractData,
    { crawlPageId: crawlPage.id, extractionId: crawlPage.extractionId },
    `extractData.${crawlPage.id}`
  );
}

async function enqueuePages(
  configuration: RecipeConfiguration,
  crawlPage: Awaited<ReturnType<typeof findPageForJob>>,
  catalogueType: CatalogueType,
  delayOptions: DelayOptions
) {
  logger.info(`Enqueuing page fetches for page ${crawlPage.url}`);

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
    logger.info(`No paginated pages found for page ${crawlPage.url}`);
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
      data: { crawlPageId: page.id, extractionId: crawlPage.extractionId },
      options: { jobId: `fetchPage.${page.id}`, lifo: true },
    })),
    delayOptions
  );
}

async function processLinks(
  configuration: RecipeConfiguration,
  crawlPage: Awaited<ReturnType<typeof findPageForJob>>,
  delayOptions: DelayOptions
) {
  logger.info(`Processing links for page ${crawlPage.url}`);

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
      logger.info(`Skipping ${url} because it has already been fetched`);
    }
  }

  if (!urls.length) {
    logger.info(`No URLs found for page ${crawlPage.url}`);
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
      data: {
        crawlPageId: page.id,
        extractionId: crawlPage.extractionId,
      },
      options: {
        jobId: `fetchPage.${page.id}`,
        lifo: true,
      },
    })),
    delayOptions
  );
}

const processNextStep = async (
  crawlPage: Awaited<ReturnType<typeof findPageForJob>>,
  delayOptions: DelayOptions
) => {
  const configuration = crawlPage.crawlStep
    .configuration as RecipeConfiguration;
  const currentStep = crawlPage.crawlStep.step;
  const catalogueType = crawlPage.extraction.recipe.catalogue
    .catalogueType as CatalogueType;

  if (configuration.pagination && currentStep != Step.FETCH_PAGINATED) {
    return enqueuePages(configuration, crawlPage, catalogueType, delayOptions);
  }

  if (configuration.pageType == PageType.DETAIL) {
    return enqueueExtraction(crawlPage);
  }

  if (!configuration.links) {
    throw new Error(
      "Don't know what to do - no links and no matching page type"
    );
  }

  processLinks(configuration, crawlPage, delayOptions);
};

const performJob = async (
  job: JobWithProgress<FetchPageJob, FetchPageProgress>,
  crawlPage: Awaited<ReturnType<typeof findPageForJob>>,
  delayOptions: DelayOptions
) => {
  if (crawlPage.extraction.status == ExtractionStatus.CANCELLED) {
    logger.info(`Extraction ${crawlPage.extractionId} was cancelled; aborting`);
    return;
  }

  if (crawlPage.crawlStep.step == Step.FETCH_ROOT) {
    await updateExtraction(crawlPage.extractionId, {
      status: ExtractionStatus.IN_PROGRESS,
    });
  }

  try {
    logger.info(`Loading ${crawlPage.url}`);
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
    await processNextStep(crawlPage, delayOptions);
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
};

export default createProcessor<FetchPageJob, FetchPageProgress>(
  async (job: JobWithProgress<FetchPageJob, FetchPageProgress>) => {
    const crawlPage = await findPageForJob(job.data.crawlPageId);

    const delayOptions: DelayOptions = {
      delayInterval: 3000,
      startWithDelay: 0,
    };

    const robotsTxt = crawlPage.extraction.recipe.acknowledgedSkipRobotsTxt
      ? undefined
      : crawlPage.extraction.recipe.robotsTxt || undefined;

    if (robotsTxt) {
      const robotsRule = findRule(robotsTxt, crawlPage.url);
      if (
        robotsRule &&
        isUrlAllowedForRule(robotsRule, crawlPage.url) &&
        robotsRule.crawlDelay &&
        robotsRule.crawlDelay > 0
      ) {
        delayOptions.delayInterval = robotsRule.crawlDelay * 1000;
      }
    }

    const domain = new URL(crawlPage.url).hostname;
    const lockKey = `crawl-lock:${domain}`;

    // Attempt to acquire the lock atomically
    const lockAcquired = await redis.set(
      lockKey,
      "locked",
      "PX",
      delayOptions.delayInterval,
      "NX"
    );

    if (!lockAcquired) {
      // Lock is held by another worker
      const remainingCooldownMillis = await redis.pttl(lockKey);
      const delay =
        remainingCooldownMillis > 0
          ? remainingCooldownMillis
          : delayOptions.delayInterval;

      logger.trace(
        `Domain ${domain} locked. Re-queuing ${crawlPage.url} with delay ${delay}ms.`
      );
      return submitJobWithOpts(Queues.FetchPage, job.data, {
        ...job.opts,
        jobId: `${job.opts.jobId}.delayed.${uuidv4()}`,
        delay: delay,
      });
    }

    logger.info(`Processing URL: ${crawlPage.url} for domain ${domain}`);
    return performJob(job, crawlPage, delayOptions);
  }
);
