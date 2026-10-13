import type { PageSetupConfig } from "../../../common/types";
import type { AgentChromeSession } from "./chrome";
import { resolveAgentMcpCommand } from "./mcpEntry";
import { PUPPETEER_PROXY_AUTH_ENV } from "./proxyAuthHook";

export const PUPPETEER_PAGE_SETUP_ENV = "PUPPETEER_PAGE_SETUP";
export const PUPPETEER_PAGE_LOAD_WAIT_ENV = "PUPPETEER_PAGE_LOAD_WAIT_TIME";

export function puppeteerMcpCommand(): { command: string; args: string[] } {
  return resolveAgentMcpCommand("puppeteerMcpServer", __dirname);
}

export function puppeteerMcpEnv(
  session: AgentChromeSession
): Record<string, string> {
  const env: Record<string, string> = {
    PUPPETEER_LAUNCH_OPTIONS: JSON.stringify(session.launchOptions),
  };
  if (session.proxyAuth) {
    env[PUPPETEER_PROXY_AUTH_ENV] = JSON.stringify(session.proxyAuth);
  }
  if (session.pageSetup) {
    env[PUPPETEER_PAGE_SETUP_ENV] = JSON.stringify(session.pageSetup);
  }
  if (session.pageLoadWaitTime && session.pageLoadWaitTime > 0) {
    env[PUPPETEER_PAGE_LOAD_WAIT_ENV] = String(session.pageLoadWaitTime);
  }
  return env;
}

export function readPageSetupFromEnv(): PageSetupConfig | undefined {
  const raw = process.env[PUPPETEER_PAGE_SETUP_ENV]?.trim();
  if (!raw) {
    return undefined;
  }
  try {
    const parsed = JSON.parse(raw) as PageSetupConfig;
    if (parsed && typeof parsed === "object" && Array.isArray(parsed.steps)) {
      return parsed;
    }
  } catch {
    console.error("[puppeteerMcp] PUPPETEER_PAGE_SETUP is not valid JSON");
  }
  return undefined;
}

export function readPageLoadWaitTimeFromEnv(): number | undefined {
  const raw = process.env[PUPPETEER_PAGE_LOAD_WAIT_ENV]?.trim();
  if (!raw) {
    return undefined;
  }
  const value = Number(raw);
  return Number.isFinite(value) && value > 0 ? value : undefined;
}
