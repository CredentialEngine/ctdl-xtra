import { z } from "zod";
import { publicProcedure, router } from ".";
import { CatalogueType, ExtractionStatus } from "../../../common/types";
import { AppError, AppErrors } from "../appErrors";
import { getItemsCount } from "../data/datasets";
import {
  destroyExtraction,
  findExtractionForDetailPage,
  findExtractions,
  findLogs,
  findPage,
  findPageForJob,
  findPagesPaginated,
  findStep,
  getExtractionCount,
  getLogCount,
  getPageCount,
  updateExtraction,
} from "../data/extractions";
import {
  readContent,
  readMarkdownContent,
  readScreenshot,
} from "../data/schema";
import { extractEntityData } from "../extraction/llm/extractEntityData";
import { retryFailedItems } from "../extraction/retryFailedItems";
import { startExtraction } from "../extraction/startExtraction";

export const extractionsRouter = router({
  create: publicProcedure
    .input(
      z.object({
        catalogueId: z.number().positive(),
        recipeId: z.number().positive(),
      })
    )
    .mutation(async (opts) => {
      return startExtraction(opts.input.catalogueId, opts.input.recipeId);
    }),
  cancel: publicProcedure
    .input(
      z.object({
        id: z.number().int().positive(),
      })
    )
    .mutation(async (opts) => {
      return updateExtraction(opts.input.id, {
        status: ExtractionStatus.CANCELLED,
      });
    }),
  retryFailed: publicProcedure
    .input(
      z.object({
        id: z.number().int().positive(),
      })
    )
    .mutation(async (opts) => {
      return retryFailedItems(opts.input.id);
    }),
  detail: publicProcedure
    .input(
      z.object({
        id: z.number().int().positive(),
      })
    )
    .query(async (opts) => {
      let result = await findExtractionForDetailPage(opts.input.id);
      if (!result) {
        throw new AppError("Extraction not found", AppErrors.NOT_FOUND);
      }
      return {
        ...result,
        dataItemsCount: await getItemsCount(opts.input.id),
      };
    }),
  destroy: publicProcedure
    .input(
      z.object({
        id: z.number().int().positive(),
      })
    )
    .mutation(async (opts) => {
      return destroyExtraction(opts.input.id);
    }),
  logs: publicProcedure
    .input(
      z.object({
        extractionId: z.number().int().positive(),
        page: z.number().int().positive().default(1),
        perPage: z.number().int().positive().default(10),
      })
    )
    .query(async (opts) => {
      const totalItems = await getLogCount(opts.input.extractionId);
      const totalPages = Math.ceil(totalItems / opts.input.perPage);
      const offset = opts.input.page * opts.input.perPage - opts.input.perPage;
      return {
        totalItems,
        totalPages,
        results: await findLogs(
          opts.input.extractionId,
          opts.input.perPage,
          offset
        ),
      };
    }),
  stepDetail: publicProcedure
    .input(
      z.object({
        stepId: z.number().int().positive(),
        page: z.number().int().positive().default(1),
      })
    )
    .query(async (opts) => {
      const crawlStep = await findStep(opts.input.stepId);
      if (!crawlStep) {
        throw new AppError("Step not found", AppErrors.NOT_FOUND);
      }
      const totalItems = await getPageCount(opts.input.stepId);
      const totalPages = Math.ceil(totalItems / 20);
      const offset = opts.input.page * 20 - 20;
      const crawlPages = await findPagesPaginated(crawlStep.id, 20, offset);
      return {
        crawlStep,
        crawlPages: {
          totalItems,
          totalPages,
          results: crawlPages,
        },
      };
    }),
  crawlPageDetail: publicProcedure
    .input(
      z.object({
        crawlPageId: z.number().int().positive(),
      })
    )
    .query(async (opts) => {
      const crawlPage = await findPage(opts.input.crawlPageId);
      if (!crawlPage) {
        throw new AppError("Step item not found", AppErrors.NOT_FOUND);
      }
      try {
        return {
          crawlPage,
          content: await readContent(
            crawlPage.extractionId,
            crawlPage.crawlStepId,
            crawlPage.id
          ),
          markdownContent: await readMarkdownContent(
            crawlPage.extractionId,
            crawlPage.crawlStepId,
            crawlPage.id
          ),
          screenshot: await readScreenshot(
            crawlPage.extractionId,
            crawlPage.crawlStepId,
            crawlPage.id
          ),
        };
      } catch (error) {
        return {
          crawlPage,
          content: null,
          markdownContent: null,
          screenshot: null,
        };
      }
    }),
  list: publicProcedure
    .input(
      z
        .object({
          page: z.number().int().positive().default(1),
          startDate: z.string().optional(),
          endDate: z.string().optional(),
        })
        .default({})
    )
    .query(async (opts) => {
      let startDate: Date | undefined = undefined;
      let endDate: Date | undefined = undefined;
      if (opts.input.startDate) {
        startDate = new Date(opts.input.startDate);
      }
      if (opts.input.endDate) {
        const d = new Date(opts.input.endDate);
        // Inclusive end-of-day: set to 23:59:59.999
        d.setHours(23, 59, 59, 999);
        endDate = d;
      }

      const filters = {
        startDate,
        endDate,
      };
      const totalItems = await getExtractionCount(filters);
      const totalPages = Math.ceil(totalItems / 20);
      return {
        totalItems,
        totalPages,
        results: await findExtractions(20, opts.input.page * 20 - 20, filters),
      };
    }),
  simulateDataExtraction: publicProcedure
    .input(
      z.object({
        crawlPageId: z.number().int().positive(),
      })
    )
    .mutation(async (opts) => {
      const crawlPage = await findPageForJob(opts.input.crawlPageId);
      if (!crawlPage) {
        throw new AppError("Page not found", AppErrors.NOT_FOUND);
      }
      if (!crawlPage.content) {
        return null;
      }
      const content = await readMarkdownContent(
        crawlPage.extractionId,
        crawlPage.crawlStepId,
        crawlPage.id
      );
      const screenshot = await readScreenshot(
        crawlPage.extractionId,
        crawlPage.crawlStepId,
        crawlPage.id
      );
      return await extractEntityData(
        {
          url: crawlPage.url,
          content,
          screenshot,
        },
        crawlPage.extraction.recipe.catalogue.catalogueType as CatalogueType
      );
    }),
});
