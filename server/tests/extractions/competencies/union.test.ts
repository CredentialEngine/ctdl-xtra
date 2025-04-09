import { describe, test, expect } from "vitest";
import { extractCompetencies, EXTRACTION_TIMEOUT } from "../..";

describe("Union", { timeout: EXTRACTION_TIMEOUT }, () => {
  describe("Union College of Union County", () => {
    test("Accounting Program Learning Outcomes", async () => {
      const extractions = await extractCompetencies(
        "http://onlinecatalog.ucc.edu/preview_program.php?catoid=11&poid=1498"
      );
      
      expect(extractions).arrayContaining([
        {
          "text": expect.like("Demonstrate the underlying theoretical and ethical framework of accounting concepts in business practice."),
          "competency_framework": expect.like("Accounting", 0.5),
          "language": "en"
        },
        {
          "text": expect.like("Evaluate the managerial application of accounting data and its intended impact."),
          "competency_framework": expect.like("Accounting", 0.5),
          "language": "en"
        },
        {
          "text": expect.like("Examine the governing principles of the practice of accounting."),
          "competency_framework": expect.like("Accounting", 0.5),
          "language": "en"
        },
        {
          "text": expect.like("Communicate effectively in a business setting through written, verbal and electronic formats."),
          "competency_framework": expect.like("Accounting", 0.5),
          "language": "en"
        },
        {
          "text": expect.like("Analyze the effect of globalization, and personal and cultural development on the practice of accounting."),
          "competency_framework": expect.like("Accounting", 0.5),
          "language": "en"
        },
        {
          "text": expect.like("Prepare a set of complete financial books and supportive records utilizing critical thinking skills and appropriate software and accounting principles."),
          "competency_framework": expect.like("Accounting", 0.5),
          "language": "en"
        },
        {
          "text": expect.like("Evaluate the various issues related to diversity, equity, and inclusion in the field of Accounting."),
          "competency_framework": expect.like("Accounting", 0.5),
          "language": "en"
        }
      ]);
    });
  });
}); 