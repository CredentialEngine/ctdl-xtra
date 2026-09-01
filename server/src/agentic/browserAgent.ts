import { findAnthropicApiKey } from "../anthropic";
import { findProxies } from "../extraction/browser";
import { normalizeUrl } from "../utils";
import getLogger from "../logging";
import { buildAgentChromeSession } from "./chrome";
import {
  PUPPETEER_ALLOWED_TOOLS,
  PUPPETEER_TOOL_PREFIX,
  allowPuppeteerTools,
} from "./permissions";
import { puppeteerMcpCommand, puppeteerMcpEnv } from "./puppeteerMcp";
import { runAgentQuery } from "./query";
import type { RunBrowserAgentOptions } from "./types";

const logger = getLogger("agentic.browserAgent");

export async function runBrowserAgent(options: RunBrowserAgentOptions) {
  const browser = options.browser ?? {};
  const apiKey = options.apiKey?.trim() || (await findAnthropicApiKey());
  const proxyUrl = await resolveProxyUrl(browser);
  const session = buildAgentChromeSession({
    proxyUrl,
    pageLoadWaitTime: browser.pageLoadWaitTime,
    pageSetup: browser.pageSetup,
  });

  const mcp = puppeteerMcpCommand();
  const mcpEnv = puppeteerMcpEnv(session);
  if (session.proxyAuth) {
    logger.info("Proxy credentials will be applied via Puppeteer MCP page hook");
  }
  options.onEvent?.({
    type: "status",
    message: `Chrome ${String(session.launchOptions.executablePath ?? "puppeteer default")}${proxyUrl ? " via proxy" : ""}${session.proxyAuth ? " (proxy auth)" : ""}`,
  });

  const result = await runAgentQuery({
    prompt: options.prompt,
    apiKey,
    model: options.model,
    maxTurns: options.maxTurns,
    maxBudgetUsd: options.maxBudgetUsd,
    allowedTools: PUPPETEER_ALLOWED_TOOLS,
    canUseTool: allowPuppeteerTools,
    mcpServers: {
      puppeteer: {
        command: mcp.command,
        args: mcp.args,
        env: mcpEnv,
      },
    },
    env: mcpEnv,
    onEvent: options.onEvent,
  });

  const requireBrowserTool = options.requireBrowserTool !== false;
  const usedBrowser = result.toolNames.some((name) =>
    name.startsWith(PUPPETEER_TOOL_PREFIX)
  );
  if (requireBrowserTool && !usedBrowser) {
    throw new Error("Agent finished without calling a Puppeteer MCP tool");
  }

  return result;
}

async function resolveProxyUrl(
  browser: NonNullable<RunBrowserAgentOptions["browser"]>
): Promise<string | undefined> {
  if (browser.skipProxy) {
    return undefined;
  }
  if (browser.proxyUrl?.trim()) {
    return browser.proxyUrl.trim();
  }
  const proxies = await findProxies();
  return proxies?.[0];
}

export function agentTargetUrl(url: string, baseUrl?: string): string {
  return normalizeUrl(url, baseUrl);
}
