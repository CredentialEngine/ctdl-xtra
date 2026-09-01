import { existsSync } from "fs";
import {
  dockerChromeArgs,
  parseProxyEndpoint,
  sharedChromeArgs,
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

function chromeExecutablePath(): string | undefined {
  const fromEnv = process.env.PUPPETEER_EXECUTABLE_PATH?.trim();
  if (fromEnv) {
    return fromEnv;
  }
  const candidates = [
    "/usr/bin/google-chrome-stable",
    "/usr/bin/google-chrome",
    "/usr/bin/chromium",
    "/usr/bin/chromium-browser",
  ];
  return candidates.find((candidate) => existsSync(candidate));
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

  const executablePath = chromeExecutablePath();
  const launchOptions: Record<string, unknown> = {
    headless: true,
    ignoreHTTPSErrors: true,
    ...(executablePath ? { executablePath } : {}),
    args: [
      ...dockerChromeArgs(),
      ...sharedChromeArgs({ proxyServerUrl: parsed?.serverUrl }),
    ],
  };

  const proxyAuth =
    parsed?.username || parsed?.password
      ? { username: parsed.username || "", password: parsed.password || "" }
      : undefined;

  return {
    launchOptions,
    proxyAuth,
    pageLoadWaitTime: options.pageLoadWaitTime,
    pageSetup: options.pageSetup,
  };
}
