import { test, expect, describe } from "vitest";
import { extractCredentials, EXTRACTION_TIMEOUT } from "../../index";

describe("Northampton Community College", { timeout: EXTRACTION_TIMEOUT }, () => {
  test(
    "Computer Information Technology",
    async () => {
      const url = "https://www.northampton.edu/education-and-training/programs/";
      const credentials = await extractCredentials(url);

      expect(credentials).toEqual([
        {
          credential_name: expect.like("Computer Information Technology"),
          credential_description: expect.like(
            "Associate degree program that provides comprehensive training in computer systems, networking, and information technology support"
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
      const url = "https://www.northampton.edu/education-and-training/programs/";
      const credentials = await extractCredentials(url);

      expect(credentials).toEqual([
        {
          credential_name: expect.like("Cybersecurity"),
          credential_description: expect.like(
            "Associate degree program focusing on information security, network protection, and cybersecurity best practices"
          ),
          credential_type: "AssociateDegree",
          language: "English",
        },
      ]);
    }
  );
}); 