import type { PageSetupConfig } from "../../../common/types";
import { resolveAgentMcpCommand } from "./mcpEntry";

export const XTRA_RECIPE_ID_ENV = "XTRA_RECIPE_ID";
export const XTRA_PAGE_LOAD_WAIT_ENV = "XTRA_PAGE_LOAD_WAIT_TIME";
export const XTRA_PAGE_SETUP_ENV = "XTRA_PAGE_SETUP";

export function xtraMcpCommand(): { command: string; args: string[] } {
  return resolveAgentMcpCommand("xtraMcpServer", __dirname);
}

export interface XtraMcpSession {
  recipeId: number;
  pageLoadWaitTime?: number;
  pageSetup?: PageSetupConfig;
}

export function xtraMcpEnv(session: XtraMcpSession): Record<string, string> {
  const env: Record<string, string> = {
    [XTRA_RECIPE_ID_ENV]: String(session.recipeId),
  };
  if (session.pageSetup) {
    env[XTRA_PAGE_SETUP_ENV] = JSON.stringify(session.pageSetup);
  }
  if (session.pageLoadWaitTime !== undefined && session.pageLoadWaitTime >= 0) {
    env[XTRA_PAGE_LOAD_WAIT_ENV] = String(session.pageLoadWaitTime);
  }
  return env;
}

/** Parse a tool-argument page wait (seconds). `0` means no extra wait. */
export function parsePageLoadWaitTime(value: unknown): number | undefined {
  if (typeof value === "number") {
    return Number.isFinite(value) && value >= 0 ? value : undefined;
  }
  if (typeof value === "string") {
    const trimmed = value.trim();
    if (!trimmed) {
      return undefined;
    }
    const parsed = Number(trimmed);
    return Number.isFinite(parsed) && parsed >= 0 ? parsed : undefined;
  }
  return undefined;
}
