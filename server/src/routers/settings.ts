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

function parseProxyPreviews(encryptedPreview: string | null | undefined): string[] {
  if (!encryptedPreview) return [];
  try {
    const parsed = JSON.parse(encryptedPreview);
    return Array.isArray(parsed) ? parsed : [encryptedPreview];
  } catch {
    return [encryptedPreview];
  }
}

export const settingsRouter = router({
  proxyPreviews: publicProcedure.query(async () => {
    const proxy = await findSetting("PROXY", false);
    return parseProxyPreviews(proxy?.encryptedPreview ?? null);
  }),
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
  addProxyUrl: publicProcedure
    .input(
      z
        .string()
        .url()
        .describe(
          "Proxy URL, e.g. http://user:password@proxy.example.com:8080"
        )
    )
    .mutation(async (opts) => {
      const proxy = await findSetting<string | string[]>("PROXY", true);
      const current: string[] =
        Array.isArray(proxy?.value) && proxy.value.length > 0
          ? proxy.value
          : typeof proxy?.value === "string" && proxy.value.trim()
            ? [proxy.value]
            : [];
      const updated = [...current, opts.input];
      const previews = updated.map((urlStr) => {
        const uri = new URL(urlStr);
        return `${uri.username}:******@${uri.hostname}:${uri.port}`;
      });
      await createOrUpdate({
        key: "PROXY",
        value: updated,
        isEncrypted: true,
        encryptedPreview: JSON.stringify(previews),
      });

      const proxyEnabledExists = await findSetting<boolean>("PROXY_ENABLED");
      if (!proxyEnabledExists) {
        await createOrUpdate({ key: "PROXY_ENABLED", value: true });
      }
    }),
  removeProxyUrl: publicProcedure
    .input(z.number().int().min(0))
    .mutation(async (opts) => {
      const proxy = await findSetting<string | string[]>("PROXY", true);
      const current: string[] =
        Array.isArray(proxy?.value) && proxy.value.length > 0
          ? proxy.value
          : typeof proxy?.value === "string" && proxy.value.trim()
            ? [proxy.value]
            : [];
      const index = opts.input;
      if (index >= current.length) return;
      const updated = current.filter((_, i) => i !== index);
      const previews = updated.map((urlStr) => {
        const uri = new URL(urlStr);
        return `${uri.username}:******@${uri.hostname}:${uri.port}`;
      });
      await createOrUpdate({
        key: "PROXY",
        value: updated,
        isEncrypted: true,
        encryptedPreview: updated.length > 0 ? JSON.stringify(previews) : null,
      });
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
