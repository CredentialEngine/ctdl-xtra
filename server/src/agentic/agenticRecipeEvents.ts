import {
  AgenticRecipeStage,
  isAgenticRecipeStage,
} from "../../../common/types";
import { agenticRecipeStageLog } from "../../../common/recipe";
import type { AgentEvent } from "./types";

export interface ParsedXtraEvent {
  kind: "stage" | "progress" | "verify" | "submit" | "test_extraction";
  stage?: AgenticRecipeStage;
  changed?: boolean;
  message?: string;
  matchCount?: number;
  extracted?: boolean;
}

export type FormattedAgentLog =
  | { kind: "status"; message: string }
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
    };
    if (!parsed.xtraEvent || !parsed.kind) {
      return null;
    }
    if (
      parsed.kind !== "stage" &&
      parsed.kind !== "progress" &&
      parsed.kind !== "verify" &&
      parsed.kind !== "submit" &&
      parsed.kind !== "test_extraction"
    ) {
      return null;
    }
    return {
      kind: parsed.kind,
      stage: isAgenticRecipeStage(parsed.stage) ? parsed.stage : undefined,
      changed: parsed.changed,
      message: parsed.message,
      matchCount: parsed.matchCount,
      extracted: parsed.extracted,
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
    if (parsed.kind === "progress" && parsed.message) {
      return { kind: "plain", message: parsed.message };
    }
    if (parsed.kind === "verify") {
      const count = parsed.matchCount ?? 0;
      return {
        kind: "plain",
        message: `Verification found ${count} matching link${count === 1 ? "" : "s"}.`,
      };
    }
    if (parsed.kind === "submit" && parsed.message) {
      return { kind: "plain", message: parsed.message };
    }
    if (parsed.kind === "test_extraction") {
      return {
        kind: "plain",
        message:
          parsed.extracted === true
            ? "Test extraction generated entries."
            : "Test extraction generated no entries.",
      };
    }
  }
  return null;
}

export function statusLog(message: string): string {
  return `<status>${message}</status>`;
}

export function stageLog(stage: AgenticRecipeStage): string {
  return agenticRecipeStageLog(stage);
}
