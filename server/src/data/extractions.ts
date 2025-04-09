import { and, eq, isNotNull } from "drizzle-orm";
import { sql } from "drizzle-orm/sql/sql";
import { SQLiteUpdateSetSource } from "drizzle-orm/sqlite-core";
import db from "../data";
import {
  crawlPages,
  crawlSteps,
  dataItems,
  extractionLogs,
  extractions,
  modelApiCalls,
} from "../data/schema";

import {
  LogLevel,
  PageStatus,
  PageType,
  Provider,
  ProviderModel,
  RecipeConfiguration,
  Step,
} from "../../../common/types";

export async function createExtraction(recipeId: number) {
  const result = await db
    .insert(extractions)
    .values({
      recipeId,
    })
    .returning();
  return result[0];
}

export async function updateExtraction(
  extractionId: number,
  updateAttributes: SQLiteUpdateSetSource<typeof extractions>
) {
  const result = await db
    .update(extractions)
    .set(updateAttributes)
    .where(eq(extractions.id, extractionId))
    .returning();
  return result[0];
}

export async function createExtractionLog(
  extractionId: number,
  log: string,
  logLevel: LogLevel = LogLevel.INFO
) {
  const result = await db
    .insert(extractionLogs)
    .values({
      extractionId,
      log,
      logLevel,
    })
    .returning();
  return result[0];
}

export async function getExtractionCount() {
  const result = await db
    .select({ count: sql<number>`count(*)` })
    .from(extractions);
  return result[0].count;
}

export async function getPageCount(stepId: number) {
  const result = await db
    .select({ count: sql<number>`count(*)` })
    .from(crawlPages)
    .where(eq(crawlPages.crawlStepId, stepId));
  return result[0].count;
}

export async function findExtractions(limit: number = 20, offset?: number) {
  offset = offset || 0;
  return db.query.extractions.findMany({
    limit,
    offset,
    with: {
      recipe: {
        with: {
          catalogue: true,
        },
      },
    },
    orderBy: (extractions, { desc }) => desc(extractions.createdAt),
  });
}

export async function findExtractionById(id: number) {
  return db.query.extractions.findFirst({
    where: (catalogues, { eq }) => eq(catalogues.id, id),
    with: {
      recipe: {
        with: {
          catalogue: true,
        },
      },
      crawlSteps: {
        orderBy: (e) => e.createdAt,
      },
    },
  });
}

export async function findExtractionForDetailPage(id: number) {
  const result = await db.query.extractions.findFirst({
    where: (catalogues, { eq }) => eq(catalogues.id, id),
    with: {
      recipe: {
        with: {
          catalogue: true,
        },
      },
      crawlSteps: {
        orderBy: (e) => e.createdAt,
        extras: {
          itemCount: sql<number>`0`.as("item_count"),
        },
      },
      logs: {
        orderBy: (e) => e.createdAt,
      },
    },
  });
  if (result) {
    for (const step of result.crawlSteps) {
      step.itemCount = await getPageCount(step.id);
    }
  }
  return result;
}

export async function findLogs(
  extractionId: number,
  limit: number = 20,
  offset?: number
) {
  return db.query.extractionLogs.findMany({
    where: (logs, { eq }) => eq(logs.extractionId, extractionId),
    limit,
    offset,
    orderBy: (logs, { desc }) => desc(logs.createdAt),
  });
}

export async function getLogCount(extractionId: number) {
  const result = await db
    .select({ count: sql<number>`count(*)` })
    .from(extractionLogs)
    .where(eq(extractionLogs.extractionId, extractionId));
  return result[0].count;
}

export async function findStep(stepId: number) {
  const result = await db.query.crawlSteps.findFirst({
    where: (steps, { eq }) => eq(steps.id, stepId),
  });
  return result;
}

export async function findPages(stepId: number) {
  const result = await db.query.crawlPages.findMany({
    where: (crawlPages, { eq }) => eq(crawlPages.crawlStepId, stepId),
    orderBy: (crawlPages) => crawlPages.createdAt,
  });
  return result;
}

export async function findPagesPaginated(
  stepId: number,
  limit: number = 20,
  offset?: number
) {
  offset = offset || 0;
  const result = await db.query.crawlPages.findMany({
    columns: {
      content: false,
      screenshot: false,
    },
    limit,
    offset,
    where: (crawlPages, { eq }) => eq(crawlPages.crawlStepId, stepId),
    orderBy: (crawlPages) => crawlPages.createdAt,
  });
  return result;
}

export async function findPage(crawlPageId: number) {
  const result = await db.query.crawlPages.findFirst({
    where: (crawlPages, { eq }) => eq(crawlPages.id, crawlPageId),
    with: {
      crawlStep: true,
    },
  });
  return result;
}

export async function findPageForJob(crawlPageId: number) {
  const result = await db.query.crawlPages.findFirst({
    where: (crawlPages, { eq }) => eq(crawlPages.id, crawlPageId),
    with: {
      extraction: {
        with: {
          recipe: {
            with: {
              catalogue: true,
            },
          },
        },
      },
      crawlStep: true,
    },
  });
  if (!result) {
    throw new Error(`Step item ${crawlPageId} not found`);
  }
  return result;
}

export async function findPageByUrl(extractionId: number, url: string) {
  const result = await db.query.crawlPages.findFirst({
    where: (crawlPages, { eq, and }) =>
      and(eq(crawlPages.url, url), eq(crawlPages.extractionId, extractionId)),
    with: {
      crawlStep: {
        with: {
          extraction: true,
        },
      },
    },
  });
  return result;
}
export async function findCrawlPageByUrl(url: string) {
  const result = await db.query.crawlPages.findFirst({
    where: (crawlPages, { eq, and }) =>
      eq(crawlPages.url, url),
    with: {
      crawlStep: true,
    },
  });
  return result;
}

export interface CreateStepOptions {
  extractionId: number;
  step: Step;
  parentStepId?: number;
  configuration: RecipeConfiguration;
}

export async function createStep({
  extractionId,
  step,
  parentStepId,
  configuration,
}: CreateStepOptions) {
  const result = await db
    .insert(crawlSteps)
    .values({
      extractionId,
      step,
      parentStepId,
      configuration,
    })
    .returning();
  return result[0];
}

export interface CreatePageOptions {
  crawlStepId: number;
  step: Step;
  extractionId: number;
  url: string;
  pageType: PageType;
  content?: string;
  screenshot?: string;
  status?: PageStatus;
}

export async function createPage({
  crawlStepId,
  step,
  extractionId,
  url,
  content,
  pageType,
  status,
  screenshot,
}: CreatePageOptions) {
  const result = await db
    .insert(crawlPages)
    .values({
      crawlStepId,
      step,
      extractionId,
      content,
      pageType,
      url,
      screenshot,
      status: status || PageStatus.WAITING,
    })
    .returning();
  return result[0];
}

export interface CreateStepAndPagesOptions {
  extractionId: number;
  step: Step;
  parentStepId?: number;
  configuration: RecipeConfiguration;
  pageType: PageType;
  pages: {
    url: string;
  }[];
}

export async function createStepAndPages(
  createOptions: CreateStepAndPagesOptions
) {
  return await db.transaction(async (tx) => {
    const step = (
      await tx
        .insert(crawlSteps)
        .values({
          extractionId: createOptions.extractionId,
          step: createOptions.step,
          parentStepId: createOptions.parentStepId,
          configuration: createOptions.configuration,
        })
        .returning()
    )[0];
    const pages = await tx
      .insert(crawlPages)
      .values(
        createOptions.pages.map((pageCreateOptions) => ({
          crawlStepId: step.id,
          step: createOptions.step,
          extractionId: createOptions.extractionId,
          url: pageCreateOptions.url,
          pageType: createOptions.pageType,
        }))
      )
      .returning();
    return {
      step,
      pages,
    };
  });
}

export async function countParentNodesOfCrawlSteps(crawlStepId: number): Promise<number> {
  const result = await db.execute(
    sql`
      WITH RECURSIVE ancestors AS (
        SELECT id, parent_step_id FROM crawl_steps WHERE id = ${crawlStepId}
        UNION ALL
        SELECT c.id, c.parent_step_id FROM crawl_steps c
        INNER JOIN ancestors a ON c.id = a.parent_step_id
      )
      SELECT COUNT(*) FROM ancestors;
    `
  );

  return Number(result.rows[0].count);
}

export async function getApiCallSummary(extractionId: number) {
  const result = await db
    .select({
      callSite: modelApiCalls.callSite,
      model: modelApiCalls.model,
      totalInputTokens: sql<number>`SUM(${modelApiCalls.input_token_count})`,
      totalOutputTokens: sql<number>`SUM(${modelApiCalls.output_token_count})`,
    })
    .from(modelApiCalls)
    .where(eq(modelApiCalls.extractionId, extractionId))
    .groupBy(modelApiCalls.callSite, modelApiCalls.model);

  return result;
}

export async function createModelApiCallLog(
  extractionId: number,
  provider: Provider,
  model: ProviderModel,
  callSite: string,
  inputTokenCount: number,
  outputTokenCount: number
) {
  const result = await db
    .insert(modelApiCalls)
    .values({
      extractionId,
      provider,
      model,
      callSite,
      input_token_count: inputTokenCount,
      output_token_count: outputTokenCount,
    })
    .returning();
  return result[0];
}

export async function updatePage(
  crawlPageId: number,
  updateAttributes: SQLiteUpdateSetSource<typeof crawlPages>
) {
  const result = await db
    .update(crawlPages)
    .set(updateAttributes)
    .where(eq(crawlPages.id, crawlPageId))
    .returning();
  return result[0];
}

export async function getStepStats(crawlStepId: number) {
  return await db
    .select({
      crawlPageId: crawlPages.id,
      status: crawlPages.status,
      dataExtractionStartedAt: crawlPages.dataExtractionStartedAt,
      dataItemCount: sql<number>`COUNT(${dataItems.id})::integer`,
    })
    .from(crawlPages)
    .leftJoin(dataItems, eq(dataItems.crawlPageId, crawlPages.id))
    .where(
      and(
        eq(crawlPages.crawlStepId, crawlStepId),
        eq(crawlPages.pageType, PageType.DETAIL)
      )
    )
    .groupBy(
      crawlPages.id,
      crawlPages.status,
      crawlPages.dataExtractionStartedAt
    );
}

export async function findFailedAndNoDataPageIds(crawlStepId: number) {
  // Pages where the download failed
  const failedIds = await db
    .select({
      id: crawlPages.id,
    })
    .from(crawlPages)
    .where(
      and(
        eq(crawlPages.crawlStepId, crawlStepId),
        eq(crawlPages.status, PageStatus.ERROR)
      )
    );

  // Pages where a data extraction was attempted, but no data was found
  const noDataIds = await db
    .select({
      id: crawlPages.id,
    })
    .from(crawlPages)
    .leftJoin(dataItems, eq(dataItems.crawlPageId, crawlPages.id))
    .where(
      and(
        eq(crawlPages.crawlStepId, crawlStepId),
        eq(crawlPages.status, PageStatus.SUCCESS),
        eq(crawlPages.pageType, PageType.DETAIL),
        isNotNull(crawlPages.dataExtractionStartedAt)
      )
    )
    .groupBy(crawlPages.id)
    .having(sql`count(${dataItems.id}) = 0`);

  return [...new Set(failedIds.concat(noDataIds).map((p) => p.id))];
}

export async function destroyExtraction(id: number) {
  return db.delete(extractions).where(eq(extractions.id, id));
}
