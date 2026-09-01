import { findProxies } from "../extraction/browser";
import { isProxyError } from "../utils";
import { redactProxyUrl } from "../extraction/chromeLaunch";
import { parseNavigateToolResult } from "./navigateResult";
import type { AgentBrowserOptions, AgentEvent } from "./types";

export const PROXY_ROTATE_PREFIX = "[proxyRotate]";

/** `[undefined, ...proxies]` by default; mirrors fetchBrowserPage / discoverDynamicLinks. */
export async function buildAgentProxyAttempts(
  browser: AgentBrowserOptions
): Promise<Array<string | undefined>> {
  if (browser.skipProxy) {
    return [undefined];
  }
  if (browser.proxyUrl?.trim()) {
    return [browser.proxyUrl.trim()];
  }

  const proxies = await findProxies();
  if (browser.rotateProxies === false) {
    return proxies?.length ? proxies : [undefined];
  }
  return [undefined, ...(proxies ?? [])];
}

export function isAgenticProxyFailure(
  message: string,
  _isError?: boolean
): boolean {
  const parsed = parseNavigateToolResult(message);
  if (parsed?.kind === "proxy") {
    return true;
  }
  return isProxyError(message);
}

export function isAgenticNavigateSuccess(
  message: string,
  isError?: boolean
): boolean {
  if (isError || isAgenticProxyFailure(message, isError)) {
    return false;
  }
  const parsed = parseNavigateToolResult(message);
  if (parsed) {
    return parsed.ok;
  }
  return /^Navigated to /m.test(message.trim());
}

export function formatProxyRotateStatus(
  attempt: number,
  total: number,
  proxyUrl: string | undefined
): string {
  const target = proxyUrl
    ? `proxy=${redactProxyUrl(proxyUrl)}`
    : "mode=direct";
  return `${PROXY_ROTATE_PREFIX} attempt ${attempt}/${total} ${target}`;
}

export function createNavigateResultWatcher(
  onEvent?: (event: AgentEvent) => void
): {
  onEvent: (event: AgentEvent) => void;
  firstNavigateResult: () =>
    | { message: string; isError?: boolean }
    | undefined;
} {
  let captured: { message: string; isError?: boolean } | undefined;

  return {
    onEvent: (event) => {
      if (event.type === "tool" && !captured) {
        const message = event.message.trim();
        const parsed = parseNavigateToolResult(message);
        if (
          parsed ||
          message.startsWith("Navigated to ") ||
          message.startsWith("error Navigated to ")
        ) {
          captured = { message: event.message, isError: event.isError };
        }
      }
      onEvent?.(event);
    },
    firstNavigateResult: () => captured,
  };
}
