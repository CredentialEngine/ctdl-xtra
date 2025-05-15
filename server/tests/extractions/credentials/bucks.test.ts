import { test, expect, describe } from "vitest";
import { extractCredentials, EXTRACTION_TIMEOUT } from "../../index";

describe("Bucks County Community College", { timeout: EXTRACTION_TIMEOUT }, () => {
  test(
    "Computer Science",
    async () => {
      const url = "https://www.bucks.edu/academics/courses/majors/";
      const credentials = await extractCredentials(url);

      expect(credentials).toEqual([
        {
          credential_name: expect.like("Computer Science"),
          credential_description: expect.like(
            "Associate degree program providing foundation in computer programming, algorithms, data structures, and software development"
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
      const url = "https://www.bucks.edu/academics/courses/majors/";
      const credentials = await extractCredentials(url);

      expect(credentials).toEqual([
        {
          credential_name: expect.like("Business Administration"),
          credential_description: expect.like(
            "Associate degree program covering business fundamentals including management, finance, marketing, and entrepreneurship"
          ),
          credential_type: "AssociateDegree",
          language: "English",
        },
      ]);
    }
  );
}); 