import { test, expect, describe } from "vitest";
import { extractCredentials, EXTRACTION_TIMEOUT } from "../../index";

describe("Delaware County Community College", { timeout: EXTRACTION_TIMEOUT }, () => {
  test(
    "Cybersecurity",
    async () => {
      const url = "https://www.dccc.edu/academics/program-search/";
      const credentials = await extractCredentials(url);

      expect(credentials).toEqual([
        {
          credential_name: expect.like("Cybersecurity"),
          credential_description: expect.like(
            "Associate degree program designed to prepare students for careers in information security, network defense, and cybersecurity analysis"
          ),
          credential_type: "AssociateDegree",
          language: "English",
        },
      ]);
    }
  );

  test(
    "Computer Information Systems",
    async () => {
      const url = "https://www.dccc.edu/academics/program-search/";
      const credentials = await extractCredentials(url);

      expect(credentials).toEqual([
        {
          credential_name: expect.like("Computer Information Systems"),
          credential_description: expect.like(
            "Associate degree program combining computer technology skills with business knowledge for technology management roles"
          ),
          credential_type: "AssociateDegree",
          language: "English",
        },
      ]);
    }
  );
}); 