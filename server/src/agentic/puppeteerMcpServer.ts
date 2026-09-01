#!/usr/bin/env node
/**
 * Puppeteer MCP server for CTDL xTRA.
 * Launch options and proxy auth come from the parent worker via env;
 * page setup runs in-process after navigate.
 */
import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import {
  CallToolRequestSchema,
  ListResourcesRequestSchema,
  ListToolsRequestSchema,
  ReadResourceRequestSchema,
} from "@modelcontextprotocol/sdk/types.js";
import puppeteer, { type Browser, type Page } from "rebrowser-puppeteer";
import { isProxyError } from "../utils";
import { applyPageSetupSteps } from "../extraction/pageSetup";
import {
  formatNavigateToolResult,
} from "./navigateResult";
import {
  installProxyAuthHook,
  applyProxyAuthToPage,
  readProxyAuthFromEnv,
} from "./proxyAuthHook";
import {
  readPageLoadWaitTimeFromEnv,
  readPageSetupFromEnv,
} from "./puppeteerMcp";

const TOOLS = [
  {
    name: "puppeteer_navigate",
    description: "Navigate to a URL",
    inputSchema: {
      type: "object",
      properties: {
        url: { type: "string", description: "URL to navigate to" },
      },
      required: ["url"],
    },
  },
  {
    name: "puppeteer_screenshot",
    description: "Take a screenshot of the current page or a specific element",
    inputSchema: {
      type: "object",
      properties: {
        name: { type: "string", description: "Name for the screenshot" },
        selector: {
          type: "string",
          description: "CSS selector for element to screenshot",
        },
        width: { type: "number", description: "Width in pixels (default: 800)" },
        height: {
          type: "number",
          description: "Height in pixels (default: 600)",
        },
        encoded: {
          type: "boolean",
          description:
            "If true, capture the screenshot as a base64-encoded data URI. Default false.",
        },
      },
      required: ["name"],
    },
  },
  {
    name: "puppeteer_click",
    description: "Click an element on the page",
    inputSchema: {
      type: "object",
      properties: {
        selector: {
          type: "string",
          description: "CSS selector for element to click",
        },
      },
      required: ["selector"],
    },
  },
  {
    name: "puppeteer_fill",
    description: "Fill out an input field",
    inputSchema: {
      type: "object",
      properties: {
        selector: {
          type: "string",
          description: "CSS selector for input field",
        },
        value: { type: "string", description: "Value to fill" },
      },
      required: ["selector", "value"],
    },
  },
  {
    name: "puppeteer_select",
    description: "Select an element on the page with Select tag",
    inputSchema: {
      type: "object",
      properties: {
        selector: {
          type: "string",
          description: "CSS selector for element to select",
        },
        value: { type: "string", description: "Value to select" },
      },
      required: ["selector", "value"],
    },
  },
  {
    name: "puppeteer_hover",
    description: "Hover an element on the page",
    inputSchema: {
      type: "object",
      properties: {
        selector: {
          type: "string",
          description: "CSS selector for element to hover",
        },
      },
      required: ["selector"],
    },
  },
  {
    name: "puppeteer_evaluate",
    description: "Execute JavaScript in the browser console",
    inputSchema: {
      type: "object",
      properties: {
        script: { type: "string", description: "JavaScript code to execute" },
      },
      required: ["script"],
    },
  },
] as const;

const PAGE_TIMEOUT = 5 * 60 * 1000;

let browser: Browser | undefined;
let page: Page | undefined;
const consoleLogs: string[] = [];
const screenshots = new Map<string, string>();
let proxyAuthHookInstalled = false;
let activeProxyAuth: ReturnType<typeof readProxyAuthFromEnv>;

const server = new Server(
  {
    name: "ctdl-xtra/puppeteer",
    version: "0.1.0",
  },
  {
    capabilities: {
      resources: {},
      tools: {},
    },
  }
);

function readLaunchOptionsFromEnv(): Record<string, unknown> {
  try {
    return JSON.parse(process.env.PUPPETEER_LAUNCH_OPTIONS || "{}") as Record<
      string,
      unknown
    >;
  } catch (error) {
    console.error(
      "Failed to parse PUPPETEER_LAUNCH_OPTIONS:",
      error instanceof Error ? error.message : error
    );
    return {};
  }
}

function proxyFailureToolResult(
  url: string,
  status?: number | null,
  message?: string
) {
  return {
    content: [
      {
        type: "text" as const,
        text: formatNavigateToolResult({
          ok: false,
          kind: "proxy",
          url,
          status,
          message,
        }),
      },
    ],
    isError: true,
  };
}

async function ensureBrowser(): Promise<Page> {
  activeProxyAuth = readProxyAuthFromEnv();

  if (browser && !browser.connected) {
    try {
      await browser.close();
    } catch {
      // Browser already gone.
    }
    browser = undefined;
    page = undefined;
    proxyAuthHookInstalled = false;
  }

  if (!browser) {
    const launchOptions = readLaunchOptionsFromEnv();
    browser = await puppeteer.launch(
      launchOptions as Parameters<typeof puppeteer.launch>[0]
    );
    const pages = await browser.pages();
    page = pages[0] ?? (await browser.newPage());
    page.on("console", (msg) => {
      const logEntry = `[${msg.type()}] ${msg.text()}`;
      consoleLogs.push(logEntry);
      server.notification({
        method: "notifications/resources/updated",
        params: { uri: "console://logs" },
      });
    });

    if (!proxyAuthHookInstalled) {
      await installProxyAuthHook(browser, page, activeProxyAuth);
      proxyAuthHookInstalled = true;
    }
  }

  if (!page) {
    throw new Error("Puppeteer page is not available");
  }

  return page;
}

async function handleToolCall(name: string, args: Record<string, unknown>) {
  const activePage = await ensureBrowser();

  switch (name) {
    case "puppeteer_navigate": {
      const targetUrl = String(args.url);
      await applyProxyAuthToPage(activePage, activeProxyAuth);
      try {
        const response = await activePage.goto(targetUrl, {
          timeout: PAGE_TIMEOUT,
          waitUntil: "networkidle2",
        });
        const status = response?.status() ?? null;
        if (status === 402 || status === 403 || status === 407) {
          return proxyFailureToolResult(
            targetUrl,
            status,
            `HTTP ${status} for ${targetUrl}`
          );
        }
        await applyPageSetupSteps(
          activePage,
          targetUrl,
          readPageSetupFromEnv()
        );
        const waitSeconds = readPageLoadWaitTimeFromEnv();
        if (waitSeconds) {
          await new Promise((resolve) =>
            setTimeout(resolve, waitSeconds * 1000)
          );
        }
        return {
          content: [
            {
              type: "text" as const,
              text: formatNavigateToolResult({
                ok: true,
                kind: "navigate",
                url: targetUrl,
              }),
            },
          ],
          isError: false,
        };
      } catch (error) {
        const message =
          error instanceof Error ? error.message : String(error);
        if (isProxyError(error instanceof Error ? error : message)) {
          return proxyFailureToolResult(targetUrl, undefined, message);
        }
        return {
          content: [
            {
              type: "text" as const,
              text: `Failed to navigate to ${targetUrl}: ${message}`,
            },
          ],
          isError: true,
        };
      }
    }
    case "puppeteer_screenshot": {
      const width = (args.width as number | undefined) ?? 800;
      const height = (args.height as number | undefined) ?? 600;
      const encoded = (args.encoded as boolean | undefined) ?? false;
      await activePage.setViewport({ width, height });
      const selector = args.selector as string | undefined;
      const screenshot = await (selector
        ? (await activePage.$(selector))?.screenshot({ encoding: "base64" })
        : activePage.screenshot({ encoding: "base64", fullPage: false }));
      if (!screenshot) {
        return {
          content: [
            {
              type: "text",
              text: selector
                ? `Element not found: ${selector}`
                : "Screenshot failed",
            },
          ],
          isError: true,
        };
      }
      screenshots.set(String(args.name), screenshot);
      server.notification({
        method: "notifications/resources/list_changed",
      });
      return {
        content: [
          {
            type: "text",
            text: `Screenshot '${args.name}' taken at ${width}x${height}`,
          },
          encoded
            ? {
                type: "text",
                text: `data:image/png;base64,${screenshot}`,
              }
            : {
                type: "image",
                data: screenshot,
                mimeType: "image/png",
              },
        ],
        isError: false,
      };
    }
    case "puppeteer_click":
      try {
        await activePage.click(String(args.selector));
        return {
          content: [{ type: "text", text: `Clicked: ${args.selector}` }],
          isError: false,
        };
      } catch (error) {
        return {
          content: [
            {
              type: "text",
              text: `Failed to click ${args.selector}: ${
                error instanceof Error ? error.message : error
              }`,
            },
          ],
          isError: true,
        };
      }
    case "puppeteer_fill":
      try {
        await activePage.waitForSelector(String(args.selector));
        await activePage.type(String(args.selector), String(args.value));
        return {
          content: [
            {
              type: "text",
              text: `Filled ${args.selector} with: ${args.value}`,
            },
          ],
          isError: false,
        };
      } catch (error) {
        return {
          content: [
            {
              type: "text",
              text: `Failed to fill ${args.selector}: ${
                error instanceof Error ? error.message : error
              }`,
            },
          ],
          isError: true,
        };
      }
    case "puppeteer_select":
      try {
        await activePage.waitForSelector(String(args.selector));
        await activePage.select(String(args.selector), String(args.value));
        return {
          content: [
            {
              type: "text",
              text: `Selected ${args.selector} with: ${args.value}`,
            },
          ],
          isError: false,
        };
      } catch (error) {
        return {
          content: [
            {
              type: "text",
              text: `Failed to select ${args.selector}: ${
                error instanceof Error ? error.message : error
              }`,
            },
          ],
          isError: true,
        };
      }
    case "puppeteer_hover":
      try {
        await activePage.waitForSelector(String(args.selector));
        await activePage.hover(String(args.selector));
        return {
          content: [{ type: "text", text: `Hovered ${args.selector}` }],
          isError: false,
        };
      } catch (error) {
        return {
          content: [
            {
              type: "text",
              text: `Failed to hover ${args.selector}: ${
                error instanceof Error ? error.message : error
              }`,
            },
          ],
          isError: true,
        };
      }
    case "puppeteer_evaluate":
      try {
        await activePage.evaluate(() => {
          (window as unknown as { mcpHelper?: unknown }).mcpHelper = {
            logs: [] as string[],
            originalConsole: { ...console },
          };
          const helper = (window as unknown as {
            mcpHelper: {
              logs: string[];
              originalConsole: Console;
            };
          }).mcpHelper;
          (["log", "info", "warn", "error"] as const).forEach((method) => {
            console[method] = (...logArgs: unknown[]) => {
              helper.logs.push(
                `[${method}] ${logArgs.map(String).join(" ")}`
              );
              helper.originalConsole[method](...logArgs);
            };
          });
        });
        const result = await activePage.evaluate(String(args.script));
        const logs = await activePage.evaluate(() => {
          const helper = (window as unknown as {
            mcpHelper: {
              logs: string[];
              originalConsole: Console;
            };
          }).mcpHelper;
          Object.assign(console, helper.originalConsole);
          const collected = helper.logs;
          delete (window as unknown as { mcpHelper?: unknown }).mcpHelper;
          return collected;
        });
        return {
          content: [
            {
              type: "text",
              text: `Execution result:\n${JSON.stringify(result, null, 2)}\n\nConsole output:\n${logs.join("\n")}`,
            },
          ],
          isError: false,
        };
      } catch (error) {
        return {
          content: [
            {
              type: "text",
              text: `Script execution failed: ${
                error instanceof Error ? error.message : error
              }`,
            },
          ],
          isError: true,
        };
      }
    default:
      return {
        content: [{ type: "text", text: `Unknown tool: ${name}` }],
        isError: true,
      };
  }
}

server.setRequestHandler(ListResourcesRequestSchema, async () => ({
  resources: [
    {
      uri: "console://logs",
      mimeType: "text/plain",
      name: "Browser console logs",
    },
    ...Array.from(screenshots.keys()).map((name) => ({
      uri: `screenshot://${name}`,
      mimeType: "image/png",
      name: `Screenshot: ${name}`,
    })),
  ],
}));

server.setRequestHandler(ReadResourceRequestSchema, async (request) => {
  const uri = request.params.uri.toString();
  if (uri === "console://logs") {
    return {
      contents: [
        {
          uri,
          mimeType: "text/plain",
          text: consoleLogs.join("\n"),
        },
      ],
    };
  }
  if (uri.startsWith("screenshot://")) {
    const name = uri.split("://")[1];
    const screenshot = screenshots.get(name);
    if (screenshot) {
      return {
        contents: [
          {
            uri,
            mimeType: "image/png",
            blob: screenshot,
          },
        ],
      };
    }
  }
  throw new Error(`Resource not found: ${uri}`);
});

server.setRequestHandler(ListToolsRequestSchema, async () => ({
  tools: [...TOOLS],
}));

server.setRequestHandler(CallToolRequestSchema, async (request) =>
  handleToolCall(
    request.params.name,
    (request.params.arguments ?? {}) as Record<string, unknown>
  )
);

async function runServer() {
  const transport = new StdioServerTransport();
  await server.connect(transport);
}

runServer().catch(console.error);

process.stdin.on("close", () => {
  console.error("Puppeteer MCP Server closed");
  server.close();
});
