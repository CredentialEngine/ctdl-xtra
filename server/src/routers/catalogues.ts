import { z } from "zod";
import { publicProcedure, router } from ".";
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
import { findOrgsByUser } from "@/data/orgs";

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
          withData: z.boolean().default(false),
        })
        .default({})
    )
    .query(async (opts) => {
      const totalItems = await getCatalogueCount();
      const totalPages = Math.ceil(totalItems / 20);
      return {
        totalItems,
        totalPages,
        results: await findCatalogues(opts.ctx.user.orgId, 20, opts.input.page * 20 - 20),
      };
    }),
  create: publicProcedure
    .input(
      z.object({
        name: z.string().min(2),
        url: z.string().url(),
        thumbnailUrl: z.string().optional(),
      })
    )
    .mutation(async (opts) => {
      const { name, url, thumbnailUrl } = opts.input;
      const userOrgs = await findOrgsByUser(opts.ctx.user.id);
      const existingCatalogue = await findCatalogueByUrl(url, userOrgs.map(org => org.orgId));
      if (existingCatalogue) {
        return {
          id: existingCatalogue.id,
          existing: true,
        };
      }
      const newCatalogue = await createCatalogue(name, url, thumbnailUrl);
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
