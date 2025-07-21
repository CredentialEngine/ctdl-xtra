import { test, expect, describe } from "vitest";
import { extractCredentials, EXTRACTION_TIMEOUT } from "../../index";

describe("Community College of Allegheny County", { timeout: EXTRACTION_TIMEOUT }, () => {
  test(
    "Barbering",
    async () => {
      const url = "https://catalog.ccac.edu/preview_program.php?catoid=14&poid=3381&returnto=4655";
      const credentials = await extractCredentials(url);

      expect(credentials).toEqual([
        {
          credential_name: expect.like("Barbering"),
          // Refer to [volatile]
          // credential_description: expect.like(
          //   "This 1,275 hour program prepares and trains students in the theory and practice of professional barbering.  Content includes didactic instruction and practical experience necessary to prepare students to sit for the Pennsylvania State Board of Barber Examiners licensing exam and for immediate employment in the barbering profession."
          // ),
          credential_description: expect.any(String),
          credential_type: "Certificate",
          language: "English",
        },
      ]);
    }
  );

  test(
    "Mathematics & Sciences",
    async () => {
      const url = "https://catalog.ccac.edu/preview_program.php?catoid=14&poid=3305&returnto=4655";
      const credentials = await extractCredentials(url);

      expect(credentials).toEqual([
        {
          credential_name: expect.like("Mathematics & Sciences"),
          // Refer to [volatile]
          // credential_description: expect.like(
          //   "This University Parallel Program provides the foundations for successful transfer to a baccalaureate degree at a four-year college or university in Science, Technology, Engineering and Mathematics (STEM) fields."
          // ),
          credential_description: expect.any(String),
          credential_type: "AssociateDegree",
          language: "English",
        },
      ]);
    }
  );
}); 