import type { Browser, Page } from "rebrowser-puppeteer";

/** JSON `{ username, password }` passed to the Puppeteer MCP subprocess. */
export const PUPPETEER_PROXY_AUTH_ENV = "PUPPETEER_PROXY_AUTH";

export type ProxyAuthCredentials = {
  username: string;
  password: string;
};

export function readProxyAuthFromEnv(): ProxyAuthCredentials | undefined {
  const raw = process.env[PUPPETEER_PROXY_AUTH_ENV]?.trim();
  if (!raw) {
    return undefined;
  }
  let parsed: unknown;
  try {
    parsed = JSON.parse(raw);
  } catch {
    return undefined;
  }
  if (!parsed || typeof parsed !== "object") {
    return undefined;
  }
  const { username, password } = parsed as {
    username?: unknown;
    password?: unknown;
  };
  if (!username && !password) {
    return undefined;
  }
  return {
    username: typeof username === "string" ? username : "",
    password: typeof password === "string" ? password : "",
  };
}

export async function authenticatePage(
  page: Page,
  auth: ProxyAuthCredentials
): Promise<void> {
  await page.authenticate(auth);
}

/** Applies proxy auth to the active page and future pages on this browser. */
export async function installProxyAuthHook(
  browser: Browser,
  page: Page
): Promise<void> {
  const auth = readProxyAuthFromEnv();
  if (!auth) {
    return;
  }

  await authenticatePage(page, auth);

  browser.on("targetcreated", async (target) => {
    if (target.type() !== "page") {
      return;
    }
    const newPage = await target.page();
    if (newPage) {
      await authenticatePage(newPage, auth);
    }
  });
}
