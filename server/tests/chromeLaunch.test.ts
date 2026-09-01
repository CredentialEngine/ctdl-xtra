import { describe, expect, it } from "vitest";
import { buildAgentChromeSession } from "../src/agentic/chrome";
import { puppeteerMcpEnv } from "../src/agentic/puppeteerMcp";
import { PUPPETEER_PROXY_AUTH_ENV } from "../src/agentic/proxyAuthHook";
import {
  parseProxyEndpoint,
  redactProxyUrl,
  sharedChromeArgs,
  sharedPuppeteerLaunchOptions,
} from "../src/extraction/chromeLaunch";

describe("shared Chrome launch", () => {
  it("uses the same launch options for the agent as getCluster", () => {
    const proxyUrl = "http://user:secret@proxy.example:8080";
    const parsed = parseProxyEndpoint(proxyUrl);
    const session = buildAgentChromeSession({ proxyUrl });

    expect(session.launchOptions).toEqual(
      sharedPuppeteerLaunchOptions({ proxyServerUrl: parsed.serverUrl })
    );
    expect(session.launchOptions.args).toEqual(
      sharedChromeArgs({ proxyServerUrl: parsed.serverUrl })
    );
    expect(session.launchOptions.args).not.toContain("--no-sandbox");
    expect(session.launchOptions.args).not.toContain("--single-process");
    expect(session.proxyAuth).toEqual({
      username: "user",
      password: "secret",
    });
  });

  it("does not require an environment flag for launch args", () => {
    const previous = process.env.DOCKER_CONTAINER;
    process.env.DOCKER_CONTAINER = "true";
    try {
      expect(buildAgentChromeSession({}).launchOptions).toEqual(
        sharedPuppeteerLaunchOptions()
      );
    } finally {
      if (previous === undefined) {
        delete process.env.DOCKER_CONTAINER;
      } else {
        process.env.DOCKER_CONTAINER = previous;
      }
    }
  });
});

describe("puppeteerMcpEnv", () => {
  it("passes launch options and a single proxy-auth channel", () => {
    const session = buildAgentChromeSession({
      proxyUrl: "http://user:secret@proxy.example:8080",
      pageLoadWaitTime: 3,
      pageSetup: { enabled: true, steps: [{ type: "wait", seconds: 1 }] },
    });
    const env = puppeteerMcpEnv(session);
    const launchOptions = JSON.parse(env.PUPPETEER_LAUNCH_OPTIONS);

    expect(launchOptions).toEqual(session.launchOptions);
    expect(env[PUPPETEER_PROXY_AUTH_ENV]).toBe(
      JSON.stringify({ username: "user", password: "secret" })
    );
    expect(env).not.toHaveProperty("DOCKER_CONTAINER");
    expect(env).not.toHaveProperty("ALLOW_DANGEROUS");
    expect(launchOptions).not.toHaveProperty("ctdlProxyAuth");
    expect(env.PUPPETEER_PAGE_LOAD_WAIT_TIME).toBe("3");
    expect(JSON.parse(env.PUPPETEER_PAGE_SETUP)).toEqual({
      enabled: true,
      steps: [{ type: "wait", seconds: 1 }],
    });
  });
});

describe("redactProxyUrl", () => {
  it("redacts credentials from proxy URLs", () => {
    expect(redactProxyUrl("http://user:secret@proxy.example:8080")).toBe(
      "http://***:***@proxy.example:8080/"
    );
  });
});
