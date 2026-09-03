import { z } from "zod";
import {
  PageType,
  RecipeConfiguration,
  UrlPatternType,
} from "../../../common/types";

const PaginationConfigurationSchema = z.object({
  urlPatternType: z.nativeEnum(UrlPatternType),
  urlPattern: z.string().trim().min(1),
  totalPages: z.number(),
  startPage: z.number().int().nonnegative().optional(),
});

const ClickDiscoveryOptionsSchema = z.object({
  limit: z.number().int().positive().max(10000).optional(),
  waitMs: z.number().int().nonnegative().max(60000).optional(),
});

const PageSetupStepInputSchema = z.discriminatedUnion("type", [
  z.object({
    type: z.literal("click"),
    selector: z.string(),
  }),
  z.object({
    type: z.literal("wait"),
    seconds: z.number(),
  }),
]);

const PageSetupConfigSchema = z
  .object({
    enabled: z.boolean(),
    steps: z.array(PageSetupStepInputSchema),
  })
  .superRefine((data, ctx) => {
    if (!data.enabled) return;
    data.steps.forEach((step, i) => {
      if (step.type === "click") {
        if (!step.selector.trim()) {
          ctx.addIssue({
            code: z.ZodIssueCode.custom,
            message: "Selector is required",
            path: ["steps", i, "selector"],
          });
        }
      } else if (step.type === "wait") {
        if (
          !Number.isFinite(step.seconds) ||
          step.seconds <= 0 ||
          step.seconds > 600
        ) {
          ctx.addIssue({
            code: z.ZodIssueCode.custom,
            message: "Wait seconds must be between 1 and 600",
            path: ["steps", i, "seconds"],
          });
        }
      }
    });
  });

export const AgentRecipeConfigurationSchema: z.ZodType<RecipeConfiguration> =
  z.lazy(() =>
    z.object({
      pageType: z.nativeEnum(PageType),
      linkRegexp: z.string().optional(),
      clickSelector: z.string().optional(),
      clickOptions: ClickDiscoveryOptionsSchema.optional(),
      pagination: PaginationConfigurationSchema.optional(),
      links: AgentRecipeConfigurationSchema.optional(),
      pageLoadWaitTime: z.number().optional(),
      exactLinkPatternMatch: z.boolean().optional(),
      contentSelector: z.string().optional(),
      pageSetup: PageSetupConfigSchema.optional(),
    })
  );

export function parseAgentRecipeConfiguration(
  value: unknown
): RecipeConfiguration {
  return AgentRecipeConfigurationSchema.parse(value);
}

export function assertRecipeConfigurationHasDetailLeaf(
  configuration: RecipeConfiguration
): void {
  let current: RecipeConfiguration | undefined = configuration;
  while (current) {
    if (current.pageType === PageType.DETAIL) {
      return;
    }
    if (!current.links) {
      throw new Error(
        "Recipe configuration must end with a DETAIL level"
      );
    }
    current = current.links;
  }
  throw new Error("Recipe configuration must end with a DETAIL level");
}
