import { describe, expect, it } from "vitest";
import { AgenticRecipeStage } from "../../common/types";
import {
  applyStageReport,
  MAX_STAGE_CHANGES,
  STAGE_CHANGE_LIMIT_MESSAGE,
} from "../src/agentic/recipeStages";

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

  it("rejects a stage change after the max number of changes", () => {
    expect(
      applyStageReport(
        null,
        AgenticRecipeStage.ASSESS_USABILITY,
        MAX_STAGE_CHANGES
      )
    ).toEqual({
      ok: false,
      error: STAGE_CHANGE_LIMIT_MESSAGE,
    });
  });

  it("still allows re-reporting the current stage at the max", () => {
    expect(
      applyStageReport(
        AgenticRecipeStage.WRITE_CONFIGURATION,
        AgenticRecipeStage.WRITE_CONFIGURATION,
        MAX_STAGE_CHANGES
      )
    ).toEqual({
      ok: true,
      stage: AgenticRecipeStage.WRITE_CONFIGURATION,
      changed: false,
    });
  });

  it("stops looping between WRITE_CONFIGURATION and VERIFY_RECIPE at 20 changes", () => {
    let current: AgenticRecipeStage | null = null;
    let count = 0;
    const path = [
      AgenticRecipeStage.ASSESS_USABILITY,
      AgenticRecipeStage.MAP_STRUCTURE,
      AgenticRecipeStage.WRITE_CONFIGURATION,
      AgenticRecipeStage.VERIFY_RECIPE,
    ];
    for (const stage of path) {
      const result = applyStageReport(current, stage, count);
      expect(result.ok).toBe(true);
      if (result.ok && result.changed) {
        current = result.stage;
        count++;
      }
    }
    while (count < MAX_STAGE_CHANGES) {
      const next =
        current === AgenticRecipeStage.VERIFY_RECIPE
          ? AgenticRecipeStage.WRITE_CONFIGURATION
          : AgenticRecipeStage.VERIFY_RECIPE;
      const result = applyStageReport(current, next, count);
      expect(result.ok).toBe(true);
      if (result.ok && result.changed) {
        current = result.stage;
        count++;
      }
    }
    expect(count).toBe(MAX_STAGE_CHANGES);
    const blocked = applyStageReport(
      current,
      current === AgenticRecipeStage.VERIFY_RECIPE
        ? AgenticRecipeStage.WRITE_CONFIGURATION
        : AgenticRecipeStage.VERIFY_RECIPE,
      count
    );
    expect(blocked).toEqual({
      ok: false,
      error: STAGE_CHANGE_LIMIT_MESSAGE,
    });
  });
});
