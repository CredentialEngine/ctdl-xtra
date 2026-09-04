import { describe, expect, it } from "vitest";
import {
  AgenticRecipeStage,
  PageType,
  type RecipeConfiguration,
} from "../../common/types";
import {
  countNonDetailLevels,
  shouldResetVerificationState,
  validateSubmitAllowed,
} from "../src/agentic/recipeSubmitGates";

const detailOnlyConfig: RecipeConfiguration = {
  pageType: PageType.DETAIL,
};

const twoLevelConfig: RecipeConfiguration = {
  pageType: PageType.DETAIL_LINKS,
  linkRegexp: "/courses/",
  links: {
    pageType: PageType.DETAIL,
  },
};

describe("countNonDetailLevels", () => {
  it("returns 0 for a DETAIL-only configuration", () => {
    expect(countNonDetailLevels(detailOnlyConfig)).toBe(0);
  });

  it("counts each non-DETAIL level", () => {
    expect(countNonDetailLevels(twoLevelConfig)).toBe(1);
  });
});

describe("shouldResetVerificationState", () => {
  it("resets when moving back before VERIFY_RECIPE", () => {
    expect(
      shouldResetVerificationState(
        AgenticRecipeStage.WRITE_CONFIGURATION,
        true
      )
    ).toBe(true);
  });

  it("does not reset when re-entering the same stage", () => {
    expect(
      shouldResetVerificationState(AgenticRecipeStage.VERIFY_RECIPE, false)
    ).toBe(false);
  });

  it("does not reset when entering VERIFY_RECIPE", () => {
    expect(
      shouldResetVerificationState(AgenticRecipeStage.VERIFY_RECIPE, true)
    ).toBe(false);
  });
});

describe("validateSubmitAllowed", () => {
  it("rejects submit before VERIFY_RECIPE", () => {
    const result = validateSubmitAllowed(twoLevelConfig, {
      currentStage: AgenticRecipeStage.WRITE_CONFIGURATION,
      verifyLinkCallsSuccessful: 1,
      testExtractionSucceeded: true,
    });
    expect(result.ok).toBe(false);
    if (!result.ok) {
      expect(result.error).toContain(AgenticRecipeStage.VERIFY_RECIPE);
    }
  });

  it("requires link verification for each non-DETAIL level", () => {
    const result = validateSubmitAllowed(twoLevelConfig, {
      currentStage: AgenticRecipeStage.VERIFY_RECIPE,
      verifyLinkCallsSuccessful: 0,
      testExtractionSucceeded: true,
    });
    expect(result.ok).toBe(false);
    if (!result.ok) {
      expect(result.error).toContain("non-DETAIL");
    }
  });

  it("requires successful test extraction", () => {
    const result = validateSubmitAllowed(detailOnlyConfig, {
      currentStage: AgenticRecipeStage.VERIFY_RECIPE,
      verifyLinkCallsSuccessful: 0,
      testExtractionSucceeded: false,
    });
    expect(result.ok).toBe(false);
    if (!result.ok) {
      expect(result.error).toContain("xtra_test_extraction");
    }
  });

  it("allows submit when verification is complete", () => {
    expect(
      validateSubmitAllowed(twoLevelConfig, {
        currentStage: AgenticRecipeStage.VERIFY_RECIPE,
        verifyLinkCallsSuccessful: 1,
        testExtractionSucceeded: true,
      })
    ).toEqual({ ok: true });

    expect(
      validateSubmitAllowed(detailOnlyConfig, {
        currentStage: AgenticRecipeStage.VERIFY_RECIPE,
        verifyLinkCallsSuccessful: 0,
        testExtractionSucceeded: true,
      })
    ).toEqual({ ok: true });
  });
});
