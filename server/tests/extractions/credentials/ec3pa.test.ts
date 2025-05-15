import { test, expect, describe } from "vitest";
import { extractCredentials, EXTRACTION_TIMEOUT } from "../../index";

describe("EC3 Pennsylvania", { timeout: EXTRACTION_TIMEOUT }, () => {
  test(
    "Advanced Manufacturing",
    async () => {
      const url = "https://www.ec3pa.org/pathways-to-careers-at-ec3pa";
      const credentials = await extractCredentials(url);

      expect(credentials).toEqual([
        {
          credential_name: expect.like("Advanced Manufacturing"),
          credential_description: expect.like(
            "Career pathway program focusing on modern manufacturing techniques, automation, and industrial technology"
          ),
          credential_type: "Certificate",
          language: "English",
        },
      ]);
    }
  );

  test(
    "Information Technology",
    async () => {
      const url = "https://www.ec3pa.org/pathways-to-careers-at-ec3pa";
      const credentials = await extractCredentials(url);

      expect(credentials).toEqual([
        {
          credential_name: expect.like("Information Technology"),
          credential_description: expect.like(
            "Career pathway program providing training in computer systems, networking, and technical support"
          ),
          credential_type: "Certificate",
          language: "English",
        },
      ]);
    }
  );
}); 