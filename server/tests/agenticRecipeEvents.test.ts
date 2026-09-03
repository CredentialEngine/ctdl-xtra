import { describe, expect, it } from "vitest";
import { AgenticRecipeStage } from "../../common/types";
import { agenticRecipeStageLog } from "../../common/recipe";
import {
  formatAgentEventForPublicLog,
  parseXtraToolResult,
  stageLog,
  statusLog,
} from "../src/agentic/agenticRecipeEvents";

describe("parseXtraToolResult", () => {
  it("parses stage events", () => {
    const payload = JSON.stringify({
      xtraEvent: true,
      kind: "stage",
      stage: AgenticRecipeStage.MAP_STRUCTURE,
      changed: true,
    });
    expect(parseXtraToolResult(payload)).toEqual({
      kind: "stage",
      stage: AgenticRecipeStage.MAP_STRUCTURE,
      changed: true,
      message: undefined,
      matchCount: undefined,
      extracted: undefined,
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
      kind: "status",
      message: "Starting browser agent",
    });
  });

  it("marks assistant text as plain logs", () => {
    expect(
      formatAgentEventForPublicLog({
        type: "assistant",
        message: "Checking whether links are copyable.",
      })
    ).toEqual({
      kind: "plain",
      message: "Checking whether links are copyable.",
    });
  });

  it("maps xtra stage tool results to stage logs when the stage changed", () => {
    const payload = JSON.stringify({
      xtraEvent: true,
      kind: "stage",
      stage: AgenticRecipeStage.ASSESS_USABILITY,
      changed: true,
    });
    expect(
      formatAgentEventForPublicLog({
        type: "tool",
        message: payload,
      })
    ).toEqual({
      kind: "stage",
      stage: AgenticRecipeStage.ASSESS_USABILITY,
    });
  });

  it("omits stage tool results when the stage did not change", () => {
    const payload = JSON.stringify({
      xtraEvent: true,
      kind: "stage",
      stage: AgenticRecipeStage.ASSESS_USABILITY,
      changed: false,
    });
    expect(
      formatAgentEventForPublicLog({
        type: "tool",
        message: payload,
      })
    ).toBeNull();
  });

  it("maps xtra progress tool results to plain logs", () => {
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
      kind: "plain",
      message: "Opening the catalogue index page.",
    });
  });

  it("maps test extraction results to whether entries were generated", () => {
    expect(
      formatAgentEventForPublicLog({
        type: "tool",
        message: JSON.stringify({
          xtraEvent: true,
          kind: "test_extraction",
          extracted: true,
        }),
      })
    ).toEqual({
      kind: "plain",
      message: "Test extraction generated entries.",
    });
    expect(
      formatAgentEventForPublicLog({
        type: "tool",
        message: JSON.stringify({
          xtraEvent: true,
          kind: "test_extraction",
          extracted: false,
        }),
      })
    ).toEqual({
      kind: "plain",
      message: "Test extraction generated no entries.",
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

describe("stageLog", () => {
  it("wraps stage enums in stage tags", () => {
    expect(stageLog(AgenticRecipeStage.VERIFY_RECIPE)).toBe(
      agenticRecipeStageLog(AgenticRecipeStage.VERIFY_RECIPE)
    );
  });
});
