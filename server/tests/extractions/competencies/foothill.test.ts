import { describe, test, expect } from "vitest";
import { extractCompetencies, EXTRACTION_TIMEOUT } from "../..";

describe("Foothill", { timeout: EXTRACTION_TIMEOUT }, () => {
  describe("Foothill Community College", () => {

    // Spec: We are required to extract competencies from both learning outcomes and course objectives
    // Each should also have a type of outcome vs objective. Currently the LLM only extracts the first list.
    test.skip("Competencies for Financial Accounting I", async () => {
      const extractions = await extractCompetencies(
        "https://catalog.foothill.edu/course-outlines/ACTG-1A/"
      );
      
      expect(extractions).arrayContaining([
        {
          "text": "Explain financial accounting terminology, concepts, principles, and frameworks.",
          "competency_framework": "Financial Accounting I",
          "language": "en"
        },
        {
          "text": "Perform related calculations and demonstrate the ability to use methods and /or procedures to solve financial accounting problems.",
          "competency_framework": "Financial Accounting I",
          "language": "en"
        }
      ]);
    });

    test("No competencies with Magnetic Particle", async () => {
      const extractions = await extractCompetencies(
        "https://catalog.foothill.edu/course-outlines/AATA-101A/"
      );
      
      expect(extractions).arrayContaining(
      [
        {
          "text": expect.like("Understand the physics of magnetism"),
          "competency_framework": "Magnetic Particle Testing Level 1",
          "language": "en"
        },
        {
          "text": expect.like("Understand and work within the limitations of the method"),
          "competency_framework": "Magnetic Particle Testing Level 1",
          "language": "en"
        },
        {
          "text": expect.like("Select equipment to conduct test"),
          "competency_framework": "Magnetic Particle Testing Level 1",
          "language": "en"
        }
      ]);
    });
  });
});
