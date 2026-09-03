import { findAnthropicApiKey } from "../anthropic";
import { normalizeUrl, isProxyError } from "../utils";
import getLogger from "../logging";
import { buildAgentChromeSession } from "./chrome";
import {
  AGENTIC_RECIPE_ALLOWED_TOOLS,
  PUPPETEER_ALLOWED_TOOLS,
  PUPPETEER_TOOL_PREFIX,
  XTRA_TOOL_PREFIX,
  allowAgenticRecipeTools,
  allowPuppeteerTools,
} from "./permissions";
import { xtraMcpCommand, xtraMcpEnv } from "./xtraMcp";
import {
  PROXY_ROTATE_PREFIX,
  buildAgentProxyAttempts,
  createNavigateResultWatcher,
  formatProxyRotateStatus,
  isAgenticNavigateSuccess,
  isAgenticProxyFailure,
} from "./proxyRotation";
import { puppeteerMcpCommand, puppeteerMcpEnv } from "./puppeteerMcp";
import { runAgentQuery } from "./query";
import type { AgentRunResult, RunBrowserAgentOptions } from "./types";

const logger = getLogger("agentic.browserAgent");

export async function runBrowserAgent(
  options: RunBrowserAgentOptions
): Promise<AgentRunResult> {
  const browser = options.browser ?? {};
  const attempts = await buildAgentProxyAttempts(browser);
  const rotate =
    browser.rotateProxies !== false &&
    !browser.skipProxy &&
    !browser.proxyUrl?.trim() &&
    attempts.length > 1;

  if (!rotate) {
    const result = await runBrowserAgentOnce(options, attempts[0]);
    return {
      ...result,
      proxyUrlUsed: attempts[0],
      proxyAttempts: 1,
    };
  }

  let lastFailure: string | undefined;
  for (let index = 0; index < attempts.length; index++) {
    const proxyUrl = attempts[index];
    const status = formatProxyRotateStatus(
      index + 1,
      attempts.length,
      proxyUrl
    );
    logger.info(status);
    options.onEvent?.({ type: "status", message: status });

    const watcher = createNavigateResultWatcher(options.onEvent);
    try {
      const result = await runBrowserAgentOnce(
        { ...options, onEvent: watcher.onEvent },
        proxyUrl
      );
      const navigate = watcher.firstNavigateResult();
      if (!navigate) {
        throw new Error("Agent finished without a navigation result");
      }
      if (isAgenticNavigateSuccess(navigate.message, navigate.isError)) {
        const successStatus = `${PROXY_ROTATE_PREFIX} attempt ${index + 1}/${attempts.length} succeeded`;
        logger.info(successStatus);
        options.onEvent?.({ type: "status", message: successStatus });
        return {
          ...result,
          proxyUrlUsed: proxyUrl,
          proxyAttempts: index + 1,
        };
      }
      if (isAgenticProxyFailure(navigate.message, navigate.isError)) {
        lastFailure = navigate.message;
        const failStatus = `${PROXY_ROTATE_PREFIX} attempt ${index + 1}/${attempts.length} failed (proxy)`;
        logger.warn(failStatus);
        options.onEvent?.({ type: "status", message: failStatus });
        continue;
      }
      if (!navigate.isError) {
        return {
          ...result,
          proxyUrlUsed: proxyUrl,
          proxyAttempts: index + 1,
        };
      }
      throw new Error(navigate.message);
    } catch (error) {
      const message =
        error instanceof Error ? error.message : "Browser agent failed";
      if (
        isProxyError(error instanceof Error ? error : message) ||
        isAgenticProxyFailure(message)
      ) {
        lastFailure = message;
        const failStatus = `${PROXY_ROTATE_PREFIX} attempt ${index + 1}/${attempts.length} failed (proxy)`;
        logger.warn(`${failStatus}: ${message}`);
        options.onEvent?.({ type: "status", message: failStatus });
        continue;
      }
      throw error;
    }
  }

  throw new Error(
    `Browser agent failed after ${attempts.length} proxy attempts. Last error: ${lastFailure ?? "unknown"}`
  );
}

async function runBrowserAgentOnce(
  options: RunBrowserAgentOptions,
  proxyUrl: string | undefined
): Promise<AgentRunResult> {
  const browser = options.browser ?? {};
  const apiKey = options.apiKey?.trim() || (await findAnthropicApiKey());
  const session = buildAgentChromeSession({
    proxyUrl,
    pageLoadWaitTime: browser.pageLoadWaitTime,
    pageSetup: browser.pageSetup,
  });

  const mcp = puppeteerMcpCommand();
  const mcpEnv = puppeteerMcpEnv(session);

  logger.info(
    `Starting Claude agent query (mcp=${mcp.command} ${mcp.args.join(" ")}${proxyUrl ? " via proxy" : ""})`
  );
  options.onEvent?.({
    type: "status",
    message: `Starting browser agent${proxyUrl ? " via proxy" : ""}`,
  });

  const agenticRecipe = options.agenticRecipe;
  const mcpServers: Record<
    string,
    { command: string; args: string[]; env: Record<string, string> }
  > = {
    puppeteer: {
      command: mcp.command,
      args: mcp.args,
      env: mcpEnv,
    },
  };
  if (agenticRecipe) {
    const xtra = xtraMcpCommand();
    mcpServers.xtra = {
      command: xtra.command,
      args: xtra.args,
      env: {
        ...xtraMcpEnv({
          recipeId: agenticRecipe.recipeId,
          pageLoadWaitTime: browser.pageLoadWaitTime,
          pageSetup: browser.pageSetup,
        }),
      },
    };
  }

  const result = await runAgentQuery({
    prompt: options.prompt,
    apiKey,
    model: options.model,
    maxTurns: options.maxTurns,
    maxBudgetUsd: options.maxBudgetUsd,
    allowedTools: agenticRecipe
      ? AGENTIC_RECIPE_ALLOWED_TOOLS
      : PUPPETEER_ALLOWED_TOOLS,
    canUseTool: agenticRecipe ? allowAgenticRecipeTools : allowPuppeteerTools,
    mcpServers,
    onEvent: options.onEvent,
  });

  const requireBrowserTool = options.requireBrowserTool !== false;
  const usedBrowser = result.toolNames.some((name) =>
    name.startsWith(PUPPETEER_TOOL_PREFIX)
  );
  const usedXtra = result.toolNames.some((name) =>
    name.startsWith(XTRA_TOOL_PREFIX)
  );
  if (requireBrowserTool && !usedBrowser) {
    throw new Error("Agent finished without calling a Puppeteer MCP tool");
  }
  if (options.agenticRecipe && !usedXtra) {
    throw new Error("Agent finished without calling an xTRA MCP tool");
  }

  return result;
}

export function agentTargetUrl(url: string, baseUrl?: string): string {
  return normalizeUrl(url, baseUrl);
}
