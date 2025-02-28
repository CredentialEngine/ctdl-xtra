import { PageType } from "@common/types";
import { describe, test } from "vitest";
import { assertConfiguration, RECIPE_TIMEOUT } from "..";

describe("Courseleaf", { timeout: RECIPE_TIMEOUT }, () => {
  test("University of Pennsylvania", async () => {
    await assertConfiguration("https://catalog.upenn.edu/courses/", {
      links: {
        pageType: PageType.DETAIL,
      },
      pageType: PageType.CATEGORY_LINKS,
      sampleLinks: ["/courses/acct/", "/courses/hist/", "/courses/punj/"],
    });
  });

  test("Texas A&M International University", async () => {
    await assertConfiguration(
      "https://catalog.tamiu.edu/course-descriptions/",
      {
        links: {
          pageType: PageType.DETAIL,
        },
        pageType: PageType.CATEGORY_LINKS,
        sampleLinks: [
          "/course-descriptions/port/",
          "/course-descriptions/ms/",
          "/course-descriptions/sost/",
        ],
      }
    );
  });
});
