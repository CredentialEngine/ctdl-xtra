import {
  AgenticRecipeStage,
  AGENTIC_RECIPE_STAGES,
  isAgenticRecipeStage,
} from "../../../common/types";

export type StageReportResult =
  | { ok: true; stage: AgenticRecipeStage; changed: boolean }
  | { ok: false; error: string };

function validStagesList(): string {
  return AGENTIC_RECIPE_STAGES.join(", ");
}

export function applyStageReport(
  current: AgenticRecipeStage | null,
  reported: unknown
): StageReportResult {
  if (!isAgenticRecipeStage(reported)) {
    if (current) {
      return {
        ok: false,
        error: `Incorrect stage. Valid stages: ${validStagesList()}. Current stage is ${current}.`,
      };
    }
    return {
      ok: false,
      error: `Incorrect stage. Valid stages: ${validStagesList()}. Report ${AgenticRecipeStage.ASSESS_USABILITY} first.`,
    };
  }

  if (current === null) {
    if (reported !== AgenticRecipeStage.ASSESS_USABILITY) {
      return {
        ok: false,
        error: `Incorrect stage. Report ${AgenticRecipeStage.ASSESS_USABILITY} first.`,
      };
    }
    return { ok: true, stage: reported, changed: true };
  }

  if (reported === current) {
    return { ok: true, stage: reported, changed: false };
  }

  const currentIndex = AGENTIC_RECIPE_STAGES.indexOf(current);
  const reportedIndex = AGENTIC_RECIPE_STAGES.indexOf(reported);
  const isAdvance = reportedIndex === currentIndex + 1;
  const isBack = reportedIndex < currentIndex;
  if (!isAdvance && !isBack) {
    const next = AGENTIC_RECIPE_STAGES[currentIndex + 1];
    const expected = next
      ? `${current}, the next stage ${next}, or a previous stage`
      : `${current} or a previous stage`;
    return {
      ok: false,
      error: `Incorrect stage. Current stage is ${current}. Report ${expected}.`,
    };
  }

  return { ok: true, stage: reported, changed: true };
}
