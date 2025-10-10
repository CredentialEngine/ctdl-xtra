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
import {
  BrowserFetchError,
  fetchBrowserPage,
  simplifiedMarkdown,
} from "../extraction/browser";
import { detectPagination } from "../extraction/llm/detectPagination";
import detectUrlRegexp, {
  createUrlExtractor,
} from "../extraction/llm/detectUrlRegexp";
import {
  fetchAndParseRobotsTxt,
  isUrlAllowed,
} from "../extraction/robotsParser";
import { submitRecipeDetection } from "../extraction/submitRecipeDetection";
import getLogger from "../logging";
import { bestOutOf, exponentialRetry } from "../utils";
import { Queues, submitJob } from "../workers";

const logger = getLogger("routers.recipes");

const PaginationConfigurationSchema = z.object({
  urlPatternType: z.nativeEnum(UrlPatternType),
  urlPattern: z.string(),
  totalPages: z.number(),
});

const ClickDiscoveryOptionsSchema = z.object({
  limit: z.number().int().positive().max(10000).optional(),
  waitMs: z.number().int().nonnegative().max(60000).optional(),
});

const RecipeConfigurationSchema = z.object({
  pageType: z.nativeEnum(PageType),
  linkRegexp: z.string().optional(),
  clickSelector: z.string().optional(),
  clickOptions: ClickDiscoveryOptionsSchema.optional(),
  pagination: PaginationConfigurationSchema.optional(),
  links: z.lazy((): z.ZodSchema => RecipeConfigurationSchema).optional(),
  pageLoadWaitTime: z.number().optional().default(0),
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
        acknowledgedSkipRobotsTxt: z.boolean().optional(),
      })
    )
    .mutation(
      async (
        opts
      ): Promise<{
        id: number;
        context?: { pageType: PageType; message?: string };
      }> => {
        try {
          const robotsTxt = await fetchAndParseRobotsTxt(opts.input.url);
          logger.info(`robotsTxt: ${JSON.stringify(robotsTxt)}`);
          if (
            robotsTxt &&
            !isUrlAllowed(robotsTxt, opts.input.url) &&
            !opts.input.acknowledgedSkipRobotsTxt
          ) {
            throw new AppError(
              "This URL cannot be crawled according to robots.txt rules. Please check the 'Bypass robots.txt' checkbox to confirm you have permission to crawl this site.",
              AppErrors.BAD_REQUEST
            );
          }

          if (opts.input.configuration) {
            return createRecipe(
              opts.input.catalogueId,
              opts.input.url,
              opts.input.configuration,
              robotsTxt || undefined,
              opts.input.acknowledgedSkipRobotsTxt
            );
          } else {
            const detection = await submitRecipeDetection(
              opts.input.url,
              opts.input.catalogueId
            );

            // If detection was successful, update the recipe with robots.txt info
            if (detection.id) {
              await updateRecipe(detection.id, {
                robotsTxt: robotsTxt || undefined,
                acknowledgedSkipRobotsTxt: opts.input.acknowledgedSkipRobotsTxt,
              });
            }

            return {
              id: detection.id,
              context: {
                pageType: detection.pageType,
                message: detection.message ?? undefined,
              },
            };
          }
        } catch (error) {
          if (error instanceof BrowserFetchError) {
            throw new AppError(
              error.uiMessage() + " URL: " + error.url,
              AppErrors.BAD_REQUEST
            );
          } else {
            throw error;
          }
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
      const { content, screenshot } = await fetchBrowserPage(opts.input.url);
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
          const { content, screenshot } = await fetchBrowserPage(url);
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
          configuration: RecipeConfigurationSchema.partial().optional(),
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
      const mergedConfiguration = opts.input.update.configuration
        ? { ...(recipe.configuration as any), ...opts.input.update.configuration }
        : undefined;
      return updateRecipe(recipe.id, {
        url: opts.input.update.url,
        ...(mergedConfiguration ? { configuration: mergedConfiguration } : {}),
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
  testRecipeRegex: publicProcedure
    .input(
      z.object({
        url: z.string().url(),
        regex: z.string(),
      })
    )
    .mutation(async (opts) => {
      const regexp = opts.input.regex;

      try {
        const { content } = await fetchBrowserPage(opts.input.url);
        const markdownContent = await simplifiedMarkdown(content);

        const testRegex = new RegExp(regexp, "g");
        const extractor = createUrlExtractor(testRegex);
        const urls = await extractor(opts.input.url, markdownContent);
        return {
          regexp,
          urls,
        };
      } catch (error) {
        if (error instanceof BrowserFetchError) {
          throw new AppError(error.uiMessage(), AppErrors.BAD_REQUEST);
        } else {
          throw error;
        }
      }
    }),
});
