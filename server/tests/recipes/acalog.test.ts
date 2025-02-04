import { PageType } from "@common/types";
import { describe, test } from "vitest";
import { assertConfiguration, RECIPE_TIMEOUT } from "..";

describe(
  "ACALOG",
  {
    timeout: RECIPE_TIMEOUT,
  },
  () => {
    test("Ivy Tech Community College - Recipe Configuration", async () => {
      await assertConfiguration(
        "https://catalog.ivytech.edu/content.php?catoid=7&navoid=771",
        {
          links: {
            pageType: PageType.COURSE_DETAIL_PAGE,
          },
          pageType: PageType.COURSE_LINKS_PAGE,
          sampleLinks: [
            "preview_course_nopop.php?catoid=7&coid=123",
            "preview_course_nopop.php?catoid=7&coid=456",
            "preview_course_nopop.php?catoid=7&coid=789",
          ],
          pagination: {
            totalPages: 24,
            urlPattern:
              "https://catalog.ivytech.edu/content.php?catoid=7&navoid=771&filter[cpage]={page_num}",
            urlPatternType: "page_num",
          },
        }
      );
    });

    test("Syracuse University - Recipe Configuration", async () => {
      await assertConfiguration(
        "http://coursecatalog.syr.edu/content.php?catoid=35&navoid=4525",
        {
          pageType: PageType.COURSE_LINKS_PAGE,
          links: {
            pageType: PageType.COURSE_DETAIL_PAGE,
          },
          linkRegexp: "preview_course_nopop.php\\?catoid=\\d+&coid=\\d+",
          sampleLinks: [
            "preview_course_nopop.php?catoid=35&coid=123",
            "preview_course_nopop.php?catoid=35&coid=456",
            "preview_course_nopop.php?catoid=35&coid=789",
          ],
          pagination: {
            urlPatternType: "page_num",
            totalPages: 55,
            urlPattern:
              "http://coursecatalog.syr.edu/content.php?catoid=35&navoid=4525&filter%5Bcpage%5D={page_num}",
          },
        }
      );
    });

    test("University of Pittsburgh - Recipe Configuration", async () => {
      await assertConfiguration(
        "https://catalog.upp.pitt.edu/content.php?catoid=225&navoid=23279",
        {
          pageType: PageType.COURSE_LINKS_PAGE,
          links: {
            pageType: PageType.COURSE_DETAIL_PAGE,
          },
          linkRegexp: "preview_course.php\\?catoid=225&coid=\\d+",
          sampleLinks: [
            "preview_course.php?catoid=225&coid=123",
            "preview_course.php?catoid=225&coid=456",
            "preview_course.php?catoid=225&coid=789",
          ],
          pagination: {
            urlPatternType: "page_num",
            totalPages: 61,
            urlPattern:
              "https://catalog.upp.pitt.edu/content.php?catoid=225&navoid=23279&filter%5Bcpage%5D={page_num}",
          },
        }
      );
    });
  }
);
