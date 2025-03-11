import { describe, test } from "vitest";
import { RECIPE_TIMEOUT, assertConfiguration } from "..";
import { PageType } from "../../../common/types";

describe("Kuali", { timeout: RECIPE_TIMEOUT }, () => {
  test("BYU-Idaho", async () => {
    await assertConfiguration("https://www.byui.edu/catalog/#/courses", {
      pageType: PageType.CATEGORY_LINKS,
      linkRegexp:
        "https:\\/\\/www\\.byui\\.edu\\/catalog\\/#\\/courses\\?group=[A-Za-z%20]+",
      pagination: undefined,
      sampleLinks: [
        "https://www.byui.edu/catalog/#/courses?group=Accounting",
        "https://www.byui.edu/catalog/#/courses?group=Welding",
      ],
      links: {
        pageType: PageType.DETAIL_LINKS,
        linkRegexp:
          "#\\/courses\\/[\\w-]+\\?group=[\\w%20]+&bc=true&bcCurrent=[\\w%20-]+&bcGroup=[\\w%20]+&bcItemType=courses",
        pagination: undefined,
        sampleLinks: [
          "#/courses/414Six2j-?group=Accounting&bc=true&bcCurrent=ACCTG100%20-%20Introduction%20to%20Accounting&bcGroup=Accounting&bcItemType=courses",
          "#/courses/NkSTgWhjW?bc=true&bcCurrent=WELD100%20-%20Introduction%20to%20Welding&bcGroup=Welding&bcItemType=courses",
        ],
        links: {
          pageType: PageType.DETAIL,
          linkRegexp: undefined,
          pagination: undefined,
        },
      },
    });
  });
});
