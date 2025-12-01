import { z } from "zod";
import { publicProcedure, router } from ".";
import { findCataloguesWithData, findDataItems, findDataset } from "../data/datasets";

export const datasetsRouter = router({
  items: publicProcedure
    .input(
      z.object({
        id: z.number().int().positive(),
        page: z.number().int().positive().default(1),
      })
    )
    .query(async (opts) => {
      const dataset = await findDataset(opts.input.id);
      const { totalItems, items } = await findDataItems(
        opts.input.id,
        20,
        opts.input.page * 20 - 20
      );
      const totalPages = Math.ceil(totalItems! / 20);
      if (!dataset) {
        return null;
      }
      return {
        dataset,
        items: {
          totalItems: totalItems!,
          totalPages,
          results: items,
        }
      };
    }),
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
    })
});
