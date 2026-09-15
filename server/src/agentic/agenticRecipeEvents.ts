import {
  AgenticRecipeStage,
  isAgenticRecipeStage,
} from "../../../common/types";
import { agenticRecipeStageLog } from "../../../common/recipe";
import type { AgentEvent } from "./types";

export interface ParsedXtraEvent {
  kind:
    | "stage"
    | "progress"
    | "verify"
    | "submit"
    | "test_extraction"
    | "give_up";
  stage?: AgenticRecipeStage;
  changed?: boolean;
  message?: string;
  matchCount?: number;
  extracted?: boolean;
  url?: string;
  entryCount?: number;
}

export type FormattedAgentLog =
  | { kind: "status"; message: string }
  | { kind: "tool"; message: string }
  | { kind: "stage"; stage: AgenticRecipeStage }
  | { kind: "plain"; message: string };

export function parseXtraToolResult(message: string): ParsedXtraEvent | null {
  const trimmed = message.trim();
  if (!trimmed.startsWith("{")) {
    return null;
  }
  try {
    const parsed = JSON.parse(trimmed) as {
      xtraEvent?: boolean;
      kind?: string;
      stage?: unknown;
      changed?: boolean;
      message?: string;
      matchCount?: number;
      extracted?: boolean;
      url?: unknown;
      linkRegexp?: unknown;
      entryCount?: number;
    };
    if (!parsed.xtraEvent || !parsed.kind) {
      return null;
    }
    if (
      parsed.kind !== "stage" &&
      parsed.kind !== "progress" &&
      parsed.kind !== "verify" &&
      parsed.kind !== "submit" &&
      parsed.kind !== "test_extraction" &&
      parsed.kind !== "give_up"
    ) {
      return null;
    }
    return {
      kind: parsed.kind,
      stage: isAgenticRecipeStage(parsed.stage) ? parsed.stage : undefined,
      changed: parsed.changed,
      message:
        parsed.kind === "verify"
          ? formatVerifyLogMessage({
              matchCount: parsed.matchCount,
              url: typeof parsed.url === "string" ? parsed.url : undefined,
              linkRegexp:
                typeof parsed.linkRegexp === "string"
                  ? parsed.linkRegexp
                  : undefined,
            })
          : parsed.message,
      matchCount: parsed.matchCount,
      extracted: parsed.extracted,
      url: typeof parsed.url === "string" ? parsed.url : undefined,
      entryCount: parsed.entryCount,
    };
  } catch {
    return null;
  }
}

export function formatAgentEventForPublicLog(
  event: AgentEvent
): FormattedAgentLog | null {
  if (event.type === "status") {
    return { kind: "status", message: event.message };
  }
  if (event.type === "toolCall") {
    return { kind: "tool", message: event.message };
  }
  if (event.type === "assistant") {
    const trimmed = event.message.trim();
    if (!trimmed) {
      return null;
    }
    return { kind: "plain", message: trimmed };
  }
  if (event.type === "tool" && !event.isError) {
    const parsed = parseXtraToolResult(event.message);
    if (!parsed) {
      return null;
    }
    if (parsed.kind === "stage") {
      if (!parsed.stage || parsed.changed === false) {
        return null;
      }
      return { kind: "stage", stage: parsed.stage };
    }
    if (
      (parsed.kind === "progress" || parsed.kind === "verify") &&
      parsed.message
    ) {
      return { kind: "plain", message: parsed.message };
    }
    if (parsed.kind === "submit" && parsed.message) {
      return { kind: "plain", message: parsed.message };
    }
    if (parsed.kind === "test_extraction") {
      return {
        kind: "plain",
        message: formatTestExtractionLogMessage({
          extracted: parsed.extracted === true,
          url: parsed.url,
          entryCount: parsed.entryCount,
        }),
      };
    }
    if (parsed.kind === "give_up" && parsed.message) {
      return { kind: "status", message: parsed.message };
    }
  }
  return null;
}

function formatTestExtractionLogMessage(input: {
  extracted: boolean;
  url?: string;
  entryCount?: number;
}): string {
  const page = input.url ? `[page](${input.url})` : "page";
  return input.extracted
    ? `Test extraction on the ${page} generated ${input.entryCount} entry(s).`
    : `Test extraction on the ${page} generated no entries.`;
}

function formatVerifyLogMessage(input: {
  matchCount?: number;
  url?: string;
  linkRegexp?: string;
}): string {
  const count = input.matchCount ?? 0;
  const links = `matching link${count === 1 ? "" : "s"}`;
  const regexp = input.linkRegexp ?? "";
  const page = input.url ? `[this page](${input.url})` : "this page";
  return `Verification found ${count} ${links} by using Regex (${regexp}) on ${page}`;
}

export function statusLog(message: string): string {
  return `<status>${message}</status>`;
}

export function toolLog(message: string): string {
  return `<tool>${message}</tool>`;
}

export function stageLog(stage: AgenticRecipeStage): string {
  return agenticRecipeStageLog(stage);
}
