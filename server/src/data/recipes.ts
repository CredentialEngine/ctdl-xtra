import { InferSelectModel, eq } from "drizzle-orm";
import { SQLiteUpdateSetSource } from "drizzle-orm/sqlite-core";
import db from "../data";
import { recipes } from "../data/schema";

import {
  PageType,
  RecipeConfiguration,
  RecipeDetectionStatus,
} from "../../../common/types";

export type Recipe = Omit<InferSelectModel<typeof recipes>, "configuration"> & {
  configuration?: RecipeConfiguration;
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
  rootPageType: PageType
) {
  const result = await db
    .insert(recipes)
    .values({
      catalogueId,
      url,
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
  configuration: RecipeConfiguration
) {
  const result = await db
    .insert(recipes)
    .values({
      catalogueId,
      url,
      isDefault: false,
      configuration,
      status: RecipeDetectionStatus.SUCCESS,
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
