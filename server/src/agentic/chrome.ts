import {
  parseProxyEndpoint,
  sharedPuppeteerLaunchOptions,
  type ParsedProxyEndpoint,
} from "../extraction/chromeLaunch";
import type { AgentBrowserOptions } from "./types";

export interface AgentChromeSession {
  launchOptions: Record<string, unknown>;
  /** Passed to the Puppeteer MCP subprocess for `page.authenticate()`. */
  proxyAuth?: { username: string; password: string };
  pageLoadWaitTime?: number;
  pageSetup?: AgentBrowserOptions["pageSetup"];
}

export function buildAgentChromeSession(options: {
  proxyUrl?: string;
  pageLoadWaitTime?: number;
  pageSetup?: AgentBrowserOptions["pageSetup"];
}): AgentChromeSession {
  let parsed: ParsedProxyEndpoint | undefined;
  if (options.proxyUrl) {
    parsed = parseProxyEndpoint(options.proxyUrl);
  }

  const proxyAuth =
    parsed?.username || parsed?.password
      ? { username: parsed.username || "", password: parsed.password || "" }
      : undefined;

  return {
    launchOptions: sharedPuppeteerLaunchOptions({
      proxyServerUrl: parsed?.serverUrl,
    }),
    proxyAuth,
    pageLoadWaitTime: options.pageLoadWaitTime,
    pageSetup: options.pageSetup,
  };
}
