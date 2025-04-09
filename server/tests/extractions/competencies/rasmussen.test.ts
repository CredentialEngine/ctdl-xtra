import { describe, test, expect } from "vitest";
import { extractCompetencies, EXTRACTION_TIMEOUT } from "../..";

describe("Rasmussen", { timeout: EXTRACTION_TIMEOUT }, () => {
  describe("Rasmussen University", () => {
    
    // This test generates high variations in the LLM output
    // In some cases it extracts the expected competencies in a shorter form
    // In other cases it extracts competencies from unrelated paragraphs in the page
    // In some, it extracts a different competency framework for each competency
    test.skip("Accounting Associate's Degree Program Learning Outcomes", async () => {
      const extractions = await extractCompetencies(
        "https://www.rasmussen.edu/degrees/business/accounting/associates/"
      );
      
      expect(extractions).arrayContaining([
        {
          "text": expect.like("Manage accounts receivable and accounts payable, general ledger, payroll, budgeting and forecasting. Understand financial and managerial accounting concepts as related to the business environment.", 0.8),
          "competency_framework": expect.like("Accounting", 0.8),
          "language": "en"
        },
        {
          "text": expect.like("Prepare tax returns, financial statements and other accounting functions through the use of a computer, including maintaining account records, input and process information and produce standard accounting reports.", 0.8),
          "competency_framework": expect.like("Accounting", 0.8),
          "language": "en"
        },
        {
          "text": expect.like("Utilize electronic spreadsheet features available in Excel, ranging from data input and manipulation to charting and pivot tables.", 0.8),
          "competency_framework": expect.like("Accounting", 0.8),
          "language": "en"
        },
        {
          "text": expect.like("Value written and interpersonal communication, critical thinking and problem-solving, information and financial literacy.", 0.8),
          "competency_framework": expect.like("Accounting", 0.8),
          "language": "en"
        }
      ]);
    });
  });
}); 