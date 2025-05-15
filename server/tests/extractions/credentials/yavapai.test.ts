import { test, expect, describe } from "vitest";
import { extractCredentials, EXTRACTION_TIMEOUT } from "../../index";

describe("Yavapai College", { timeout: EXTRACTION_TIMEOUT }, () => {
  test(
    "Computer Information Systems",
    async () => {
      const url = "https://catalog.yc.edu/content.php?catoid=28&navoid=8632";
      const credentials = await extractCredentials(url);

      expect(credentials).toEqual([
        {
          credential_name: expect.like("Computer Information Systems"),
          credential_description: expect.like(
            "Associate of Applied Science degree program that provides students with fundamental knowledge in computer systems, networking, and information technology"
          ),
          credential_type: "AssociateDegree",
          language: "English",
        },
      ]);
    }
  );

  test(
    "Business Administration",
    async () => {
      const url = "https://catalog.yc.edu/content.php?catoid=28&navoid=8632";
      const credentials = await extractCredentials(url);

      expect(credentials).toEqual([
        {
          credential_name: expect.like("Business Administration"),
          credential_description: expect.like(
            "Associate degree program that covers fundamental business principles including management, marketing, accounting, and business communications"
          ),
          credential_type: "AssociateDegree",
          language: "English",
        },
      ]);
    }
  );
}); 