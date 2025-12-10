import { and, desc, eq, ilike, or, sql } from "drizzle-orm";
import { CatalogueType } from "../../../common/types";
import db from "../data";
import { catalogues, extractions, recipes } from "../data/schema";

export interface FindCatalogueOptions {
  limit?: number;
  offset?: number;
  catalogueType?: CatalogueType;
  search?: string;
  institutionId?: number;
}

export async function getCatalogueCount(
  options: Omit<FindCatalogueOptions, "limit" | "offset">
) {
  const result = await db
    .select({ count: sql<number>`count(*)` })
    .from(catalogues)
    .where(
      and(
        options.institutionId
          ? eq(catalogues.institutionId, options.institutionId)
          : undefined,
        options.catalogueType
          ? eq(catalogues.catalogueType, options.catalogueType)
          : undefined,
        options.search
          ? or(
              ilike(catalogues.name, `%${options.search}%`),
              ilike(catalogues.url, `%${options.search}%`)
            )
          : undefined
      )
    );
  return result[0].count;
}

export async function findCatalogueById(id: number) {
  const result = await db.query.catalogues.findFirst({
    where: (catalogues, { eq }) => eq(catalogues.id, id),
    with: {
      recipes: true,
      institution: true,
    },
  });
  if (result) {
    result.recipes = result.recipes.sort((a, b) => {
      if (a.isDefault === b.isDefault) {
        const aCreated = +new Date(a.createdAt);
        const bCreated = +new Date(b.createdAt);
        // isDefault is the same on both items, so we need to sort by createdAt
        if (aCreated < bCreated) return 1; // desc
        if (aCreated > bCreated) return -1; // desc
        return 0;
      }
      // We want isDefault to be true first, so when a is true and b is false, a should come first.
      if (a.isDefault) return -1;
      return 1;
    });
  }
  return result;
}

export async function findCatalogue(url: string, catalogueType: CatalogueType) {
  return db.query.catalogues.findFirst({
    where: (catalogues, { eq }) =>
      and(eq(catalogues.url, url), eq(catalogues.catalogueType, catalogueType)),
  });
}

export async function findLatestExtractionsForCatalogue(catalogueId: number) {
  const catExtractions = await db
    .select()
    .from(extractions)
    .innerJoin(recipes, eq(extractions.recipeId, recipes.id))
    .where(eq(recipes.catalogueId, catalogueId))
    .orderBy(desc(extractions.createdAt))
    .limit(10);
  return catExtractions.map((e) => e.extractions);
}

export async function findCatalogues(options: FindCatalogueOptions) {
  const { limit = 20, offset = 0, catalogueType, search } = options;
  return db.query.catalogues.findMany({
    limit,
    offset,
    with: {
      recipes: true,
      institution: true,
    },
    where: and(
      options.institutionId
        ? eq(catalogues.institutionId, options.institutionId)
        : undefined,
      catalogueType ? eq(catalogues.catalogueType, catalogueType) : undefined,
      search
        ? or(
            ilike(catalogues.name, `%${search}%`),
            ilike(catalogues.url, `%${search}%`)
          )
        : undefined
    ),
  });
}

export async function createCatalogue(
  name: string,
  url: string,
  institutionId: number,
  catalogueType?: CatalogueType,
  thumbnailUrl?: string
) {
  const result = await db
    .insert(catalogues)
    .values({ name, url, thumbnailUrl, catalogueType, institutionId })
    .returning();
  return result[0];
}

export async function destroyCatalogue(id: number) {
  return db.delete(catalogues).where(eq(catalogues.id, id));
}

export async function updateCatalogueInstitution(
  id: number,
  institutionId: number
) {
  const result = await db
    .update(catalogues)
    .set({ institutionId })
    .where(eq(catalogues.id, id))
    .returning();
  return result[0];
}
