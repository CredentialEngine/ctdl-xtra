import {
  AgenticRecipeStage,
  AGENTIC_RECIPE_STAGES,
  PageType,
  type RecipeConfiguration,
} from "../../../common/types";

export interface SubmitVerificationState {
  currentStage: AgenticRecipeStage | null;
  verifyLinkCallsSuccessful: number;
  testExtractionSucceeded: boolean;
}

export function countNonDetailLevels(
  configuration: RecipeConfiguration
): number {
  let count = 0;
  let current: RecipeConfiguration | undefined = configuration;
  while (current && current.pageType !== PageType.DETAIL) {
    count++;
    current = current.links;
  }
  return count;
}

export function shouldResetVerificationState(
  nextStage: AgenticRecipeStage,
  changed: boolean
): boolean {
  if (!changed) {
    return false;
  }
  const verifyIndex = AGENTIC_RECIPE_STAGES.indexOf(
    AgenticRecipeStage.VERIFY_RECIPE
  );
  const nextIndex = AGENTIC_RECIPE_STAGES.indexOf(nextStage);
  return nextIndex < verifyIndex;
}

export function validateSubmitAllowed(
  configuration: RecipeConfiguration,
  state: SubmitVerificationState
): { ok: true } | { ok: false; error: string } {
  if (state.currentStage !== AgenticRecipeStage.VERIFY_RECIPE) {
    return {
      ok: false,
      error: `Cannot submit before ${AgenticRecipeStage.VERIFY_RECIPE}. Report that stage and complete verification first.`,
    };
  }

  const nonDetailLevels = countNonDetailLevels(configuration);
  if (
    nonDetailLevels > 0 &&
    state.verifyLinkCallsSuccessful < nonDetailLevels
  ) {
    return {
      ok: false,
      error: `Complete link verification for all ${nonDetailLevels} non-DETAIL level(s) before submitting (${state.verifyLinkCallsSuccessful} completed).`,
    };
  }

  if (!state.testExtractionSucceeded) {
    return {
      ok: false,
      error:
        "Call xtra_test_extraction on at least one DETAIL page with successful extraction before submitting.",
    };
  }

  return { ok: true };
}
