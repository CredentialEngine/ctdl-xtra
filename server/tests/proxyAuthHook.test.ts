import { afterEach, describe, expect, it } from "vitest";
import {
  PUPPETEER_PROXY_AUTH_ENV,
  installProxyAuthHook,
  readProxyAuthFromEnv,
} from "../src/agentic/proxyAuthHook";

describe("readProxyAuthFromEnv", () => {
  afterEach(() => {
    delete process.env[PUPPETEER_PROXY_AUTH_ENV];
  });

  it("returns undefined when env is unset", () => {
    expect(readProxyAuthFromEnv()).toBeUndefined();
  });

  it("parses username and password", () => {
    process.env[PUPPETEER_PROXY_AUTH_ENV] = JSON.stringify({
      username: "proxyuser",
      password: "proxypass",
    });
    expect(readProxyAuthFromEnv()).toEqual({
      username: "proxyuser",
      password: "proxypass",
    });
  });

  it("returns undefined for invalid JSON", () => {
    process.env[PUPPETEER_PROXY_AUTH_ENV] = "not-json";
    expect(readProxyAuthFromEnv()).toBeUndefined();
  });
});

describe("installProxyAuthHook", () => {
  afterEach(() => {
    delete process.env[PUPPETEER_PROXY_AUTH_ENV];
  });

  it("authenticates the initial page and hooks new pages", async () => {
    process.env[PUPPETEER_PROXY_AUTH_ENV] = JSON.stringify({
      username: "user",
      password: "pass",
    });

    const authenticatedPages: string[] = [];
    const page = {
      authenticate: async (auth: { username: string; password: string }) => {
        authenticatedPages.push(`${auth.username}:${auth.password}`);
      },
    };
    const targetHandlers: Array<(target: { type: () => string; page: () => Promise<typeof page | null> }) => Promise<void>> = [];
    const browser = {
      on: (
        event: string,
        handler: (target: {
          type: () => string;
          page: () => Promise<typeof page | null>;
        }) => Promise<void>
      ) => {
        if (event === "targetcreated") {
          targetHandlers.push(handler);
        }
      },
    };

    await installProxyAuthHook(browser as never, page as never);
    expect(authenticatedPages).toEqual(["user:pass"]);

    await targetHandlers[0]?.({
      type: () => "page",
      page: async () => page,
    });
    expect(authenticatedPages).toEqual(["user:pass", "user:pass"]);

    await targetHandlers[0]?.({
      type: () => "service_worker",
      page: async () => page,
    });
    expect(authenticatedPages).toHaveLength(2);
  });
});
