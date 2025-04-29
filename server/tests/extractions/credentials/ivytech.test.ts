import { test, expect, describe } from "vitest";
import { extractCredentials, EXTRACTION_TIMEOUT } from "../../index";

describe("Ivy Tech Community College", { timeout: EXTRACTION_TIMEOUT }, () => {
  test(
    "Accounting",
    async () => {
      const url = "https://www.ivytech.edu/programs/all-academic-programs/school-of-business-logistics-supply-chain/accounting/";
      const credentials = await extractCredentials(url);

      expect(credentials).toEqual([
        {
          credential_description: expect.like(
            "The Associate of Applied Science (AAS) in Accounting degree program is designed for students who want to move into a career in accounting quickly. An AAS degree is the perfect first step toward your career goals if you are looking to start a career in the accounting field and continue to build your accounting knowledge with real-world experience in the discipline or apply your accounting education to starting your own business."
          ),
          credential_name: expect.like("Associate of Applied Science"), // TODO: this is not the correct credential name
          "credential_type": "AssociateDegree",
          "language": "English"
        },
        {
          credential_description: expect.like(
            "The Associate of Science (AS) in Accounting degree program is designed for students who want to have a head start on their accounting education. This program prepares students to pursue accounting at a four-year college or university."
          ),
          credential_name: expect.like("Associate of Science"), // TODO: this is not the correct credential name
          credential_type: "AssociateDegree",
          language: "English",
        },
        {
          credential_description: expect.like(
            "The Accounting Technical Certificate (TC) program offers students the opportunity to go from school to work in one year. This program prepares graduates to be ready for a career in accounting by offering a strong foundation of education in accounting."
          ),
          credential_name: expect.like("Accounting"),
          credential_type: "Certificate",
          language: "English",
        },
        {
          credential_description: expect.like(
            "The Short-Term Certificate in Enrolled Agent program teaches students how to prepare taxes. From working in an office to starting a business, graduates are ready for many career opportunities with this credential."
          ),
          credential_name: expect.like("Enrolled Agent"),
          credential_type: "Certificate",
          language: "English",
        },
        {
          credential_description: expect.like(
            "The Short-Term Certificate in Professional Bookkeeping and Payroll program gives students the skillset to manage records and payroll for an organization. Graduates from this program are ready for a career in bookkeeping upon graduation."
          ),
          credential_name: expect.like("Professional Bookkeeping and Payroll"),
          credential_type: "Certificate",
          language: "English",
        },
      ]);
    }
  );
});
