import { z } from "zod";
import { publicProcedure, router } from ".";
import { findCataloguesWithData, findDataItems } from "../data/datasets";

export const datasetsRouter = router({
  list: publicProcedure
    .input(
      z
        .object({
          page: z.number().int().positive().default(1),
        })
        .default({})
    )
    .query(async (opts) => {
      const { totalItems, items } = await findCataloguesWithData(
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
  items: publicProcedure
    .input(
      z.object({
        page: z.number().int().positive().default(1),
        extractionId: z.number().int().positive(),
      })
    )
    .query(async (opts) => {
      const { totalItems, items } = await findDataItems(
        opts.input.extractionId,
        20,
        opts.input.page * 20 - 20
      );
      const totalPages = Math.ceil(totalItems! / 20);
      return {
        totalItems: totalItems!,
        totalPages,
        results: items,
      };
    }),
});
