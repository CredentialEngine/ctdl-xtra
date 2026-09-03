import { existsSync } from "fs";
import path from "path";
import type { PageSetupConfig } from "../../../common/types";
import { serverPackageRoot } from "./paths";

export const XTRA_RECIPE_ID_ENV = "XTRA_RECIPE_ID";
export const XTRA_PAGE_LOAD_WAIT_ENV = "XTRA_PAGE_LOAD_WAIT_TIME";
export const XTRA_PAGE_SETUP_ENV = "XTRA_PAGE_SETUP";

export function xtraMcpCommand(): { command: string; args: string[] } {
  const sourceEntry = path.join(
    serverPackageRoot(),
    "src",
    "agentic",
    "xtraMcpServer.ts"
  );
  const tsxCli = path.join(
    serverPackageRoot(),
    "node_modules",
    "tsx",
    "dist",
    "cli.mjs"
  );
  if (existsSync(sourceEntry) && existsSync(tsxCli)) {
    return { command: process.execPath, args: [tsxCli, sourceEntry] };
  }

  const compiledEntry = path.join(__dirname, "xtraMcpServer.js");
  if (existsSync(compiledEntry)) {
    return { command: process.execPath, args: [compiledEntry] };
  }

  throw new Error(
    "Could not resolve xTRA MCP entry (run pnpm run build in server/)"
  );
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
