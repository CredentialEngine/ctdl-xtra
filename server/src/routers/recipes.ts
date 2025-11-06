import { z } from "zod";
import { publicProcedure, router } from ".";
import { CatalogueType, PageType, RecipeConfiguration, UrlPatternType } from "../../../common/types";
import { AppError, AppErrors } from "../appErrors";
import {
  createRecipe,
  destroyRecipe,
  findRecipeById,
  searchTemplateRecipes,
  setDefault,
  updateRecipe,
} from "../data/recipes";
import {
  BrowserFetchError,
  fetchBrowserPage,
  simplifiedMarkdown,
} from "../extraction/browser";
import { discoverDynamicLinks } from "../extraction/dynamicLinkDiscovery";
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
        name: z.string().optional(),
        description: z.string().optional(),
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

          // Check if configuration is provided and valid (has pageType at minimum)
          // This ensures template and manual modes don't trigger background detection tasks
          const hasValidConfiguration = 
            opts.input.configuration && 
            typeof opts.input.configuration === 'object' &&
            'pageType' in opts.input.configuration &&
            opts.input.configuration.pageType !== undefined &&
            opts.input.configuration.pageType !== null;

          if (hasValidConfiguration && opts.input.configuration) {
            logger.info(`Creating recipe with provided configuration (template/manual mode). No background tasks will be triggered.`);
            const recipe = await createRecipe(
              opts.input.catalogueId,
              opts.input.url,
              opts.input.configuration as RecipeConfiguration,
              robotsTxt || undefined,
              opts.input.acknowledgedSkipRobotsTxt,
              opts.input.name,
              opts.input.description
            );
            logger.info(`Created recipe ${recipe.id} without background detection tasks`);
            return {
              id: recipe.id,
            };
          } else {
            // Only trigger detection if configuration is explicitly not provided (detect mode)
            // If configuration is provided but invalid, reject the request to prevent accidental detection
            if (opts.input.configuration !== undefined && opts.input.configuration !== null) {
              logger.warn(`Invalid configuration provided. Rejecting recipe creation to prevent accidental background detection.`);
              throw new AppError(
                "Invalid recipe configuration provided. Please ensure the configuration includes a valid pageType.",
                AppErrors.BAD_REQUEST
              );
            }

            logger.info(`No configuration provided. Starting recipe detection with background tasks (detect mode).`);
            const detection = await submitRecipeDetection(
              opts.input.url,
              opts.input.catalogueId
            );

            // If detection was successful, update the recipe with robots.txt info, name, and description
            if (detection.id) {
              await updateRecipe(detection.id, {
                robotsTxt: robotsTxt || undefined,
                acknowledgedSkipRobotsTxt: opts.input.acknowledgedSkipRobotsTxt,
                name: opts.input.name,
                description: opts.input.description,
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
          url: z.string().optional(),
          configuration: RecipeConfigurationSchema.optional(),
          isTemplate: z.boolean().optional(),
          name: z.string().optional(),
          description: z.string().optional(),
        }),
      })
    )
    .mutation(async (opts) => {
      const recipe = await findRecipeById(opts.input.id);
      if (!recipe) {
        throw new AppError("Recipe not found", AppErrors.NOT_FOUND);
      }
      
      // Only trigger detection if URL changed, not if only configuration or isTemplate changed
      const urlChanged = opts.input.update.url !== undefined && opts.input.update.url !== recipe.url;
      
      if (urlChanged) {
        await submitJob(
          Queues.DetectConfiguration,
          { recipeId: recipe.id },
          `detectConfiguration.${recipe.id}`
        );
      }
      
      // Build update object with only provided fields
      const updateData: any = {};
      
      if (opts.input.update.url !== undefined) {
        updateData.url = opts.input.update.url;
      }
      
      if (opts.input.update.configuration !== undefined) {
        // If configuration is provided, use it directly (full replacement)
        updateData.configuration = opts.input.update.configuration;
      }
      
      if (opts.input.update.isTemplate !== undefined) {
        updateData.isTemplate = opts.input.update.isTemplate;
      }
      
      if (opts.input.update.name !== undefined) {
        updateData.name = opts.input.update.name;
      }
      
      if (opts.input.update.description !== undefined) {
        updateData.description = opts.input.update.description;
      }
      
      return updateRecipe(recipe.id, updateData);
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
        regex: z.string().optional(),
        clickSelector: z.string().optional(),
        clickOptions: ClickDiscoveryOptionsSchema.optional(),
      })
    )
    .mutation(async (opts) => {
      const regexp = opts.input.regex;

      try {
        let urls: string[];

        // Use dynamic links harvesting if clickSelector is provided
        if (opts.input.clickSelector) {
          urls = await discoverDynamicLinks(
            opts.input.url,
            opts.input.clickSelector,
            opts.input.clickOptions
          );
          
          // If regex is provided, filter the discovered URLs by the regex
          if (regexp) {
            const testRegex = new RegExp(regexp, "g");
            urls = urls.filter((url) => testRegex.test(url));
            // Reset regex lastIndex for next use
            testRegex.lastIndex = 0;
          }
        } else {
          // Use traditional regex-based extraction (regex is required when no clickSelector)
          if (!regexp) {
            throw new AppError("Regex is required when clickSelector is not provided", AppErrors.BAD_REQUEST);
          }
          const { content } = await fetchBrowserPage(opts.input.url);
          const markdownContent = await simplifiedMarkdown(content);

          const testRegex = new RegExp(regexp, "g");
          const extractor = createUrlExtractor(testRegex);
          urls = await extractor(opts.input.url, markdownContent);
        }

        return {
          regexp: regexp || "",
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
  searchTemplates: publicProcedure
    .input(
      z.object({
        catalogueType: z.nativeEnum(CatalogueType).optional(),
        searchQuery: z.string().optional(),
      })
    )
    .query(async (opts) => {
      const results = await searchTemplateRecipes(
        opts.input.catalogueType,
        opts.input.searchQuery
      );
      return results.map((r) => ({
        recipe: r.recipe,
        catalogue: r.catalogue,
        extractionCount: r.extractionCount,
        mostRecentExtractionDate: r.mostRecentExtractionDate,
      }));
    }),
});
