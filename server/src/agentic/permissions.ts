import type { CanUseTool } from "@anthropic-ai/claude-agent-sdk";

export const PUPPETEER_TOOL_PREFIX = "mcp__puppeteer__";

export const PUPPETEER_ALLOWED_TOOLS = ["ToolSearch", "mcp__puppeteer__*"];

export const allowPuppeteerTools: CanUseTool = async (toolName) => {
  if (toolName === "ToolSearch" || toolName.startsWith(PUPPETEER_TOOL_PREFIX)) {
    return { behavior: "allow" };
  }
  return {
    behavior: "deny",
    message: "This agent session only permits Puppeteer MCP tools.",
  };
};
