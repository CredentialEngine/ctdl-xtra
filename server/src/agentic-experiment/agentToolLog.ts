import { colorize } from "./agentLogColors";
import { REGISTER_PAGE_CONTENT_MCP_TOOL } from "./pageRegistry";

export function shortToolName(toolName: string) {
  if (toolName.startsWith("mcp__puppeteer__")) {
    return toolName.replace("mcp__puppeteer__", "puppeteer:");
  }

  if (toolName === REGISTER_PAGE_CONTENT_MCP_TOOL) {
    return "xTRA registerPageContent";
  }

  return toolName;
}

function toolLogStyle(toolName: string) {
  if (toolName === REGISTER_PAGE_CONTENT_MCP_TOOL) {
    return "toolXtra" as const;
  }

  if (toolName.startsWith("mcp__puppeteer__")) {
    return "toolPuppeteer" as const;
  }

  return "toolGeneric" as const;
}

export function formatToolUseForLog(
  toolName: string,
  input: Record<string, unknown>
) {
  let line: string;

  if (toolName === REGISTER_PAGE_CONTENT_MCP_TOOL) {
    const url = typeof input.url === "string" ? input.url : "(missing url)";
    const title = typeof input.title === "string" ? input.title : null;
    const content =
      typeof input.content === "string"
        ? input.content
        : String(input.content ?? "");
    const titleSuffix = title ? ` — ${title}` : "";
    line = `[xTRA registerPageContent] ${url}${titleSuffix} (${content.length} chars)`;
  } else {
    line = `[tool:${toolName}] ${JSON.stringify(input)}`;
  }

  return colorize(toolLogStyle(toolName), line);
}
