import { test, expect, describe } from "vitest";
import { extractCredentials, EXTRACTION_TIMEOUT } from "../../index";

describe("EC3 Pennsylvania", { timeout: EXTRACTION_TIMEOUT }, () => {
  test(
    "Criminal Justice",
    async () => {
      const url = "https://www.ec3pa.org/pathways-to-careers-at-ec3pa/criminal-justice/";
      const credentials = await extractCredentials(url);

      expect(credentials).toEqual([
        {
          credential_name: expect.like("Criminal Justice"),
          // Refer to [volatile]
          // credential_description: expect.like(
          //   "The Associate of Applied Science in Criminal Justice provides students with a comprehensive practical and professional knowledge of the Criminal Justice System, consisting of law enforcement, courts, and corrections. Students will develop a knowledge of the application of the law, social sciences, and criminology to prepare them to advance to the ACT120 Police Academy or transfer to a four-year college or university to obtain a bachelor's degree."
          // ),
          credential_description: expect.any(String),
          credential_type: "AssociateDegree",
          language: "English",
        },
      ]);
    }
  );

  test(
    "Corrections",
    async () => {
      const url = "https://www.ec3pa.org/pathways-to-careers-at-ec3pa/corrections/";
      const credentials = await extractCredentials(url);

      expect(credentials).toEqual([
        {
          credential_name: expect.like("Corrections"),
          // Refer to [volatile]
          // credential_description: expect.like(
          //   "The Corrections Program develops practical and professional knowledge and skills within the correctional field including the application of the law, social sciences, and criminology. The Certificate prepares students for entry level careers in corrections and employment opportunities within the correctional system."
          // ),
          credential_description: expect.any(String),
          credential_type: "Certificate",
          language: "English",
        },
      ]);
    }
  );

  test(
    "Software Development",
    async () => {
      const url = "https://www.ec3pa.org/pathways-to-careers-at-ec3pa/information-technology-software-development/";
      const credentials = await extractCredentials(url);

      expect(credentials).toEqual([
        {
          credential_name: expect.like("Software Development"),
          // Refer to [volatile]
          // credential_description: expect.like(
          //   "Graduates with the Associate of Applied Science (A.A.S) degree in Software Development will have the basic knowledge, skills, and abilities to obtain an entry-level position as a mobile app developer, programmer, or software quality assurance technician. Students that have completed the A.A.S degree program in Software Development will have knowledge in C#, Python, Java, JavaScript, and more."
          // ),
          credential_description: expect.any(String),
          credential_type: "AssociateDegree",
          language: "English",
        },
      ]);
    }
  );
}); 