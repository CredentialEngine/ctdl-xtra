import { test, expect, describe } from "vitest";
import { extractCredentials, EXTRACTION_TIMEOUT } from "../../index";

describe("Bismarck State College", { timeout: EXTRACTION_TIMEOUT }, () => {
  test(
    "Advanced Digital Technologies",
    async () => {
      const url =
        "https://catalog.bismarckstate.edu/catalog/degrees/career-technical-education/advanced-digital-technologies/";
      const credentials = await extractCredentials(url);

      // Verify the credential details
      expect(credentials).toEqual([
        {
          credential_name: expect.like("Advanced Digital Technologies Associate in Applied Science"),
          credential_description: expect.like(
            `With an ever-changing workplace, many employers desire graduates who have well-rounded educational backgrounds including skills related to digital technology. The Advanced Digital Technology degree offers students an opportunity to combine three short-term certificates (16+ credits each) that are job skill related into one AAS degree. The certificates would include coursework from technical fields including cybersecurity, mobile application development, management, and exercise science.

The Advanced Digital Technologies degree empowers students to customize their degree based on educational and professional goals. The short-term certificates are designed to provide you with workforce-ready technical skills in addition to strengthening your critical thinking, analysis, problem solving, and communication skills.`
          ),
          credential_type: "AssociateDegree",
          language: "English",
        },
      ]);
    }
  );

  test(
    "Computer Networking",
    async () => {
      const url = "https://bismarckstate.edu/academics/programs/Computer%20Networking";
      const credentials = await extractCredentials(url);

      expect(credentials).toEqual([
        {
          credential_name: expect.like("Computer Networking"),
          credential_description: expect.like(
            `The Certificate in Computer Networking is a great way to kick-start your career. You may choose from online and on-campus course-delivery options. This flexibility allows you to complete coursework at your convenience and on your schedule.`
          ),
          credential_type: "Certificate",
          language: "English",
        },
      ]);
    }
  );
});
