import { test, expect, describe } from "vitest";
import { extractCredentials, EXTRACTION_TIMEOUT } from "../../index";

describe("Microsoft Certifications", { timeout: EXTRACTION_TIMEOUT }, () => {
  test(
    "Microsoft 365 Administrator Expert",
    async () => {
      const url = "https://learn.microsoft.com/en-us/credentials/certifications/m365-administrator-expert/";
      const credentials = await extractCredentials(url);

      expect(credentials).toEqual([
        {
          // Refer to [volatile]
          // credential_description: expect.like(
          //   "Microsoft 365 Certified: Administrator Expert certification is designed for administrators who deploy and manage Microsoft 365 and perform Microsoft 365 tenant-level implementation and administration of cloud and hybrid environments."
          // ),
          credential_description: expect.any(String),
          credential_name: expect.like("Microsoft 365 Certified: Administrator Expert"),
          credential_type: "Certificate",
          language: "English",
        }
      ]);
    }
  );

  test(
    "Microsoft 365 Collaboration Communications Systems Engineer Associate",
    async () => {
      const url = "https://learn.microsoft.com/en-us/certifications/m365-collaboration-communications-systems-engineer";
      const credentials = await extractCredentials(url);

      expect(credentials).toEqual([
        {
          // Refer to [volatile]
          // credential_description: expect.like(
          //   "Microsoft 365 Certified: Collaboration Communications Systems Engineer Associate certification demonstrates skills to configure, deploy, monitor, and manage Microsoft Teams Phone, meetings, and certified devices."
          // ),
          credential_description: expect.any(String),
          credential_name: expect.like("Microsoft 365 Certified: Collaboration Communications Systems Engineer Associate"),
          credential_type: "Certificate",
          language: "English",
        }
      ]);
    }
  );

  test(
    "Microsoft 365 Endpoint Administrator Associate",
    async () => {
      const url = "https://learn.microsoft.com/en-us/certifications/modern-desktop";
      const credentials = await extractCredentials(url);

      expect(credentials).toEqual([
        {
          // Refer to [volatile]
          // credential_description: expect.like(
          //   "Microsoft 365 Certified: Endpoint Administrator Associate certification demonstrates expertise in planning and executing an endpoint deployment strategy, using essential elements of modern management, co-management approaches, and Microsoft Intune integration."
          // ),
          credential_description: expect.any(String),
          credential_name: expect.like("Microsoft 365 Certified: Endpoint Administrator Associate"),
          credential_type: "Certificate",
          language: "English",
        }
      ]);
    }
  );

  test(
    "Microsoft 365 Exchange Online Support Engineer Specialty",
    async () => {
      const url = "https://learn.microsoft.com/en-us/certifications/m365-exchange-online-support-engineer-specialty";
      const credentials = await extractCredentials(url);

      expect(credentials).toEqual([
        {
          // Refer to [volatile]
          // credential_description: expect.like(
          //   "Microsoft 365 Certified: Exchange Online Support Engineer Specialty certification demonstrates expertise in identifying, troubleshooting, and resolving issues with Microsoft Exchange Online, hybrid Exchange environments, and related Exchange components, technologies, and services."
          // ),
          credential_description: expect.any(String),
          credential_name: expect.like("Microsoft 365 Certified: Exchange Online Support Engineer Specialty"),
          credential_type: "Certificate",
          language: "English",
        }
      ]);
    }
  );
});
