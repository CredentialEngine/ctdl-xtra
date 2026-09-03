import { describe, expect, it } from "vitest";
import { AgenticRecipeStage } from "../../common/types";
import { applyStageReport } from "../src/agentic/recipeStages";

describe("applyStageReport", () => {
  it("requires ASSESS_USABILITY first", () => {
    const result = applyStageReport(
      null,
      AgenticRecipeStage.MAP_STRUCTURE
    );
    expect(result).toEqual({
      ok: false,
      error: `Incorrect stage. Report ${AgenticRecipeStage.ASSESS_USABILITY} first.`,
    });
  });

  it("rejects unknown stage values", () => {
    const result = applyStageReport(null, 1);
    expect(result.ok).toBe(false);
    if (!result.ok) {
      expect(result.error).toContain("Incorrect stage");
      expect(result.error).toContain(AgenticRecipeStage.ASSESS_USABILITY);
    }
  });

  it("accepts the first stage and sequential advances", () => {
    const first = applyStageReport(null, AgenticRecipeStage.ASSESS_USABILITY);
    expect(first).toEqual({
      ok: true,
      stage: AgenticRecipeStage.ASSESS_USABILITY,
      changed: true,
    });
    const second = applyStageReport(
      AgenticRecipeStage.ASSESS_USABILITY,
      AgenticRecipeStage.MAP_STRUCTURE
    );
    expect(second).toEqual({
      ok: true,
      stage: AgenticRecipeStage.MAP_STRUCTURE,
      changed: true,
    });
  });

  it("rejects skipped stages", () => {
    const result = applyStageReport(
      AgenticRecipeStage.ASSESS_USABILITY,
      AgenticRecipeStage.WRITE_CONFIGURATION
    );
    expect(result.ok).toBe(false);
    if (!result.ok) {
      expect(result.error).toContain("Incorrect stage");
      expect(result.error).toContain(AgenticRecipeStage.MAP_STRUCTURE);
    }
  });

  it("allows going back from VERIFY_RECIPE to WRITE_CONFIGURATION", () => {
    expect(
      applyStageReport(
        AgenticRecipeStage.VERIFY_RECIPE,
        AgenticRecipeStage.WRITE_CONFIGURATION
      )
    ).toEqual({
      ok: true,
      stage: AgenticRecipeStage.WRITE_CONFIGURATION,
      changed: true,
    });
  });

  it("treats re-entering the current stage as unchanged", () => {
    expect(
      applyStageReport(
        AgenticRecipeStage.MAP_STRUCTURE,
        AgenticRecipeStage.MAP_STRUCTURE
      )
    ).toEqual({
      ok: true,
      stage: AgenticRecipeStage.MAP_STRUCTURE,
      changed: false,
    });
  });
});
