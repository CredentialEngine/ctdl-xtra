import { BrowserFetchError } from "./extraction/browser";
import getLogger from "./logging";

const logger = getLogger("utils");

export async function exponentialRetry<T>(
  fn: () => Promise<T>,
  retries: number,
  delay: number = 1000
) {
  let attempt = 0;
  let retryErr: unknown;
  while (attempt <= retries) {
    try {
      return await fn();
    } catch (error) {
      if ((error as any)?.noRetry) {
        throw error;
      }
      logger.warn(
        `Exponential retries fn failed with error ${error}. Details:`
      );
      logger.error(error);
      logger.info("Retrying...");
      retryErr = error;
      if (attempt === retries) throw error;
      await new Promise((resolve) =>
        setTimeout(resolve, delay * Math.pow(2, attempt))
      );
      attempt++;
    }
  }
  logger.error("All retries failed");
  throw retryErr;
}

export async function bestOutOf<T>(
  times: number,
  fn: () => Promise<T>,
  compareWithFn: (result: T) => string
) {
  const results = new Map<string, { count: number; result: T }>();
  let bestResult: T | undefined;
  let maxCount = 0;

  for (let i = 0; i < times; i++) {
    const result = await fn();
    const compareResult = compareWithFn(result);
    const resultCount = (results.get(compareResult)?.count || 0) + 1;
    results.set(compareResult, { count: resultCount + 1, result });

    if (resultCount > maxCount) {
      maxCount = resultCount;
      bestResult = result;
    }
  }

  return bestResult as T;
}

export function unique<T>(array: T[]): T[] {
  return Array.from(new Set(array));
}

export function resolveAbsoluteUrl(base: string, relative: string): string {
  const baseUrl = new URL(base);
  const absoluteUrl = new URL(relative, baseUrl);
  return absoluteUrl.href;
}

/**
 * Checks if a URL is absolute (has protocol)
 */
function isAbsoluteUrl(url: string): boolean {
  try {
    new URL(url);
    return true;
  } catch {
    return false;
  }
}

/**
 * Resolves relative URLs against a base URL when provided.
 */
export function normalizeUrl(url: string, baseUrl?: string): string {
  // If URL is already absolute, return as-is
  if (isAbsoluteUrl(url)) {
    return url;
  }

  // If URL is relative and we have a base URL, resolve it
  if (baseUrl) {
    return resolveAbsoluteUrl(baseUrl, url);
  }

  // If URL is relative but no base URL provided, log warning and return as-is
  logger.warn(`Relative URL "${url}" provided without baseUrl. Attempting to fetch as-is.`);
  return url;
}

export function buildFrontendUrl(suffix: string) {
  let baseUrl = process.env.FRONTEND_URL || "";
  if (!baseUrl.endsWith("/")) {
    baseUrl = `${baseUrl}/`;
  }
  if (suffix.startsWith("/")) {
    suffix = suffix.substring(1);
  }
  return `${baseUrl}${suffix}`;
}

export function isProxyError(error?: Error | BrowserFetchError | string | undefined) {
  const httpStatus = error instanceof BrowserFetchError ? error.status : undefined;
  const errorMessage = error instanceof Error 
    ? error.message
    : typeof error === "string"
      ? error
      : undefined;
  const isPaymentError = httpStatus && httpStatus === 402; // Some proxies use this to indicate lack of funds
  const isBlockedError = httpStatus && httpStatus === 403; // Forbidden often indicates IP/proxy block
  const isTunnelError = errorMessage && errorMessage.includes("net::ERR_TUNNEL_CONNECTION_FAILED");
  const isConnectionRefusedError = errorMessage && errorMessage.includes("net::ERR_CONNECTION_REFUSED");
  const isAuthError = httpStatus && httpStatus === 407; // HTTP 407: Proxy Authentication Required

  return [isPaymentError, isBlockedError, isTunnelError, isConnectionRefusedError, isAuthError].some(Boolean);
}

const HTTP_MESSAGES = {
  400: "Bad Request",
  401: "Unauthorized",
  403: "Forbidden",
  404: "Not Found",
  407: "Proxy related error",
  500: "Webpage server error",
  502: "Bad Gateway",
  503: "Service Unavailable",
  504: "Gateway Timeout",
};

export function httpCodeToMessage(code: keyof typeof HTTP_MESSAGES) {
  return HTTP_MESSAGES[code] || `HTTP ${code}`;
}