import { z } from "zod";
import { publicProcedure, router } from ".";
import { createOrUpdate, findSetting } from "../data/settings";
import { SETTING_DEFAULTS } from "../constants";

const DetailQuerySchema = z.object({
  key: z.enum([
    "PROXY",
    "PROXY_ENABLED",
    "OPENAI_API_KEY",
    "MAX_EXTRACTION_BUDGET",
  ]),
});

type DetailQueryInput = z.infer<typeof DetailQuerySchema>;

export const settingsRouter = router({
  detail: publicProcedure
    .input(DetailQuerySchema)
    .query(async (opts: { input: DetailQueryInput }) => {
      const found = await findSetting(opts.input.key);
      if (found) {
        return found;
      }
      return {
        key: opts.input.key,
        value: SETTING_DEFAULTS[opts.input.key],
        isEncrypted: false,
        encryptedPreview: null,
        createdAt: new Date(),
      };
    }),
  setOpenAIApiKey: publicProcedure
    .input(
      z.object({
        apiKey: z.string().regex(/^sk-.{30,200}$/),
      })
    )
    .mutation(async (opts) => {
      await createOrUpdate({
        key: "OPENAI_API_KEY",
        value: opts.input.apiKey,
        isEncrypted: true,
        encryptedPreview: `sk-...${opts.input.apiKey.slice(-4)}`,
      });
    }),
  setProxyEnabled: publicProcedure.input(z.boolean()).mutation(async (opts) => {
    await createOrUpdate({
      key: "PROXY_ENABLED",
      value: opts.input,
    });
  }),
  setProxyUrl: publicProcedure
    .input(
      z
        .string()
        .url()
        .describe(
          "The URL of the proxy server. Can contain username and password, for example: http://user:password@proxy.example.com:8080"
        )
    )
    .mutation(async (opts) => {
      const uri = new URL(opts.input);
      const preview = `${uri.username}:******@${uri.hostname}:${uri.port}`;
      await createOrUpdate({
        key: "PROXY",
        value: opts.input,
        isEncrypted: true,
        encryptedPreview: preview,
      });

      const proxyEnabledExists = await findSetting<boolean>("PROXY_ENABLED");
      if (!proxyEnabledExists) {
        await createOrUpdate({
          key: "PROXY_ENABLED",
          value: true,
        });
      }
    }),
  setMaxExtractionBudget: publicProcedure
    .input(
      z
        .number()
        .nonnegative()
        .finite()
        .describe("Maximum USD budget allowed per extraction. No enforcement logic here.")
    )
    .mutation(async (opts) => {
      await createOrUpdate({
        key: "MAX_EXTRACTION_BUDGET",
        value: opts.input,
      });
    }),
});
