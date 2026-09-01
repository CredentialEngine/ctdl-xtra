import type { CanUseTool, McpServerConfig } from "@anthropic-ai/claude-agent-sdk";
import {
  DEFAULT_AGENT_MODEL,
  DEFAULT_MAX_BUDGET_USD,
  DEFAULT_MAX_TURNS,
  type AgentEvent,
  type AgentRunResult,
} from "./types";
import { serverPackageRoot } from "./paths";

export interface AgentQueryRequest {
  prompt: string;
  apiKey: string;
  model?: string;
  maxTurns?: number;
  maxBudgetUsd?: number;
  allowedTools?: string[];
  canUseTool?: CanUseTool;
  mcpServers?: Record<string, McpServerConfig>;
  env?: Record<string, string>;
  onEvent?: (event: AgentEvent) => void;
}

export async function runAgentQuery(
  request: AgentQueryRequest
): Promise<AgentRunResult> {
  const apiKey = request.apiKey.trim();
  if (!apiKey) {
    throw new Error("ANTHROPIC_API_KEY is required");
  }

  const log = request.onEvent ?? (() => undefined);
  const { query } = await import("@anthropic-ai/claude-agent-sdk");
  const toolNames = new Set<string>();
  const toolErrors: string[] = [];

  let resultText = "";
  let numTurns = 0;
  let totalCostUsd = 0;
  let terminalSubtype = "unknown";
  let terminalError: string | undefined;

  for await (const message of query({
    prompt: request.prompt,
    options: {
      cwd: serverPackageRoot(),
      model: request.model ?? DEFAULT_AGENT_MODEL,
      maxTurns: request.maxTurns ?? DEFAULT_MAX_TURNS,
      maxBudgetUsd: request.maxBudgetUsd ?? DEFAULT_MAX_BUDGET_USD,
      permissionMode: "dontAsk",
      settingSources: [],
      canUseTool: request.canUseTool,
      allowedTools: request.allowedTools,
      mcpServers: request.mcpServers,
      env: {
        ...process.env,
        ANTHROPIC_API_KEY: apiKey,
        CLAUDE_AGENT_SDK_CLIENT_APP: "ctdl-xtra",
        ...request.env,
      },
    },
  })) {
    collectToolNames(message, toolNames);

    if (message.type === "assistant") {
      const text = assistantText(message);
      if (text) {
        log({ type: "assistant", message: text });
      }
    }

    if (message.type === "user") {
      const toolResult = toolResultText(message);
      if (toolResult) {
        const isError = toolResult.startsWith("error ");
        if (isError) {
          toolErrors.push(toolResult);
        }
        log({ type: "tool", message: toolResult, isError });
      }
    }

    if (message.type === "result") {
      terminalSubtype = message.subtype;
      numTurns = message.num_turns;
      totalCostUsd = message.total_cost_usd;
      if (message.subtype === "success") {
        resultText = (message.result ?? "").trim();
      } else {
        terminalError = Array.isArray(message.errors)
          ? message.errors.join("; ")
          : message.subtype;
      }
    }
  }

  if (terminalSubtype !== "success" || !resultText) {
    throw new Error(
      terminalError ||
        `Agent query did not complete (subtype=${terminalSubtype})`
    );
  }

  return {
    resultText,
    toolNames: [...toolNames],
    toolErrors,
    numTurns,
    totalCostUsd,
  };
}

function assistantText(message: unknown): string | null {
  const content = (message as { message?: { content?: unknown } }).message
    ?.content;
  if (typeof content === "string") {
    return content.trim() || null;
  }
  if (!Array.isArray(content)) {
    return null;
  }
  const text = content
    .flatMap((block) => {
      if (
        block &&
        typeof block === "object" &&
        "type" in block &&
        (block as { type: string }).type === "text" &&
        "text" in block
      ) {
        return [(block as { text: string }).text];
      }
      return [];
    })
    .join("\n")
    .trim();
  return text || null;
}

function toolResultText(message: unknown): string | null {
  const content = (message as { message?: { content?: unknown } }).message
    ?.content;
  if (!Array.isArray(content)) {
    return null;
  }
  const parts: string[] = [];
  for (const block of content) {
    if (!block || typeof block !== "object") {
      continue;
    }
    const typed = block as {
      type?: string;
      is_error?: boolean;
      content?: unknown;
    };
    if (typed.type !== "tool_result") {
      continue;
    }
    const prefix = typed.is_error ? "error " : "";
    if (typeof typed.content === "string") {
      parts.push(`${prefix}${typed.content}`);
      continue;
    }
    if (Array.isArray(typed.content)) {
      const text = typed.content
        .flatMap((item) =>
          item &&
          typeof item === "object" &&
          "text" in item &&
          typeof (item as { text?: unknown }).text === "string"
            ? [(item as { text: string }).text]
            : []
        )
        .join("\n");
      if (text) {
        parts.push(`${prefix}${text}`);
      }
    }
  }
  const joined = parts.join("\n").trim();
  return joined ? joined.slice(0, 800) : null;
}

function collectToolNames(message: unknown, into: Set<string>) {
  const typed = message as {
    type?: string;
    message?: { content?: unknown };
  };
  if (typed.type !== "assistant") {
    return;
  }
  const content = typed.message?.content;
  if (!Array.isArray(content)) {
    return;
  }
  for (const block of content) {
    if (
      block &&
      typeof block === "object" &&
      (block as { type?: string }).type === "tool_use" &&
      typeof (block as { name?: string }).name === "string"
    ) {
      into.add((block as { name: string }).name);
    }
  }
}
