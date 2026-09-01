/** Chrome launch flags shared by `getCluster`, dynamic discovery, and the agentic Puppeteer MCP. */

export type ParsedProxyEndpoint = {
  /** `protocol://host:port` for Chrome `--proxy-server`. */
  serverUrl: string;
  username?: string;
  password?: string;
};

export function parseProxyEndpoint(proxyUrl: string): ParsedProxyEndpoint {
  const url = new URL(proxyUrl);
  return {
    serverUrl: `${url.protocol}//${url.host}`,
    username: url.username || undefined,
    password: url.password || undefined,
  };
}

export function redactProxyUrl(proxyUrl: string): string {
  try {
    const url = new URL(proxyUrl);
    if (url.username) {
      url.username = "***";
    }
    if (url.password) {
      url.password = "***";
    }
    return url.toString();
  } catch {
    return "(invalid-url)";
  }
}

/** Flags used by `getCluster` for every fetch (with or without a proxy). */
export function sharedChromeArgs(options?: { proxyServerUrl?: string }): string[] {
  return [
    "--disable-dev-shm-usage",
    "--font-render-hinting=none",
    "--force-gpu-mem-available-mb=4096",
    "--ignore-certificate-errors",
    options?.proxyServerUrl ? `--proxy-server=${options.proxyServerUrl}` : "",
  ].filter(Boolean);
}

/** Puppeteer launch options shared by `getCluster` and the agentic Chrome session. */
export function sharedPuppeteerLaunchOptions(options?: {
  proxyServerUrl?: string;
}): {
  headless: true;
  ignoreHTTPSErrors: true;
  args: string[];
} {
  return {
    headless: true,
    ignoreHTTPSErrors: true,
    args: sharedChromeArgs({ proxyServerUrl: options?.proxyServerUrl }),
  };
}
