import { test, expect, describe } from "vitest";
import { extractCredentials, EXTRACTION_TIMEOUT } from "../../index";

describe("Butler County Community College", { timeout: EXTRACTION_TIMEOUT }, () => {
  test(
    "Information Technology",
    async () => {
      const url = "https://www.bc3.edu/programs-classes/degrees-certificates/index.html";
      const credentials = await extractCredentials(url);

      expect(credentials).toEqual([
        {
          credential_name: expect.like("Information Technology"),
          credential_description: expect.like(
            "Associate degree program that prepares students for careers in information technology, systems administration, and technical support"
          ),
          credential_type: "AssociateDegree",
          language: "English",
        },
      ]);
    }
  );

  test(
    "Computer Programming Certificate",
    async () => {
      const url = "https://www.bc3.edu/programs-classes/degrees-certificates/index.html";
      const credentials = await extractCredentials(url);

      expect(credentials).toEqual([
        {
          credential_name: expect.like("Computer Programming"),
          credential_description: expect.like(
            "Certificate program focusing on programming languages, software development, and application design"
          ),
          credential_type: "Certificate",
          language: "English",
        },
      ]);
    }
  );
}); 