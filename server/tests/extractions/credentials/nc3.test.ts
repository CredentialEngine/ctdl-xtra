import { test, expect, describe } from "vitest";
import { extractCredentials, EXTRACTION_TIMEOUT } from "../../index";

describe("NC3 Certifications", { timeout: EXTRACTION_TIMEOUT }, () => {
  test(
    "Certified Industry 4.0 Associate - Fundamentals",
    async () => {
      const url = "https://www.nc3.net/wp-content/uploads/2023/03/Certified-Industry-4.0-Associate-%E2%80%93-Fundamentals-Overview-031023.pdf";
      const credentials = await extractCredentials(url);

      expect(credentials).toEqual([
        {
          credential_description: expect.like(
            "Students who pass the Certified Industry 4.0 Associate – Fundamentals comprehensive knowledge exam will be well-rounded machine operators/technicians, with responsibility for efficient operation of the equipment. They will ensure that the system is running at maximum capacity with an understanding of the role of each component and device. They can identify malfunctions and make minor repairs. To be eligible for the Certified Industry 4.0 Associate – Fundamentals comprehensive knowledge exam students must complete all other Level 1 Certifications listed as prerequisites."
          ),
          credential_name: expect.like("Certified Industry 4.0 Associate", 0.5), // TODO: Fix high variance
          credential_type: "Certificate",
          language: "English",
        }
      ]);
    }
  );

  test(
    "Festo Certification Program Guide - Electricity",
    async () => {
      const url = "https://www.nc3.net/wp-content/uploads/2023/03/Festo-Certification-Program-Guide_Electricity-031023.pdf";
      const credentials = await extractCredentials(url);

      expect(credentials).toEqual([
        {
          credential_description: expect.like(
            "These industry recognized certifications have been specifically developed to give students the knowledge and skills required to enable them to work safely and effectively with electricity. The lab components of the training offer the student the opportunity to build, test and troubleshoot AC/DC circuits and examine the operating voltages and currents related to proper circuit operation. Technicians will use various instruments to make circuit measurements and calculations."
          ),
          credential_name: expect.like("Electricity"),
          credential_type: "Certificate",
          language: "English",
        }
      ]);
    }
  );
}); 