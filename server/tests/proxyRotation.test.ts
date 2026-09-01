import { afterEach, describe, expect, it, vi } from "vitest";
import {
  formatNavigateToolResult,
  parseNavigateToolResult,
} from "../src/agentic/navigateResult";
import {
  buildAgentProxyAttempts,
  createNavigateResultWatcher,
  isAgenticNavigateSuccess,
  isAgenticProxyFailure,
} from "../src/agentic/proxyRotation";

vi.mock("../src/extraction/browser", () => ({
  findProxies: vi.fn(),
}));

import { findProxies } from "../src/extraction/browser";

const findProxiesMock = vi.mocked(findProxies);

describe("buildAgentProxyAttempts", () => {
  afterEach(() => {
    vi.clearAllMocks();
  });

  it("returns direct only when skipProxy is set", async () => {
    await expect(buildAgentProxyAttempts({ skipProxy: true })).resolves.toEqual([
      undefined,
    ]);
  });

  it("returns a single explicit proxy without direct attempt", async () => {
    await expect(
      buildAgentProxyAttempts({ proxyUrl: "http://user:pass@proxy.example:8080" })
    ).resolves.toEqual(["http://user:pass@proxy.example:8080"]);
  });

  it("defaults to direct first then each configured proxy", async () => {
    findProxiesMock.mockResolvedValue([
      "http://a.example:1",
      "http://b.example:2",
    ]);
    await expect(buildAgentProxyAttempts({})).resolves.toEqual([
      undefined,
      "http://a.example:1",
      "http://b.example:2",
    ]);
  });

  it("omits direct attempt when rotateProxies is false", async () => {
    findProxiesMock.mockResolvedValue(["http://a.example:1"]);
    await expect(
      buildAgentProxyAttempts({ rotateProxies: false })
    ).resolves.toEqual(["http://a.example:1"]);
  });
});

describe("navigate tool result", () => {
  it("round-trips a successful navigate payload", () => {
    const text = formatNavigateToolResult({
      ok: true,
      kind: "navigate",
      url: "https://example.com",
    });
    expect(parseNavigateToolResult(text)).toEqual({
      ok: true,
      kind: "navigate",
      url: "https://example.com",
    });
    expect(isAgenticNavigateSuccess(text, false)).toBe(true);
    expect(isAgenticProxyFailure(text, false)).toBe(false);
  });

  it("detects structured proxy failures, including the error prefix", () => {
    const text = formatNavigateToolResult({
      ok: false,
      kind: "proxy",
      url: "https://example.com",
      status: 407,
      message: "HTTP 407 for https://example.com",
    });
    const prefixed = `error ${text}`;
    expect(parseNavigateToolResult(prefixed)?.kind).toBe("proxy");
    expect(isAgenticProxyFailure(prefixed, true)).toBe(true);
    expect(isAgenticNavigateSuccess(prefixed, true)).toBe(false);
  });

  it("does not treat chrome error-page titles as proxy failure", () => {
    expect(
      isAgenticProxyFailure(
        "Navigated to https://example.com\nHTTP ERROR 407",
        false
      )
    ).toBe(false);
  });
});

describe("createNavigateResultWatcher", () => {
  it("captures the first navigate tool result only", () => {
    const events: string[] = [];
    const watcher = createNavigateResultWatcher((event) => {
      if (event.type === "tool") {
        events.push(event.message);
      }
    });

    const failure = formatNavigateToolResult({
      ok: false,
      kind: "proxy",
      url: "https://example.com",
      status: 407,
    });
    watcher.onEvent({
      type: "tool",
      message: `error ${failure}`,
      isError: true,
    });
    watcher.onEvent({
      type: "tool",
      message: formatNavigateToolResult({
        ok: true,
        kind: "navigate",
        url: "https://example.com",
      }),
      isError: false,
    });

    expect(events).toHaveLength(2);
    expect(watcher.firstNavigateResult()?.isError).toBe(true);
    expect(parseNavigateToolResult(watcher.firstNavigateResult()!.message)?.kind).toBe(
      "proxy"
    );
  });
});
