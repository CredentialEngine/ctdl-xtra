import { z } from "zod";
import { publicProcedure, router } from ".";
import { CatalogueType } from "../../../common/types";
import {
  createCatalogue,
  destroyCatalogue,
  findCatalogueById,
  findCatalogueByUrl,
  findCatalogues,
  findLatestExtractionsForCatalogue,
  getCatalogueCount,
} from "../data/catalogues";
import { findDatasets } from "../data/datasets";
import { fetchPreview } from "../extraction/browser";

export const cataloguesRouter = router({
  preview: publicProcedure
    .input(
      z.object({
        url: z.string().url(),
      })
    )
    .query(async (opts) => fetchPreview(opts.input.url)),
  list: publicProcedure
    .input(
      z
        .object({
          page: z.number().int().positive().default(1),
          search: z.string().optional(),
          catalogueType: z.nativeEnum(CatalogueType).optional(),
        })
        .default({})
    )
    .query(async (opts) => {
      const totalItems = await getCatalogueCount(opts.input);
      const totalPages = Math.ceil(totalItems / 20);
      const params = {
        limit: 20,
        offset: opts.input.page * 20 - 20,
        search: opts.input.search,
        catalogueType: opts.input.catalogueType,
      };
      return {
        totalItems,
        totalPages,
        results: await findCatalogues(params),
      };
    }),
  create: publicProcedure
    .input(
      z.object({
        name: z.string().min(2),
        url: z.string().url(),
        thumbnailUrl: z.string().optional(),
        catalogueType: z.nativeEnum(CatalogueType).optional(),
      })
    )
    .mutation(async (opts) => {
      const { name, url, thumbnailUrl, catalogueType } = opts.input;
      const existingCatalogue = await findCatalogueByUrl(url);
      if (existingCatalogue) {
        return {
          id: existingCatalogue.id,
          existing: true,
        };
      }
      const newCatalogue = await createCatalogue(
        name,
        url,
        catalogueType,
        thumbnailUrl
      );
      return {
        id: newCatalogue.id,
        existing: false,
      };
    }),
  detail: publicProcedure
    .input(
      z.object({
        id: z.number().int().positive(),
      })
    )
    .query(async (opts) => {
      const result = await findCatalogueById(opts.input.id);
      if (!result) {
        return undefined;
      }
      const extractions = await findLatestExtractionsForCatalogue(result.id);
      return {
        ...result,
        extractions,
      };
    }),
  datasets: publicProcedure
    .input(
      z.object({
        id: z.number().int().positive(),
        page: z.number().int().positive().default(1),
      })
    )
    .query(async (opts) => {
      const { totalItems, items } = await findDatasets(
        opts.input.id,
        20,
        opts.input.page * 20 - 20
      );
      const totalPages = Math.ceil(totalItems / 20);
      return {
        totalItems,
        totalPages,
        results: items,
      };
    }),
  destroy: publicProcedure
    .input(
      z.object({
        id: z.number().int().positive(),
      })
    )
    .mutation(async (opts) => {
      return destroyCatalogue(opts.input.id);
    }),
});
