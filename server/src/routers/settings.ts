import { z } from "zod";
import { publicProcedure, router } from ".";
import { AppError, AppErrors } from "../appErrors";
import { createOrUpdate, findSetting } from "../data/settings";

export const settingsRouter = router({
  detail: publicProcedure
    .input(
      z.object({
        key: z.enum(["PROXY", "PROXY_ENABLED", "OPENAI_API_KEY"]),
      })
    )
    .query(async (opts) => {
      let setting;
      if (opts.input.key === "PROXY") {
        setting = await findSetting(opts.input.key);
      } else if (opts.input.key === "PROXY_ENABLED") {
        setting = await findSetting<boolean>(opts.input.key);
      } else if (opts.input.key === "OPENAI_API_KEY") {
        setting = await findSetting<string>(opts.input.key);
      } else {
        throw new AppError("Unknown setting", AppErrors.BAD_REQUEST);
      }
      return setting;
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
        isEncrypted: false,
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
});
