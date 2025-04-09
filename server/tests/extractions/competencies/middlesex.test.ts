import { describe, test, expect } from "vitest";
import { extractCompetencies, EXTRACTION_TIMEOUT } from "../..";

describe("Middlesex", { timeout: EXTRACTION_TIMEOUT }, () => {
  describe("Middlesex County College", () => {
    test("Accounting Program Learning Outcomes", async () => {
      const extractions = await extractCompetencies(
        "https://www.course-catalog.com/mcc/C/2024-2025/degree/1"
      );
      
      expect(extractions).arrayContaining([
        {
          "text": expect.like("Possess a strong foundational knowledge of accounting principles, with the ability to analyze financial transactions, prepare and post journal entries and construct a complete set of financial statements. Apply foundational knowledge of accounting principles to prepare management reports, projections, and budget analysis."),
          "competency_framework": expect.like("Accounting", 0.5),
          "language": "en"
        },
        {
          "text": expect.like("Create written and computer-generated reports and documents using correct accounting terminology and references to current accounting pronouncements."),
          "competency_framework": expect.like("Accounting", 0.5),
          "language": "en"
        },
        {
          "text": expect.like("Demonstrate ethical/professional responsibility in the analysis and reporting of business financial data."),
          "competency_framework": expect.like("Accounting", 0.5),
          "language": "en"
        }
      ]);
    });
  });
}); 