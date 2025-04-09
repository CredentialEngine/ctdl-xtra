import { describe, test, expect } from "vitest";
import { extractCompetencies, EXTRACTION_TIMEOUT } from "../..";

describe("DeAnza", { timeout: EXTRACTION_TIMEOUT }, () => {
  describe("De Anza College", () => {
    
    // To do: Fix the LLM returning an empty list for this page
    test.skip("Financial Accounting I - Honors Learning Outcomes", async () => {
      const extractions = await extractCompetencies(
        "https://www.deanza.edu/catalog/courses/outline.html?y=2024-2025&course=acctd01ah"
      );
      
      expect(extractions).arrayContaining([
        {
          "text": expect.like("Recognize accounting's role in society and how accounting meets the information needs of investors and creditors."),
          "competency_framework": expect.like("Financial Accounting", 0.5),
          "language": "en"
        },
        {
          "text": expect.like("Analyze fundamental business concepts, how businesses operate and how accounting serves them."),
          "competency_framework": expect.like("Financial Accounting", 0.5),
          "language": "en"
        },
        {
          "text": expect.like("Analyze fundamental accounting concepts underlying financial statements."),
          "competency_framework": expect.like("Financial Accounting", 0.5),
          "language": "en"
        },
        {
          "text": expect.like("Evaluate the uses and limitations of financial statements."),
          "competency_framework": expect.like("Financial Accounting", 0.5),
          "language": "en"
        },
        {
          "text": expect.like("Evaluate the usefulness of information produced by an accounting system and how it is directly related to that system's design."),
          "competency_framework": expect.like("Financial Accounting", 0.5),
          "language": "en"
        },
        {
          "text": expect.like("Analyze ethical issues within an accounting/business framework."),
          "competency_framework": expect.like("Financial Accounting", 0.5),
          "language": "en"
        },
        {
          "text": expect.like("Define and explain the conceptual framework of accounting."),
          "competency_framework": expect.like("Financial Accounting", 0.5),
          "language": "en"
        },
        {
          "text": expect.like("Demonstrate a deeper understanding of the material through completion of an honors assignment."),
          "competency_framework": expect.like("Financial Accounting", 0.5),
          "language": "en"
        }
      ]);
    });
  });
}); 