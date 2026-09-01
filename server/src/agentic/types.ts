import type { PageSetupConfig } from "../../../common/types";

export const DEFAULT_AGENT_MODEL = "haiku";
export const DEFAULT_MAX_TURNS = 24;
export const DEFAULT_MAX_BUDGET_USD = 5;
export const AGENT_SMOKE_URL = "https://www.google.com";

/**
 * Browser context aligned with `FetchBrowserPageOptions`.
 * Launch/proxy settings are applied to the Puppeteer MCP session today;
 * page wait/setup are passed through to prompts until MCP can run them.
 */
export interface AgentBrowserOptions {
  skipProxy?: boolean;
  /** Reserved: fetchBrowserPage rotates proxies; MCP currently uses the first. */
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
}

export interface RunBrowserAgentOptions {
  prompt: string;
  apiKey?: string;
  model?: string;
  maxTurns?: number;
  maxBudgetUsd?: number;
  browser?: AgentBrowserOptions;
  /** Fail if the agent never called a Puppeteer MCP tool. Default true. */
  requireBrowserTool?: boolean;
  onEvent?: (event: AgentEvent) => void;
}
