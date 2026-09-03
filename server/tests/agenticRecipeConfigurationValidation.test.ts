import { describe, expect, it } from "vitest";
import {
  assertRecipeConfigurationHasDetailLeaf,
  parseAgentRecipeConfiguration,
} from "../src/agentic/recipeConfigurationValidation";
import { PageType } from "../../common/types";

describe("parseAgentRecipeConfiguration", () => {
  it("accepts a nested recipe configuration", () => {
    const configuration = parseAgentRecipeConfiguration({
      pageType: PageType.DETAIL_LINKS,
      linkRegexp: "course\\/\\w+",
      links: {
        pageType: PageType.DETAIL,
      },
    });
    expect(configuration.pageType).toBe(PageType.DETAIL_LINKS);
    expect(configuration.links?.pageType).toBe(PageType.DETAIL);
  });

  it("rejects configurations without a DETAIL leaf", () => {
    expect(() =>
      assertRecipeConfigurationHasDetailLeaf({
        pageType: PageType.DETAIL_LINKS,
        linkRegexp: "course\\/\\w+",
        links: {
          pageType: PageType.CATEGORY_LINKS,
          linkRegexp: "dept\\/\\w+",
        },
      })
    ).toThrow(/DETAIL level/);
  });
});
