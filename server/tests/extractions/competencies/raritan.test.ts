import { describe, test, expect } from "vitest";
import { extractCompetencies, EXTRACTION_TIMEOUT } from "../..";

describe("Raritan", { timeout: EXTRACTION_TIMEOUT }, () => {
  describe("Raritan Valley Community College", () => {
    test("Accounting Program Learning Outcomes", async () => {
      const extractions = await extractCompetencies(
        "https://catalog.raritanval.edu/preview_program.php?catoid=15&poid=1858&returnto=1319"
      );
      
      expect(extractions).arrayContaining([
        {
          "text": expect.like("Demonstrate the skills necessary to diagnose, service, and repair automotive systems encountered in skill level B and C to industry standards."),
          "competency_framework": expect.like("Automotive Technology", 0.5),
          "language": "en"
        },
        {
          "text": expect.like("Demonstrate the safe and proper use of tools and equipment necessary to diagnose and repair automotive systems to an acceptable standard in the automotive industry."),
          "competency_framework": expect.like("Automotive Technology", 0.5),
          "language": "en"
        },
        {
          "text": expect.like("Locate and apply technical service and repair information."),
          "competency_framework": expect.like("Automotive Technology", 0.5),
          "language": "en"
        },
        {
          "text": expect.like("Apply knowledge and practical experience in an automotive co-op."),
          "competency_framework": expect.like("Automotive Technology", 0.5),
          "language": "en"
        },
        {
          "text": expect.like("Complete manufacturer certification modules."),
          "competency_framework": expect.like("Automotive Technology", 0.5),
          "language": "en"
        }
      ]);
    });
  });
}); 