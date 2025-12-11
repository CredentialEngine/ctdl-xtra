import { and, desc, eq, sql } from "drizzle-orm";
import db from ".";
import {
  crawlPages,
  dataItems,
  datasets
} from "./schema";

import {
  CompetencyStructuredData,
  CourseStructuredData,
  CredentialStructuredData,
  LearningProgramStructuredData,
  TextInclusion,
} from "../../../common/types";
import { findExtractionById } from "./extractions";

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
      crawlPageId,
      datasetId,
      structuredData,
      textInclusion,
    })
    .returning();
  return result[0];
}

export async function createDataset(
  extractionId: number
) {
  const extraction = await findExtractionById(extractionId);
  if (!extraction) {
    throw new Error("Extraction could not be found");
  }
  const result = await db
    .insert(datasets)
    .values({ catalogueId: extraction.recipe.catalogueId, extractionId })
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

export async function getItemsCount(datasetId: number) {
  return (
    await db
      .select({ count: sql<number>`count(*)` })
      .from(dataItems)
      .where(eq(dataItems.datasetId, datasetId))
  )[0].count;
}

export async function findDataset(id: number) {
  return db.query.datasets.findFirst({
    where: (datasets, { eq }) => eq(datasets.id, id),
    with: {
      extraction: {
        with: {
          recipe: {
            with: {
              catalogue: {
                with: {
                  institution: true,
                },
              },
            },
          },
        }
      },
    },
  });
}

export async function findLatestDataset(extractionId: number) {
  return db.query.datasets.findFirst({
    where: eq(datasets.extractionId, extractionId),
    orderBy: desc(datasets.createdAt)
  });
}

export async function findCatalogueDatasets(
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
      id: datasets.id,
      extractionId: datasets.extractionId,
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

export async function findExtractionDatasets(extractionId: number) {
  return db.query.datasets.findMany({
    where: (datasets, { eq }) => eq(datasets.extractionId, extractionId),
    orderBy: (datasets, { desc }) => desc(datasets.createdAt),
  });
}

export async function findDataItems(
  datasetId: number,
  limit: number = 20,
  offset: number = 0,
  skipTotals = false
) {
  const items = await db
    .select({
      id: dataItems.id,
      structuredData: dataItems.structuredData,
      textInclusion: dataItems.textInclusion,
      url: crawlPages.url,
    })
    .from(dataItems)
    .innerJoin(crawlPages, eq(crawlPages.id, dataItems.crawlPageId))
    .where(eq(dataItems.datasetId, datasetId))
    .limit(limit)
    .offset(offset);

  if (skipTotals) {
    return { items };
  }

  const totalItems = await getItemsCount(datasetId);
  return { totalItems, items };
}
