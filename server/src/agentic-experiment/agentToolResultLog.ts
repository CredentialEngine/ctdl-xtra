import type { SDKMessage } from "@anthropic-ai/claude-agent-sdk";
import { shortToolName } from "./agentToolLog";

export type ToolResultLogEntry = {
  toolUseId?: string;
  toolName?: string;
  isError: boolean;
  text: string;
};

const MAX_TOOL_RESULT_LOG_CHARS = 500;

export class ToolCallTracker {
  private readonly toolNamesByUseId = new Map<string, string>();

  remember(toolUseId: string, toolName: string) {
    if (toolUseId && toolName) {
      this.toolNamesByUseId.set(toolUseId, toolName);
    }
  }

  resolve(toolUseId?: string) {
    if (!toolUseId) {
      return undefined;
    }

    return this.toolNamesByUseId.get(toolUseId);
  }
}

function truncateForLog(text: string) {
  const trimmed = text.trim();
  if (trimmed.length <= MAX_TOOL_RESULT_LOG_CHARS) {
    return trimmed;
  }

  return `${trimmed.slice(0, MAX_TOOL_RESULT_LOG_CHARS)}…`;
}

function textFromContent(content: unknown): string {
  if (typeof content === "string") {
    return content;
  }

  if (!Array.isArray(content)) {
    if (content == null) {
      return "";
    }

    return truncateForLog(String(content));
  }

  const parts: string[] = [];
  for (const block of content) {
    if (typeof block !== "object" || block == null) {
      continue;
    }

    const typed = block as { type?: string; text?: string };
    if (typed.type === "text" && typeof typed.text === "string") {
      parts.push(typed.text);
    }
  }

  if (parts.length) {
    return truncateForLog(parts.join("\n"));
  }

  return truncateForLog(JSON.stringify(content));
}

function entryFromToolResultBlock(
  block: Record<string, unknown>,
  tracker: ToolCallTracker
): ToolResultLogEntry | undefined {
  if (block.type !== "tool_result") {
    return undefined;
  }

  const toolUseId =
    typeof block.tool_use_id === "string" ? block.tool_use_id : undefined;
  const toolName = tracker.resolve(toolUseId);

  return {
    toolUseId,
    toolName,
    isError: block.is_error === true,
    text: textFromContent(block.content),
  };
}

function entriesFromToolUseResult(
  toolUseResult: unknown,
  tracker: ToolCallTracker
): ToolResultLogEntry[] {
  if (toolUseResult == null) {
    return [];
  }

  if (typeof toolUseResult === "string") {
    return [{ isError: false, text: truncateForLog(toolUseResult) }];
  }

  if (Array.isArray(toolUseResult)) {
    const entries: ToolResultLogEntry[] = [];
    for (const item of toolUseResult) {
      if (typeof item !== "object" || item == null) {
        continue;
      }

      const asBlock = item as Record<string, unknown>;
      const fromBlock = entryFromToolResultBlock(asBlock, tracker);
      if (fromBlock) {
        entries.push(fromBlock);
        continue;
      }

      entries.push({
        isError: asBlock.isError === true || asBlock.is_error === true,
        text: textFromContent(asBlock.content ?? asBlock.text ?? item),
      });
    }

    return entries;
  }

  if (typeof toolUseResult !== "object") {
    return [{ isError: false, text: truncateForLog(String(toolUseResult)) }];
  }

  const result = toolUseResult as Record<string, unknown>;
  const toolUseId =
    typeof result.tool_use_id === "string" ? result.tool_use_id : undefined;

  return [
    {
      toolUseId,
      toolName:
        typeof result.tool_name === "string"
          ? result.tool_name
          : tracker.resolve(toolUseId),
      isError: result.isError === true || result.is_error === true,
      text: textFromContent(result.content ?? result.text ?? result.message),
    },
  ];
}

export function extractToolResultsFromUserMessage(
  message: Extract<SDKMessage, { type: "user" }>,
  tracker: ToolCallTracker
): ToolResultLogEntry[] {
  const entries: ToolResultLogEntry[] = [];
  const content = message.message.content;

  if (Array.isArray(content)) {
    for (const block of content) {
      if (typeof block !== "object" || block == null) {
        continue;
      }

      const fromBlock = entryFromToolResultBlock(
        block as unknown as Record<string, unknown>,
        tracker
      );
      if (fromBlock) {
        entries.push(fromBlock);
      }
    }
  }

  if (!entries.length && message.tool_use_result !== undefined) {
    entries.push(...entriesFromToolUseResult(message.tool_use_result, tracker));
  }

  if (!entries.length) {
    return [{ isError: false, text: "" }];
  }

  return entries;
}

export function formatToolResultLabel(entry: ToolResultLogEntry) {
  const name = entry.toolName ? shortToolName(entry.toolName) : "tool";
  return entry.isError ? `[tool error ${name}]` : `[tool ok ${name}]`;
}
