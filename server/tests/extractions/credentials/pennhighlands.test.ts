import { test, expect, describe } from "vitest";
import { extractCredentials, EXTRACTION_TIMEOUT } from "../../index";

describe("Pennsylvania Highlands Community College", { timeout: EXTRACTION_TIMEOUT }, () => {
  test(
    "Business Management Associate Degree",
    async () => {
      const url = "https://www.pennhighlands.edu/academics/business-communication/business-management/";
      const credentials = await extractCredentials(url);

      expect(credentials).toEqual([
        {
          credential_name: expect.like("Business Management"),
          credential_description: expect.like(
            "Associate in Applied Science degree program designed to prepare students for management roles in various business sectors"
          ),
          credential_type: "AssociateDegree",
          language: "English",
        },
      ]);
    }
  );

  test(
    "Computer Science",
    async () => {
      const url = "https://www.pennhighlands.edu/academics/computer-information-sciences/computer-science/";
      const credentials = await extractCredentials(url);

      expect(credentials).toEqual([
        {
          credential_name: expect.like("Computer Science"),
          credential_description: expect.like(
            "Associate in Science degree program that provides foundation in computer programming, systems analysis, and software development"
          ),
          credential_type: "AssociateDegree",
          language: "English",
        },
      ]);
    }
  );

  test(
    "Accounting",
    async () => {
      const url = "https://www.pennhighlands.edu/academics/business-communication/accounting/";
      const credentials = await extractCredentials(url);

      expect(credentials).toEqual([
        {
          credential_name: expect.like("Accounting"),
          credential_description: expect.like(
            "Associate in Applied Science degree program that prepares students for careers in accounting, bookkeeping, and financial management"
          ),
          credential_type: "AssociateDegree",
          language: "English",
        },
      ]);
    }
  );

  test(
    "Business Management Certificate",
    async () => {
      const url = "https://www.pennhighlands.edu/academics/business-communication/business-management-certificate/";
      const credentials = await extractCredentials(url);

      expect(credentials).toEqual([
        {
          credential_name: expect.like("Business Management"),
          credential_description: expect.like(
            "Certificate program providing practical business management skills and knowledge for immediate workforce entry"
          ),
          credential_type: "Certificate",
          language: "English",
        },
      ]);
    }
  );

  test(
    "Behavioral Sciences",
    async () => {
      const url = "https://www.pennhighlands.edu/academics/social-sciences-criminal-justice/behavioral-sciences/";
      const credentials = await extractCredentials(url);

      expect(credentials).toEqual([
        {
          credential_name: expect.like("Behavioral Sciences"),
          credential_description: expect.like(
            "Associate in Arts degree program that explores human behavior, psychology, and social sciences with transfer opportunities"
          ),
          credential_type: "AssociateDegree",
          language: "English",
        },
      ]);
    }
  );

  test(
    "Bookkeeping Certificate",
    async () => {
      const url = "https://www.pennhighlands.edu/academics/business-communication/bookkeeping/";
      const credentials = await extractCredentials(url);

      expect(credentials).toEqual([
        {
          credential_name: expect.like("Bookkeeping"),
          credential_description: expect.like(
            "Certificate program focused on essential bookkeeping skills, financial record keeping, and accounting fundamentals"
          ),
          credential_type: "Certificate",
          language: "English",
        },
      ]);
    }
  );
}); 