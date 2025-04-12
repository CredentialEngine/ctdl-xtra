import { z } from "zod";
import { publicProcedure, router } from ".";
import { CatalogueType, PageType, UrlPatternType } from "../../../common/types";
import { AppError, AppErrors } from "../appErrors";
import {
  createRecipe,
  destroyRecipe,
  findRecipeById,
  setDefault,
  updateRecipe,
} from "../data/recipes";
import { fetchBrowserPage, simplifiedMarkdown } from "../extraction/browser";
import { detectPagination } from "../extraction/llm/detectPagination";
import detectUrlRegexp, {
  createUrlExtractor,
} from "../extraction/llm/detectUrlRegexp";
import { submitRecipeDetection } from "../extraction/submitRecipeDetection";
import { bestOutOf, exponentialRetry } from "../utils";
import { Queues, submitJob } from "../workers";
import { ProxySettings } from "../types";
import { findGetSettingJSON } from "../data/settings";

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
        configuration: RecipeConfigurationSchema.optional(),
      })
    )
    .mutation(
      async (
        opts
      ): Promise<{
        id: number;
        context?: { pageType: PageType; message?: string };
      }> => {
        if (opts.input.configuration) {
          return createRecipe(
            opts.input.catalogueId,
            opts.input.url,
            opts.input.configuration
          );
        } else {
          const detection = await submitRecipeDetection(
            opts.input.url,
            opts.input.catalogueId
          );
          return {
            id: detection.id,
            context: {
              pageType: detection.pageType,
              message: detection.message ?? undefined,
            },
          };
        }
      }
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
  detectPagination: publicProcedure
    .input(
      z.object({
        url: z.string().url(),
        catalogueType: z.nativeEnum(CatalogueType),
      })
    )
    .mutation(async (opts) => {
      const proxy = await findGetSettingJSON<ProxySettings>('PROXY');
      const { content, screenshot } = await fetchBrowserPage(opts.input.url, proxy?.enabled ? proxy.url : undefined);
      const markdownContent = await simplifiedMarkdown(content);
      return detectPagination(
        {
          url: opts.input.url,
          content: markdownContent,
          screenshot,
          catalogueType: opts.input.catalogueType,
        },
        PageType.DETAIL_LINKS,
        true
      );
    }),
  detectUrlRegexp: publicProcedure
    .input(
      z.object({
        urls: z.array(z.string().url()),
        pageType: z.nativeEnum(PageType),
        catalogueType: z.nativeEnum(CatalogueType),
      })
    )
    .mutation(async (opts) => {
      const pages = await Promise.all(
        opts.input.urls.map(async (url) => {
          const proxy = await findGetSettingJSON<ProxySettings>('PROXY');
          const { content, screenshot } = await fetchBrowserPage(url, proxy?.enabled ? proxy.url : undefined);
          const markdownContent = await simplifiedMarkdown(content);
          return { url, content: markdownContent, screenshot };
        })
      );
      const detection = await bestOutOf(
        3,
        () =>
          exponentialRetry(
            async () =>
              detectUrlRegexp(
                {
                  url: pages[0].url,
                  content: pages[0].content,
                  screenshot: pages[0].screenshot,
                  catalogueType: opts.input.catalogueType,
                },
                opts.input.pageType,
                pages.length > 1 ? [pages[1]] : undefined
              ),
            10
          ),
        (r) => r.source
      );
      const extractor = createUrlExtractor(detection);
      const urls = await extractor(pages[0].url, pages[0].content);
      return {
        regexp: detection.source,
        urls,
      };
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
