import { z } from "zod";
import { merge } from "lodash";
import { publicProcedure, router } from ".";
import { createOrUpdate, findSettings } from "../data/settings";
import { decryptFromDb } from "../data/schema";

export const settingsRouter = router({
  list: publicProcedure.query(async (_opts) => {
    const allSettings = await findSettings();
    return allSettings.map((setting) => ({
      ...setting,
      value: setting.isEncrypted ? "*****" : setting.value,
    }));
  }),
  setSetting: publicProcedure
    .input(
      z.object({
        key: z.string(),
        value: z.string(),
        isEncrypted: z.boolean().optional(),
        encryptedPreview: z.string().optional(),
        merge: z.boolean().optional(),
      })
    )
    .mutation(async (opts) => {
      const { key, value, isEncrypted, encryptedPreview, merge: mergeSettings } = opts.input;

      if (mergeSettings) {
        const existingSettings = await findSettings();
        let existingSetting = existingSettings.find((setting) => setting.key === key);
        if (existingSetting?.isEncrypted) {
          existingSetting.value = decryptFromDb(existingSetting.value);
        }

        if (existingSetting) {
          const newValue = merge(JSON.parse(existingSetting.value), JSON.parse(value));
          await createOrUpdate(key, JSON.stringify(newValue), isEncrypted, encryptedPreview || null);
        }
      } else {
        await createOrUpdate(key, value, isEncrypted, encryptedPreview || null);
      }

      await createOrUpdate(key, value, isEncrypted, encryptedPreview || null);
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
        `sk-...${opts.input.apiKey.slice(-4)}`
      );
    }),
});
