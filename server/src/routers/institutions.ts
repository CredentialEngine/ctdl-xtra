import { z } from "zod";
import { publicProcedure, router } from ".";
import {
  createInstitution,
  destroyInstitution,
  findInstitutionById,
  findInstitutions,
  getInstitutionCount,
  updateInstitution,
} from "../data/institutions";
import getLogger from "../logging";

const logger = getLogger("routers.institutions");

export const institutionsRouter = router({
  list: publicProcedure
    .input(
      z
        .object({
          page: z.number().int().positive().default(1),
          search: z.string().optional(),
          url: z.string().url().optional(),
          limit: z.number().int().positive().max(500).default(20),
        })
        .default({})
    )
    .query(async (opts) => {
      const limit = opts.input.limit || 20;
      const totalItems = await getInstitutionCount({
        search: opts.input.search,
      });
      const totalPages = Math.ceil(totalItems / limit);
      const params = {
        limit,
        offset: opts.input.page * limit - limit,
        search: opts.input.search,
        url: opts.input.url,
      };
      return {
        totalItems,
        totalPages,
        results: await findInstitutions(params),
      };
    }),
  create: publicProcedure
    .input(
      z.object({
        name: z.string().min(2),
        domains: z.array(z.string().min(1)).min(1),
      })
    )
    .mutation(async (opts) => {
      const result = await createInstitution(
        opts.input.name,
        opts.input.domains
      );
      logger.info(`Created institution ${result.id} (${result.name})`);
      return { id: result.id };
    }),
  detail: publicProcedure
    .input(
      z.object({
        id: z.number().int().positive(),
      })
    )
    .query(async (opts) => {
      return findInstitutionById(opts.input.id);
    }),
  update: publicProcedure
    .input(
      z.object({
        id: z.number().int().positive(),
        name: z.string().min(2),
        domains: z.array(z.string().min(1)).min(1),
      })
    )
    .mutation(async (opts) => {
      return updateInstitution(
        opts.input.id,
        opts.input.name,
        opts.input.domains
      );
    }),
  destroy: publicProcedure
    .input(
      z.object({
        id: z.number().int().positive(),
      })
    )
    .mutation(async (opts) => {
      return destroyInstitution(opts.input.id);
    }),
});
