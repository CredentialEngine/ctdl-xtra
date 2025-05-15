import { test, expect, describe } from "vitest";
import { extractCredentials, EXTRACTION_TIMEOUT } from "../../index";

describe("Lehigh Carbon Community College", { timeout: EXTRACTION_TIMEOUT }, () => {
  test(
    "Computer Information Systems",
    async () => {
      const url = "https://www.lccc.edu/academics/programs/";
      const credentials = await extractCredentials(url);

      expect(credentials).toEqual([
        {
          credential_name: expect.like("Computer Information Systems"),
          credential_description: expect.like(
            "Associate degree program that combines computer technology with business applications and information management"
          ),
          credential_type: "AssociateDegree",
          language: "English",
        },
      ]);
    }
  );

  test(
    "Cybersecurity",
    async () => {
      const url = "https://www.lccc.edu/academics/programs/";
      const credentials = await extractCredentials(url);

      expect(credentials).toEqual([
        {
          credential_name: expect.like("Cybersecurity"),
          credential_description: expect.like(
            "Associate degree program focused on network security, information protection, and cyber defense strategies"
          ),
          credential_type: "AssociateDegree",
          language: "English",
        },
      ]);
    }
  );
}); 