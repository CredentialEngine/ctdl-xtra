import { and, desc, eq, inArray, sql } from "drizzle-orm";
import db from ".";
import {
  crawlPages,
  crawlSteps,
  dataItems,
  datasets,
  catalogues,
  extractions,
} from "./schema";

import {
  CompetencyStructuredData,
  CourseStructuredData,
  LearningProgramStructuredData,
  TextInclusion,
  CredentialStructuredData,
} from "../../../common/types";
import { randomUUID } from "node:crypto";

export async function createDataItem<
  T extends
    | CourseStructuredData
    | LearningProgramStructuredData
    | CompetencyStructuredData
    | CredentialStructuredData,
>(
  crawlPageId: number,
  datasetId: number,
  structuredData: T,
  textInclusion: TextInclusion<T>
) {
  const result = await db
    .insert(dataItems)
    .values({
      uuid: randomUUID(),
      crawlPageId,
      datasetId,
      structuredData,
      textInclusion,
    })
    .returning();
  return result[0];
}

export async function findOrCreateDataset(
  catalogueId: number,
  extractionId: number
) {
  await db
    .insert(datasets)
    .values({ catalogueId, extractionId })
    .onConflictDoNothing();
  return db.query.datasets.findFirst({
    where: (datasets, { eq }) =>
      and(
        eq(datasets.catalogueId, catalogueId),
        eq(datasets.extractionId, extractionId)
      ),
  });
}

export async function findCataloguesWithData(
  limit: number = 20,
  offset: number = 0
) {
  const totalItems = (
    await db
      .select({
        totalCatalogueIds: sql<number>`count(distinct catalogue_id)`,
      })
      .from(datasets)
  )[0].totalCatalogueIds;

  const catalogueIdsQuery = db
    .selectDistinct({
      catalogueId: datasets.catalogueId,
    })
    .from(datasets)
    .limit(limit)
    .offset(offset);

  const items = await db.query.catalogues.findMany({
    where: (catalogues, { inArray }) =>
      inArray(catalogues.id, catalogueIdsQuery),
  });
  return { totalItems, items };
}

export async function getItemsCount(extractionId: number) {
  return (
    await db
      .select({ count: sql<number>`count(*)` })
      .from(datasets)
      .innerJoin(dataItems, eq(datasets.id, dataItems.datasetId))
      .where(eq(datasets.extractionId, extractionId))
  )[0].count;
}

export async function findDatasets(
  catalogueId: number,
  limit: number = 20,
  offset: number = 0
) {
  const totalItems = (
    await db
      .select({ count: sql<number>`count(*)` })
      .from(datasets)
      .where(eq(datasets.catalogueId, catalogueId))
  )[0].count;

  let datasetsQuery = db
    .select({
      id: datasets.extractionId,
      createdAt: datasets.createdAt,
    })
    .from(datasets)
    .where(eq(datasets.catalogueId, catalogueId))
    .orderBy(desc(datasets.createdAt))
    .limit(limit)
    .offset(offset)
    .$dynamic();

  const items = await Promise.all(
    (await datasetsQuery).map(async (dataset) => ({
      ...dataset,
      itemsCount: await getItemsCount(dataset.id),
    }))
  );

  return { totalItems, items };
}

export async function findDataItems(
  extractionId: number,
  limit: number = 20,
  offset: number = 0,
  skipTotals = false
) {
  const items = await db
    .select({
      id: dataItems.id,
      uuid: dataItems.uuid,
      structuredData: dataItems.structuredData,
      textInclusion: dataItems.textInclusion,
      url: crawlPages.url,
    })
    .from(dataItems)
    .innerJoin(crawlPages, eq(crawlPages.id, dataItems.crawlPageId))
    .innerJoin(crawlSteps, eq(crawlSteps.id, crawlPages.crawlStepId))
    .innerJoin(extractions, eq(extractions.id, crawlSteps.extractionId))
    .where(eq(crawlSteps.extractionId, extractionId))
    .limit(limit)
    .offset(offset);

  if (skipTotals) {
    return { items };
  }

  const totalItems = await getItemsCount(extractionId);
  return { totalItems, items };
}

export async function findDataItemsWithSameUrlAcrossExtractions(
  extractionIds: number[],
  url: string
) {
  if (!extractionIds || extractionIds.length === 0) return [];

  const items = await db
    .select({
      id: dataItems.id,
      uuid: dataItems.uuid,
      structuredData: dataItems.structuredData,
      textInclusion: dataItems.textInclusion,
      url: crawlPages.url,
      extractionId: datasets.extractionId,
      catalogueType: catalogues.catalogueType,
    })
    .from(dataItems)
    .innerJoin(crawlPages, eq(crawlPages.id, dataItems.crawlPageId))
    .innerJoin(datasets, eq(datasets.id, dataItems.datasetId))
    .innerJoin(catalogues, eq(catalogues.id, datasets.catalogueId))
    .where(
      and(
        inArray(datasets.extractionId, extractionIds),
        eq(crawlPages.url, url)
      )
    )
    .orderBy(crawlPages.url, datasets.extractionId);

  return items;
}
