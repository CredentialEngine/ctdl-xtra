import { PageType } from "@common/types";
import { z } from "zod";
import { publicProcedure, router } from ".";
import { AppError, AppErrors } from "../appErrors";
import {
  destroyRecipe,
  findRecipeById,
  setDefault,
  updateRecipe,
} from "../data/recipes";
import { createRecipe } from "../extraction/createRecipe";
import { Queues, submitJob } from "../workers";

enum UrlPatternType {
  page_num = "page_num",
}

const PaginationConfigurationSchema = z.object({
  urlPatternType: z.nativeEnum(UrlPatternType),
  urlPattern: z.string(),
  totalPages: z.number(),
});

const RecipeConfigurationSchema = z.object({
  pageType: z.nativeEnum(PageType),
  linkRegexp: z.string().optional(),
  pagination: PaginationConfigurationSchema.optional(),
  links: z.lazy((): z.ZodSchema => RecipeConfigurationSchema).optional(),
});

export const recipesRouter = router({
  detail: publicProcedure
    .input(
      z.object({
        id: z.number().int().positive(),
      })
    )
    .query(async (opts) => {
      return findRecipeById(opts.input.id);
    }),
  create: publicProcedure
    .input(
      z.object({
        url: z.string().url(),
        catalogueId: z.number().int().positive(),
      })
    )
    .mutation(async (opts) =>
      createRecipe(opts.input.url, opts.input.catalogueId)
    ),
  reconfigure: publicProcedure
    .input(
      z.object({
        id: z.number().int().positive(),
      })
    )
    .mutation(async (opts) => {
      const recipe = await findRecipeById(opts.input.id);
      if (!recipe) {
        throw new AppError("Recipe not found", AppErrors.NOT_FOUND);
      }
      await submitJob(
        Queues.DetectConfiguration,
        { recipeId: opts.input.id },
        `detectConfiguration.${recipe.id}`
      );
      return;
    }),
  update: publicProcedure
    .input(
      z.object({
        id: z.number().int().positive(),
        update: z.object({
          url: z.string(),
        }),
      })
    )
    .mutation(async (opts) => {
      const recipe = await findRecipeById(opts.input.id);
      if (!recipe) {
        throw new AppError("Recipe not found", AppErrors.NOT_FOUND);
      }
      await submitJob(
        Queues.DetectConfiguration,
        { recipeId: recipe.id },
        `detectConfiguration.${recipe.id}`
      );
      return updateRecipe(recipe.id, {
        url: opts.input.update.url,
      });
    }),
  destroy: publicProcedure
    .input(
      z.object({
        id: z.number().int().positive(),
      })
    )
    .mutation(async (opts) => {
      const recipe = await findRecipeById(opts.input.id);
      if (!recipe) {
        throw new AppError("Recipe not found", AppErrors.NOT_FOUND);
      }
      return destroyRecipe(opts.input.id);
    }),
  setDefault: publicProcedure
    .input(z.object({ id: z.number().int().positive() }))
    .mutation(async (opts) => {
      const recipe = await findRecipeById(opts.input.id);
      if (!recipe) {
        throw new AppError("Recipe not found", AppErrors.NOT_FOUND);
      }
      return setDefault(opts.input.id);
    }),
});
