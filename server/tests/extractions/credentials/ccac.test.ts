import { test, expect, describe } from "vitest";
import { extractCredentials, EXTRACTION_TIMEOUT } from "../../index";

describe("Community College of Allegheny County", { timeout: EXTRACTION_TIMEOUT }, () => {
  test(
    "Cybersecurity",
    async () => {
      const url = "https://catalog.ccac.edu/content.php?catoid=14&navoid=4655";
      const credentials = await extractCredentials(url);

      expect(credentials).toEqual([
        {
          credential_name: expect.like("Cybersecurity"),
          credential_description: expect.like(
            "Associate degree program focusing on information security, network defense, and cybersecurity fundamentals to prepare students for careers in information security"
          ),
          credential_type: "AssociateDegree",
          language: "English",
        },
      ]);
    }
  );

  test(
    "Computer Programming",
    async () => {
      const url = "https://catalog.ccac.edu/content.php?catoid=14&navoid=4655";
      const credentials = await extractCredentials(url);

      expect(credentials).toEqual([
        {
          credential_name: expect.like("Computer Programming"),
          credential_description: expect.like(
            "Certificate or degree program that teaches software development, programming languages, and application development skills"
          ),
          credential_type: "Certificate",
          language: "English",
        },
      ]);
    }
  );
}); 