import { InferSelectModel, eq, and, or, ilike, sql } from "drizzle-orm";
import { SQLiteUpdateSetSource } from "drizzle-orm/sqlite-core";
import db from "../data";
import { recipes, catalogues, extractions } from "../data/schema";

import {
  PageType,
  RecipeConfiguration,
  RecipeDetectionStatus,
  CatalogueType,
} from "../../../common/types";
import { RobotsTxt } from "../extraction/robotsParser";

export type Recipe = Omit<InferSelectModel<typeof recipes>, "configuration"> & {
  configuration?: RecipeConfiguration;
  robotsTxt?: RobotsTxt;
  acknowledgedSkipRobotsTxt?: boolean;
};

export async function findRecipes() {
  return db.select().from(recipes);
}

export async function findDefaultRecipe(catalogueId: number) {
  return db.query.recipes.findFirst({
    where: (recipes, { eq }) =>
      eq(recipes.catalogueId, catalogueId) && eq(recipes.isDefault, true),
  });
}

export async function maybeSetDefault(catalogueId: number, recipeId: number) {
  const defaultExists = await findDefaultRecipe(catalogueId);
  if (defaultExists) {
    return;
  }
  const result = await db
    .update(recipes)
    .set({ isDefault: true })
    .where(eq(recipes.id, recipeId))
    .returning();
  return result[0];
}

export async function setDefault(recipeId: number) {
  const result = await db.transaction(async (tx) => {
    await tx.update(recipes).set({ isDefault: false });

    return tx
      .update(recipes)
      .set({ isDefault: true })
      .where(eq(recipes.id, recipeId))
      .returning();
  });
  return result[0];
}

export async function findRecipeById(id: number) {
  return await db.query.recipes.findFirst({
    where: (recipes, { eq }) => eq(recipes.id, id),
    with: {
      catalogue: true,
    },
  });
}

export async function startRecipe(
  catalogueId: number,
  url: string,
  rootPageType: PageType,
  name?: string,
  description?: string
) {
  const result = await db
    .insert(recipes)
    .values({
      catalogueId,
      url,
      name,
      description,
      isDefault: false,
      configuration: {
        pageType: rootPageType,
      },
      status: RecipeDetectionStatus.WAITING,
    })
    .returning({ id: recipes.id });
  return result[0];
}

export async function createRecipe(
  catalogueId: number,
  url: string,
  configuration: RecipeConfiguration,
  robotsTxt?: RobotsTxt,
  acknowledgedSkipRobotsTxt?: boolean,
  name?: string,
  description?: string
) {
  const result = await db
    .insert(recipes)
    .values({
      catalogueId,
      url,
      name,
      description,
      isDefault: false,
      configuration,
      status: RecipeDetectionStatus.SUCCESS,
      robotsTxt,
      acknowledgedSkipRobotsTxt,
    })
    .returning({ id: recipes.id });
  return result[0];
}

export async function updateRecipe(
  recipeId: number,
  updateAttributes: SQLiteUpdateSetSource<typeof recipes>
) {
  const result = await db
    .update(recipes)
    .set(updateAttributes)
    .where(eq(recipes.id, recipeId))
    .returning();
  return result[0];
}

export async function destroyRecipe(id: number) {
  return db.delete(recipes).where(eq(recipes.id, id));
}

export async function searchTemplateRecipes(
  catalogueType?: CatalogueType,
  searchQuery?: string
) {
  const whereConditions: any[] = [
    eq(recipes.isTemplate, true),
  ];

  // Filter by catalogue type if provided
  if (catalogueType !== undefined) {
    whereConditions.push(eq(catalogues.catalogueType, catalogueType));
  }

  // Add search filter if provided
  if (searchQuery && searchQuery.trim()) {
    whereConditions.push(
      or(
        ilike(catalogues.name, `%${searchQuery}%`),
        ilike(catalogues.url, `%${searchQuery}%`)
      )!
    );
  }

  // Join with catalogues to filter by catalogue type
  const results = await db
    .select({
      recipe: recipes,
      catalogue: catalogues,
      extractionCount: sql<number>`COUNT(${extractions.id})`.as("extraction_count"),
      mostRecentExtractionDate: sql<string | null>`MAX(${extractions.createdAt})`.as("most_recent_extraction_date"),
    })
    .from(recipes)
    .innerJoin(catalogues, eq(catalogues.id, recipes.catalogueId))
    .leftJoin(extractions, eq(extractions.recipeId, recipes.id))
    .where(and(...whereConditions))
    .groupBy(recipes.id, catalogues.id)
    .limit(50);

  return results;
}
