import { test, expect, describe } from "vitest";
import { extractCredentials, EXTRACTION_TIMEOUT } from "../../index";

describe("Montgomery County Community College", { timeout: EXTRACTION_TIMEOUT }, () => {
  test(
    "Computer Information Systems",
    async () => {
      const url = "https://www.mc3.edu/degrees-and-programs";
      const credentials = await extractCredentials(url);

      expect(credentials).toEqual([
        {
          credential_name: expect.like("Computer Information Systems"),
          credential_description: expect.like(
            "Associate degree program integrating computer technology with business processes and information management systems"
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
      const url = "https://www.mc3.edu/degrees-and-programs";
      const credentials = await extractCredentials(url);

      expect(credentials).toEqual([
        {
          credential_name: expect.like("Business Administration"),
          credential_description: expect.like(
            "Associate degree program providing comprehensive foundation in business principles, management, and organizational behavior"
          ),
          credential_type: "AssociateDegree",
          language: "English",
        },
      ]);
    }
  );
}); 