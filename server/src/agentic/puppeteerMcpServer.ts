#!/usr/bin/env node
/**
 * Puppeteer MCP server with proxy-auth hook for CTDL xTRA.
 * Based on @modelcontextprotocol/server-puppeteer@2025.5.12; adds
 * page.authenticate() when PUPPETEER_PROXY_AUTH is set.
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
import { installProxyAuthHook } from "./proxyAuthHook";

const TOOLS = [
  {
    name: "puppeteer_navigate",
    description: "Navigate to a URL",
    inputSchema: {
      type: "object",
      properties: {
        url: { type: "string", description: "URL to navigate to" },
        launchOptions: {
          type: "object",
          description:
            "PuppeteerJS LaunchOptions. Default null. If changed and not null, browser restarts.",
        },
        allowDangerous: {
          type: "boolean",
          description:
            "Allow dangerous LaunchOptions that reduce security. Default false.",
        },
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

const DANGEROUS_ARGS = [
  "--no-sandbox",
  "--disable-setuid-sandbox",
  "--single-process",
  "--disable-web-security",
  "--ignore-certificate-errors",
  "--disable-features=IsolateOrigins",
  "--disable-site-isolation-trials",
  "--allow-running-insecure-content",
];

let browser: Browser | undefined;
let page: Page | undefined;
const consoleLogs: string[] = [];
const screenshots = new Map<string, string>();
let previousLaunchOptions: unknown = null;
let proxyAuthHookInstalled = false;

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

function deepMerge(
  target: Record<string, unknown>,
  source: Record<string, unknown>
): Record<string, unknown> {
  const output: Record<string, unknown> = { ...target };
  if (typeof target !== "object" || typeof source !== "object") {
    return source;
  }
  for (const key of Object.keys(source)) {
    const targetVal = target[key];
    const sourceVal = source[key];
    if (Array.isArray(targetVal) && Array.isArray(sourceVal)) {
      output[key] = [
        ...new Set([
          ...(key === "args" || key === "ignoreDefaultArgs"
            ? (targetVal as string[]).filter(
                (arg) =>
                  !(sourceVal as string[]).some(
                    (launchArg) =>
                      arg.startsWith("--") &&
                      launchArg.startsWith(arg.split("=")[0])
                  )
              )
            : targetVal),
          ...sourceVal,
        ]),
      ];
    } else if (
      sourceVal instanceof Object &&
      key in target &&
      targetVal instanceof Object
    ) {
      output[key] = deepMerge(
        targetVal as Record<string, unknown>,
        sourceVal as Record<string, unknown>
      );
    } else {
      output[key] = sourceVal;
    }
  }
  return output;
}

async function ensureBrowser(args: {
  launchOptions?: Record<string, unknown>;
  allowDangerous?: boolean;
}): Promise<Page> {
  let envConfig: Record<string, unknown> = {};
  try {
    envConfig = JSON.parse(process.env.PUPPETEER_LAUNCH_OPTIONS || "{}");
  } catch (error) {
    console.warn(
      "Failed to parse PUPPETEER_LAUNCH_OPTIONS:",
      error instanceof Error ? error.message : error
    );
  }

  const mergedConfig = deepMerge(envConfig, args.launchOptions || {});

  if (mergedConfig.args && Array.isArray(mergedConfig.args)) {
    const dangerousArgs = (mergedConfig.args as string[]).filter((arg) =>
      DANGEROUS_ARGS.some((dangerousArg) => arg.startsWith(dangerousArg))
    );
    if (
      dangerousArgs.length > 0 &&
      !(args.allowDangerous || process.env.ALLOW_DANGEROUS === "true")
    ) {
      throw new Error(
        `Dangerous browser arguments detected: ${dangerousArgs.join(", ")}. ` +
          "Set allowDangerous: true or ALLOW_DANGEROUS=true to override."
      );
    }
  }

  try {
    if (
      (browser && !browser.connected) ||
      (args.launchOptions &&
        JSON.stringify(args.launchOptions) !==
          JSON.stringify(previousLaunchOptions))
    ) {
      await browser?.close();
      browser = undefined;
      page = undefined;
      proxyAuthHookInstalled = false;
    }
  } catch {
    browser = undefined;
    page = undefined;
    proxyAuthHookInstalled = false;
  }

  previousLaunchOptions = args.launchOptions ?? null;

  if (!browser) {
    const npxArgs = { headless: false };
    const dockerArgs = {
      headless: true,
      args: ["--no-sandbox", "--single-process", "--no-zygote"],
    };
    browser = await puppeteer.launch(
      deepMerge(
        process.env.DOCKER_CONTAINER ? dockerArgs : npxArgs,
        mergedConfig
      ) as Parameters<typeof puppeteer.launch>[0]
    );
    const pages = await browser.pages();
    page = pages[0];
    page.on("console", (msg) => {
      const logEntry = `[${msg.type()}] ${msg.text()}`;
      consoleLogs.push(logEntry);
      server.notification({
        method: "notifications/resources/updated",
        params: { uri: "console://logs" },
      });
    });

    if (!proxyAuthHookInstalled) {
      await installProxyAuthHook(browser, page);
      proxyAuthHookInstalled = true;
    }
  }

  if (!page) {
    throw new Error("Puppeteer page is not available");
  }

  return page;
}

async function handleToolCall(name: string, args: Record<string, unknown>) {
  const activePage = await ensureBrowser({
    launchOptions: args.launchOptions as Record<string, unknown> | undefined,
    allowDangerous: args.allowDangerous as boolean | undefined,
  });

  switch (name) {
    case "puppeteer_navigate":
      await activePage.goto(String(args.url));
      return {
        content: [
          {
            type: "text",
            text: `Navigated to ${args.url}`,
          },
        ],
        isError: false,
      };
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
