import { existsSync } from "fs";
import path from "path";
import type { AgentChromeSession } from "./chrome";
import { PUPPETEER_PROXY_AUTH_ENV } from "./proxyAuthHook";
import { serverPackageRoot } from "./paths";

export function puppeteerMcpCommand(): { command: string; args: string[] } {
  const compiledEntry = path.join(__dirname, "puppeteerMcpServer.js");
  if (existsSync(compiledEntry)) {
    return { command: process.execPath, args: [compiledEntry] };
  }

  const sourceEntry = path.join(__dirname, "puppeteerMcpServer.ts");
  const tsxCli = path.join(
    serverPackageRoot(),
    "node_modules",
    "tsx",
    "dist",
    "cli.mjs"
  );
  if (existsSync(tsxCli)) {
    return { command: process.execPath, args: [tsxCli, sourceEntry] };
  }

  throw new Error(
    "Could not resolve Puppeteer MCP entry (run pnpm run build in server/)"
  );
}

export function puppeteerMcpEnv(
  session: AgentChromeSession
): Record<string, string> {
  const executablePath = session.launchOptions.executablePath;
  return {
    PUPPETEER_LAUNCH_OPTIONS: JSON.stringify(session.launchOptions),
    ALLOW_DANGEROUS: "true",
    ...(typeof executablePath === "string"
      ? { PUPPETEER_EXECUTABLE_PATH: executablePath }
      : {}),
    ...(session.proxyAuth
      ? { [PUPPETEER_PROXY_AUTH_ENV]: JSON.stringify(session.proxyAuth) }
      : {}),
  };
}
