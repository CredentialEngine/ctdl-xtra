import { z } from "zod";
import { publicProcedure, router } from ".";
import { createOrUpdate, findSettings } from "../data/settings";
import { findUserById } from '../data/users';

export const settingsRouter = router({
  list: publicProcedure.query(async (_opts) => {
    const allSettings = await findSettings(_opts.ctx.user?.orgId);
    return allSettings.map((setting) => ({
      ...setting,
      value: setting.isEncrypted ? "*****" : setting.value,
    }));
  }),
  setOpenAIApiKey: publicProcedure
    .input(
      z.object({
        apiKey: z.string().regex(/^sk-.{30,200}$/),
      })
    )
    .mutation(async (opts) => {
      await createOrUpdate(
        "OPENAI_API_KEY",
        opts.input.apiKey,
        true,
        `sk-...${opts.input.apiKey.slice(-4)}`,
        opts.ctx.user.orgId
      );
    }),
});
