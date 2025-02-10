import { desc, eq, sql, and, inArray, } from "drizzle-orm";
import db from "../data";
import { catalogues, extractions, recipes } from "../data/schema";

export async function getCatalogueCount() {
  const result = await db
    .select({ count: sql<number>`count(*)` })
    .from(catalogues);
  return result[0].count;
}

export async function findCatalogueById(id: number) {
  const result = await db.query.catalogues.findFirst({
    where: (catalogues, { eq }) => eq(catalogues.id, id),
    with: {
      recipes: true,
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

export async function findCatalogueByUrl(url: string, orgIds: number[]) {
  return db.query.catalogues.findFirst({
    where: and(
      eq(catalogues.url, url),
      inArray(catalogues.orgId, orgIds),
    ),
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

export async function findCatalogues(orgId: number, limit: number = 20, offset?: number) {
  offset = offset || 0;
  return db.query.catalogues.findMany({
    where: eq(catalogues.orgId, orgId),
    limit,
    offset,
    with: {
      recipes: true,
    },
  });
}

export async function createCatalogue(
  name: string,
  url: string,
  orgId: number,
  thumbnailUrl?: string,
) {
  const result = await db
    .insert(catalogues)
    .values({ name, url, thumbnailUrl, orgId })
    .returning();
  return result[0];
}

export async function destroyCatalogue(id: number) {
  return db.delete(catalogues).where(eq(catalogues.id, id));
}
