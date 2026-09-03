import type { AgentEvent } from "./types";

export interface ParsedXtraEvent {
  kind: "stage" | "progress" | "verify" | "submit" | "test_extraction";
  stage?: number;
  message?: string;
  matchCount?: number;
  extracted?: boolean;
}

export function parseXtraToolResult(message: string): ParsedXtraEvent | null {
  const trimmed = message.trim();
  if (!trimmed.startsWith("{")) {
    return null;
  }
  try {
    const parsed = JSON.parse(trimmed) as {
      xtraEvent?: boolean;
      kind?: string;
      stage?: number;
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
      stage: parsed.stage,
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
): { message: string; isStatus: boolean } | null {
  if (event.type === "status") {
    return { message: event.message, isStatus: true };
  }
  if (event.type === "assistant") {
    const trimmed = event.message.trim();
    if (!trimmed) {
      return null;
    }
    return { message: trimmed, isStatus: false };
  }
  if (event.type === "tool" && !event.isError) {
    const parsed = parseXtraToolResult(event.message);
    if (!parsed) {
      return null;
    }
    if (parsed.kind === "stage" && parsed.message) {
      return { message: parsed.message, isStatus: true };
    }
    if (parsed.kind === "progress" && parsed.message) {
      return { message: parsed.message, isStatus: false };
    }
    if (parsed.kind === "verify") {
      const count = parsed.matchCount ?? 0;
      return {
        message: `Verification found ${count} matching link${count === 1 ? "" : "s"}.`,
        isStatus: false,
      };
    }
    if (parsed.kind === "submit" && parsed.message) {
      return { message: parsed.message, isStatus: false };
    }
    if (parsed.kind === "test_extraction") {
      return {
        message:
          parsed.extracted === true
            ? "Test extraction generated entries."
            : "Test extraction generated no entries.",
        isStatus: false,
      };
    }
  }
  return null;
}

export function statusLog(message: string): string {
  return `<status>${message}</status>`;
}
