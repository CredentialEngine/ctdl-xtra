import { describe, expect, it } from "vitest";
import {
  formatAgentEventForPublicLog,
  parseXtraToolResult,
  statusLog,
} from "../src/agentic/agenticRecipeEvents";

describe("parseXtraToolResult", () => {
  it("parses stage events", () => {
    const payload = JSON.stringify({
      xtraEvent: true,
      kind: "stage",
      stage: 2,
      message: "Stage 2: Map catalogue structure",
    });
    expect(parseXtraToolResult(payload)).toEqual({
      kind: "stage",
      stage: 2,
      message: "Stage 2: Map catalogue structure",
    });
  });

  it("returns null for non-xtra payloads", () => {
    expect(parseXtraToolResult("Clicked: body")).toBeNull();
  });
});

describe("formatAgentEventForPublicLog", () => {
  it("marks status events as status logs", () => {
    expect(
      formatAgentEventForPublicLog({
        type: "status",
        message: "Starting browser agent",
      })
    ).toEqual({
      message: "Starting browser agent",
      isStatus: true,
    });
  });

  it("marks assistant text as non-status logs", () => {
    expect(
      formatAgentEventForPublicLog({
        type: "assistant",
        message: "Checking whether links are copyable.",
      })
    ).toEqual({
      message: "Checking whether links are copyable.",
      isStatus: false,
    });
  });

  it("maps xtra stage tool results to status logs", () => {
    const payload = JSON.stringify({
      xtraEvent: true,
      kind: "stage",
      stage: 1,
      message: "Stage 1: Assess catalogue usability",
    });
    expect(
      formatAgentEventForPublicLog({
        type: "tool",
        message: payload,
      })
    ).toEqual({
      message: "Stage 1: Assess catalogue usability",
      isStatus: true,
    });
  });

  it("maps xtra progress tool results to non-status logs", () => {
    const payload = JSON.stringify({
      xtraEvent: true,
      kind: "progress",
      message: "Opening the catalogue index page.",
    });
    expect(
      formatAgentEventForPublicLog({
        type: "tool",
        message: payload,
      })
    ).toEqual({
      message: "Opening the catalogue index page.",
      isStatus: false,
    });
  });
});

describe("statusLog", () => {
  it("wraps messages in status tags", () => {
    expect(statusLog("Running stage 3")).toBe(
      "<status>Running stage 3</status>"
    );
  });
});
