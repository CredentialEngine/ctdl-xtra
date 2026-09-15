import { describe, expect, it } from "vitest";
import { AgenticRecipeStage } from "../../common/types";
import { agenticRecipeStageLog } from "../../common/recipe";
import {
  formatAgentEventForPublicLog,
  parseXtraToolResult,
  stageLog,
  statusLog,
  toolLog,
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

  it("marks tool call events as tool logs", () => {
    expect(
      formatAgentEventForPublicLog({
        type: "toolCall",
        message: "puppeteer_navigate",
      })
    ).toEqual({
      kind: "tool",
      message: "puppeteer_navigate",
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
          url: "https://catalog.example.edu/programs/nursing",
          entryCount: 3,
        }),
      })
    ).toEqual({
      kind: "plain",
      message:
        "Test extraction on the [page](https://catalog.example.edu/programs/nursing) generated 3 entry(s).",
    });
    expect(
      formatAgentEventForPublicLog({
        type: "tool",
        message: JSON.stringify({
          xtraEvent: true,
          kind: "test_extraction",
          extracted: false,
          url: "https://catalog.example.edu/programs/missing",
        }),
      })
    ).toEqual({
      kind: "plain",
      message:
        "Test extraction on the [page](https://catalog.example.edu/programs/missing) generated no entries.",
    });
  });

  it("maps verify results to a regex and page log", () => {
    expect(
      formatAgentEventForPublicLog({
        type: "tool",
        message: JSON.stringify({
          xtraEvent: true,
          kind: "verify",
          matchCount: 0,
          url: "https://catalog.example.edu/programs",
          linkRegexp: "/programs/[a-z-]+$",
        }),
      })
    ).toEqual({
      kind: "plain",
      message:
        "Verification found 0 matching links by using Regex (/programs/[a-z-]+$) on [this page](https://catalog.example.edu/programs)",
    });
    expect(
      formatAgentEventForPublicLog({
        type: "tool",
        message: JSON.stringify({
          xtraEvent: true,
          kind: "verify",
          matchCount: 1,
          url: "https://catalog.example.edu/courses",
          linkRegexp: "COURSE-\\d+",
        }),
      })
    ).toEqual({
      kind: "plain",
      message:
        "Verification found 1 matching link by using Regex (COURSE-\\d+) on [this page](https://catalog.example.edu/courses)",
    });
  });

  it("maps give_up tool results to status logs", () => {
    expect(
      formatAgentEventForPublicLog({
        type: "tool",
        message: JSON.stringify({
          xtraEvent: true,
          kind: "give_up",
          message: "Site requires login.",
        }),
      })
    ).toEqual({
      kind: "status",
      message: "Site requires login.",
    });
  });
});

describe("toolLog", () => {
  it("wraps messages in tool tags", () => {
    expect(toolLog("puppeteer_navigate")).toBe(
      "<tool>puppeteer_navigate</tool>"
    );
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
