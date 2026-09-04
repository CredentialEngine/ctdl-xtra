import type { PageSetupConfig } from "../../../common/types";

export const DEFAULT_AGENT_MODEL = "haiku";
export const DEFAULT_MAX_TURNS = 24;
export const DEFAULT_MAX_BUDGET_USD = 5;
export const AGENT_SMOKE_URL = "https://www.google.com";

export function resolveAgentModel(model?: string | null): string {
  const trimmed = model?.trim();
  return trimmed || DEFAULT_AGENT_MODEL;
}

/**
 * Browser context aligned with `FetchBrowserPageOptions`.
 * Launch, proxy, page wait, and page setup are applied by the Puppeteer MCP session.
 */
export interface AgentBrowserOptions {
  skipProxy?: boolean;
  /** When true (default), try direct first then each configured proxy. */
  rotateProxies?: boolean;
  /** Explicit proxy URL. When omitted, uses `findProxies()` like fetchBrowserPage. */
  proxyUrl?: string;
  pageLoadWaitTime?: number;
  pageSetup?: PageSetupConfig;
  baseUrl?: string;
}

export type AgentEvent =
  | { type: "status"; message: string }
  | { type: "assistant"; message: string }
  | { type: "tool"; message: string; isError?: boolean };

export interface AgentRunResult {
  resultText: string;
  toolNames: string[];
  toolErrors: string[];
  numTurns: number;
  totalCostUsd: number;
  /** Proxy used for the successful attempt; undefined when direct. */
  proxyUrlUsed?: string;
  proxyAttempts?: number;
}

export interface AgenticRecipeSessionOptions {
  recipeId: number;
}

export interface RunBrowserAgentOptions {
  prompt: string;
  apiKey?: string;
  model?: string;
  maxTurns?: number;
  maxBudgetUsd?: number;
  browser?: AgentBrowserOptions;
  /** When set, attaches the xTRA recipe-config MCP server. */
  agenticRecipe?: AgenticRecipeSessionOptions;
  /** Fail if the agent never called a Puppeteer MCP tool. Default true. */
  requireBrowserTool?: boolean;
  onEvent?: (event: AgentEvent) => void;
}
