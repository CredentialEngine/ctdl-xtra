#!/usr/bin/env node
/**
 * xTRA MCP server for agentic recipe configuration.
 * Provides reporting and dry-run verification tools for the browser agent.
 */
import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import {
  CallToolRequestSchema,
  ListToolsRequestSchema,
} from "@modelcontextprotocol/sdk/types.js";
import {
  AgenticRecipeStage,
  AGENTIC_RECIPE_STAGES,
  RecipeDetectionStatus,
  type PageSetupConfig,
} from "../../../common/types";
import { updateRecipe } from "../data/recipes";
import {
  assertRecipeConfigurationHasDetailLeaf,
  parseAgentRecipeConfiguration,
} from "./recipeConfigurationValidation";
import {
  shouldResetVerificationState,
  validateSubmitAllowed,
  type SubmitVerificationState,
} from "./recipeSubmitGates";
import { applyStageReport, MAX_STAGE_CHANGES } from "./recipeStages";
import { verifyRecipeLinks } from "./verifyRecipeLinks";
import {
  TEST_EXTRACTION_LIMIT_MESSAGE,
  TestExtractionLimitError,
  testExtraction,
} from "./testExtraction";

const TOOLS = [
  {
    name: "xtra_report_stage",
    description:
      "Report the current recipe configuration stage enum. Call when entering or re-entering a stage. Do not skip stages. Limited to 20 stage changes per recipe (re-reporting the current stage does not count).",
    inputSchema: {
      type: "object",
      properties: {
        stage: {
          type: "string",
          enum: [...AGENTIC_RECIPE_STAGES],
          description: `Stage enum: ${AGENTIC_RECIPE_STAGES.join(", ")}`,
        },
      },
      required: ["stage"],
    },
  },
  {
    name: "xtra_report_progress",
    description:
      "Explain what you are doing right now. Call before major inspection steps.",
    inputSchema: {
      type: "object",
      properties: {
        message: {
          type: "string",
          description: "User-visible explanation of the current action",
        },
      },
      required: ["message"],
    },
  },
  {
    name: "xtra_verify_recipe_links",
    description:
      "Dry-run link extraction for a recipe level: fetch the page and return URLs matching the regexp (does not enqueue pages).",
    inputSchema: {
      type: "object",
      properties: {
        url: { type: "string", description: "Page URL to test" },
        linkRegexp: {
          type: "string",
          description: "Link RegExp pattern for this level",
        },
        clickSelector: {
          type: "string",
          description: "Optional dynamic catalogue CSS selector",
        },
        clickOptions: {
          type: "object",
          properties: {
            limit: { type: "number" },
            waitMs: { type: "number" },
          },
        },
        exactLinkPatternMatch: { type: "boolean" },
      },
      required: ["url"],
    },
  },
  {
    name: "xtra_test_extraction",
    description:
      "Run xTRA entity extraction on a DETAIL page URL. Returns whether any entries were extracted (extracted: true/false). Limited to 10 calls per recipe.",
    inputSchema: {
      type: "object",
      properties: {
        url: {
          type: "string",
          description: "DETAIL page URL to extract",
        },
      },
      required: ["url"],
    },
  },
  {
    name: "xtra_give_up",
    description:
      "Stop configuration and report why the catalogue cannot be configured. Use when the site is not recipe-compatible or configuration cannot be completed.",
    inputSchema: {
      type: "object",
      properties: {
        message: {
          type: "string",
          description:
            "User-visible explanation of why configuration is being abandoned",
        },
      },
      required: ["message"],
    },
  },
  {
    name: "xtra_submit_recipe_configuration",
    description:
      "Submit the final validated recipe configuration after VERIFY_RECIPE succeeds.",
    inputSchema: {
      type: "object",
      properties: {
        configuration: {
          type: "object",
          description: "Full nested recipe configuration object",
        },
        summary: {
          type: "string",
          description: "Brief summary of the configured recipe levels",
        },
      },
      required: ["configuration"],
    },
  },
] as const;

function readRecipeIdFromEnv(): number {
  const raw = process.env.XTRA_RECIPE_ID?.trim();
  const value = Number(raw);
  if (!Number.isInteger(value) || value <= 0) {
    throw new Error("XTRA_RECIPE_ID env var must be a positive integer");
  }
  return value;
}

function readPageLoadWaitTimeFromEnv(): number | undefined {
  const raw = process.env.XTRA_PAGE_LOAD_WAIT_TIME?.trim();
  if (!raw) {
    return undefined;
  }
  const value = Number(raw);
  return Number.isFinite(value) && value >= 0 ? value : undefined;
}

function readPageSetupFromEnv(): PageSetupConfig | undefined {
  const raw = process.env.XTRA_PAGE_SETUP?.trim();
  if (!raw) {
    return undefined;
  }
  try {
    return JSON.parse(raw) as PageSetupConfig;
  } catch {
    console.error("[xtraMcp] XTRA_PAGE_SETUP is not valid JSON");
    return undefined;
  }
}

function xtraPayload(payload: Record<string, unknown>) {
  return JSON.stringify({ xtraEvent: true, ...payload });
}

let currentStage: AgenticRecipeStage | null = null;
let stageChangeCount = 0;
let verifyLinkCallsSuccessful = 0;
let testExtractionSucceeded = false;

function verificationState(): SubmitVerificationState {
  return {
    currentStage,
    verifyLinkCallsSuccessful,
    testExtractionSucceeded,
  };
}

function resetVerificationState() {
  verifyLinkCallsSuccessful = 0;
  testExtractionSucceeded = false;
}

async function handleToolCall(name: string, args: Record<string, unknown>) {
  switch (name) {
    case "xtra_report_stage": {
      const result = applyStageReport(
        currentStage,
        args.stage,
        stageChangeCount
      );
      if (!result.ok) {
        return toolError(result.error);
      }
      if (result.changed) {
        stageChangeCount++;
      }
      if (shouldResetVerificationState(result.stage, result.changed)) {
        resetVerificationState();
      }
      currentStage = result.stage;
      return toolSuccess(
        xtraPayload({
          kind: "stage",
          stage: result.stage,
          changed: result.changed,
          attempt: stageChangeCount,
          remaining: MAX_STAGE_CHANGES - stageChangeCount,
        })
      );
    }
    case "xtra_report_progress": {
      const message = String(args.message ?? "").trim();
      if (!message) {
        return toolError("message is required");
      }
      return toolSuccess(
        xtraPayload({
          kind: "progress",
          message,
        })
      );
    }
    case "xtra_verify_recipe_links": {
      const url = String(args.url ?? "").trim();
      if (!url) {
        return toolError("url is required");
      }
      try {
        const result = await verifyRecipeLinks({
          url,
          linkRegexp:
            typeof args.linkRegexp === "string"
              ? args.linkRegexp
              : undefined,
          clickSelector:
            typeof args.clickSelector === "string"
              ? args.clickSelector
              : undefined,
          clickOptions:
            args.clickOptions && typeof args.clickOptions === "object"
              ? (args.clickOptions as {
                  limit?: number;
                  waitMs?: number;
                })
              : undefined,
          exactLinkPatternMatch:
            typeof args.exactLinkPatternMatch === "boolean"
              ? args.exactLinkPatternMatch
              : undefined,
          pageLoadWaitTime: readPageLoadWaitTimeFromEnv(),
          pageSetup: readPageSetupFromEnv(),
        });
        verifyLinkCallsSuccessful++;
        return toolSuccess(
          xtraPayload({
            kind: "verify",
            url: result.url,
            linkRegexp: result.linkRegexp,
            matchCount: result.matchCount,
            sampleUrls: result.sampleUrls,
            urls: result.urls,
            markdownPreview: result.markdownPreview,
          })
        );
      } catch (error) {
        const message =
          error instanceof Error ? error.message : "Verification failed";
        return toolError(message);
      }
    }
    case "xtra_test_extraction": {
      const url = String(args.url ?? "").trim();
      if (!url) {
        return toolError("url is required");
      }
      try {
        const result = await testExtraction({
          url,
          recipeId: readRecipeIdFromEnv(),
          pageLoadWaitTime: readPageLoadWaitTimeFromEnv(),
          pageSetup: readPageSetupFromEnv(),
        });
        if (result.extracted) {
          testExtractionSucceeded = true;
        }
        return toolSuccess(
          xtraPayload({
            kind: "test_extraction",
            url: result.url,
            extracted: result.extracted,
            entryCount: result.entryCount,
            attempt: result.attempt,
            remaining: result.remaining,
          })
        );
      } catch (error) {
        if (error instanceof TestExtractionLimitError) {
          return toolError(TEST_EXTRACTION_LIMIT_MESSAGE);
        }
        const message =
          error instanceof Error ? error.message : "Test extraction failed";
        return toolError(message);
      }
    }
    case "xtra_give_up": {
      const message = String(args.message ?? "").trim();
      if (!message) {
        return toolError("message is required");
      }
      return toolSuccess(
        xtraPayload({
          kind: "give_up",
          message,
        })
      );
    }
    case "xtra_submit_recipe_configuration": {
      const recipeId = readRecipeIdFromEnv();
      try {
        const configuration = parseAgentRecipeConfiguration(args.configuration);
        assertRecipeConfigurationHasDetailLeaf(configuration);
        const submitGate = validateSubmitAllowed(
          configuration,
          verificationState()
        );
        if (!submitGate.ok) {
          return toolError(submitGate.error);
        }
        await updateRecipe(recipeId, {
          configuration,
          status: RecipeDetectionStatus.SUCCESS,
          detectionFailureReason: null,
        });
        const summary =
          typeof args.summary === "string" && args.summary.trim()
            ? args.summary.trim()
            : "Recipe configuration saved.";
        return toolSuccess(
          xtraPayload({
            kind: "submit",
            recipeId,
            message: summary,
          })
        );
      } catch (error) {
        const message =
          error instanceof Error
            ? error.message
            : "Could not save recipe configuration";
        return toolError(message);
      }
    }
    default:
      return toolError(`Unknown tool: ${name}`);
  }
}

function toolSuccess(text: string) {
  return {
    content: [{ type: "text" as const, text }],
    isError: false,
  };
}

function toolError(message: string) {
  return {
    content: [{ type: "text" as const, text: message }],
    isError: true,
  };
}

const server = new Server(
  {
    name: "ctdl-xtra/recipe-config",
    version: "0.1.0",
  },
  {
    capabilities: {
      tools: {},
    },
  }
);

server.setRequestHandler(ListToolsRequestSchema, async () => ({
  tools: [...TOOLS],
}));

server.setRequestHandler(CallToolRequestSchema, async (request) =>
  handleToolCall(
    request.params.name,
    (request.params.arguments ?? {}) as Record<string, unknown>
  )
);

async function runServer() {
  const transport = new StdioServerTransport();
  await server.connect(transport);
}

runServer().catch(console.error);

process.stdin.on("close", () => {
  console.error("xTRA MCP Server closed");
  server.close();
});
