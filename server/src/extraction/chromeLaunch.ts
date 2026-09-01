/** Chrome launch flags shared by `fetchBrowserPage`/`getCluster` and the agentic Puppeteer MCP. */

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

/** Extra flags required to run Chrome inside the worker container. */
export function dockerChromeArgs(): string[] {
  return ["--no-sandbox", "--disable-setuid-sandbox", "--disable-gpu"];
}
