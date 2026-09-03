import { describe, expect, it } from "vitest";
import {
  AGENTIC_RECIPE_STAGE_LABELS,
  agenticRecipeStageLog,
  agenticRecipeStageUiStates,
  latestAgenticRecipeStageFromLogs,
  parseAgenticRecipeStageLog,
} from "../../common/recipe";
import { AgenticRecipeStage } from "../../common/types";

describe("agenticRecipeStageLog", () => {
  it("round-trips stage enums", () => {
    const line = agenticRecipeStageLog(AgenticRecipeStage.MAP_STRUCTURE);
    expect(line).toBe(`<stage>${AgenticRecipeStage.MAP_STRUCTURE}</stage>`);
    expect(parseAgenticRecipeStageLog(line)).toBe(
      AgenticRecipeStage.MAP_STRUCTURE
    );
  });

  it("returns null for non-stage logs", () => {
    expect(parseAgenticRecipeStageLog("<status>Running</status>")).toBeNull();
  });
});

describe("agenticRecipeStageUiStates", () => {
  it("marks all stages pending before the first stage log", () => {
    const states = agenticRecipeStageUiStates(null);
    expect(states[AgenticRecipeStage.ASSESS_USABILITY]).toBe("pending");
    expect(states[AgenticRecipeStage.VERIFY_RECIPE]).toBe("pending");
  });

  it("marks earlier stages done and later stages pending", () => {
    const states = agenticRecipeStageUiStates(
      AgenticRecipeStage.WRITE_CONFIGURATION
    );
    expect(states[AgenticRecipeStage.ASSESS_USABILITY]).toBe("done");
    expect(states[AgenticRecipeStage.MAP_STRUCTURE]).toBe("done");
    expect(states[AgenticRecipeStage.WRITE_CONFIGURATION]).toBe("in_progress");
    expect(states[AgenticRecipeStage.VERIFY_RECIPE]).toBe("pending");
  });

  it("marks every stage done when completed without error", () => {
    const states = agenticRecipeStageUiStates(
      AgenticRecipeStage.MAP_STRUCTURE,
      { completed: true }
    );
    expect(states[AgenticRecipeStage.ASSESS_USABILITY]).toBe("done");
    expect(states[AgenticRecipeStage.MAP_STRUCTURE]).toBe("done");
    expect(states[AgenticRecipeStage.WRITE_CONFIGURATION]).toBe("done");
    expect(states[AgenticRecipeStage.VERIFY_RECIPE]).toBe("done");
  });
});

describe("latestAgenticRecipeStageFromLogs", () => {
  it("uses the most recent stage log", () => {
    expect(
      latestAgenticRecipeStageFromLogs([
        agenticRecipeStageLog(AgenticRecipeStage.ASSESS_USABILITY),
        "<status>Opening the catalogue</status>",
        agenticRecipeStageLog(AgenticRecipeStage.MAP_STRUCTURE),
      ])
    ).toBe(AgenticRecipeStage.MAP_STRUCTURE);
  });
});

describe("AGENTIC_RECIPE_STAGE_LABELS", () => {
  it("has a label for every stage enum", () => {
    expect(AGENTIC_RECIPE_STAGE_LABELS[AgenticRecipeStage.ASSESS_USABILITY]).toBe(
      "Assess catalogue usability"
    );
  });
});
