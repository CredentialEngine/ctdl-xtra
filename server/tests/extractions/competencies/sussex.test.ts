import { describe, test, expect } from "vitest";
import { extractCompetencies, EXTRACTION_TIMEOUT } from "../..";

describe("Sussex", { timeout: EXTRACTION_TIMEOUT }, () => {
  describe("Sussex County Community College", () => {
    test("Accounting Program Learning Outcomes", async () => {
      const extractions = await extractCompetencies(
        "https://catalog.sussex.edu/preview_program.php?catoid=6&poid=806&returnto=331"
      );
      
      expect(extractions).arrayContaining([
        {
          "text": expect.like("Demonstrate knowledge of generally accepted accounting principles (GAAP)."),
          "competency_framework": expect.like("Accounting", 0.5),
          "language": "en"
        },
        {
          "text": expect.like("Describe and implement all the steps in the accounting cycle."),
          "competency_framework": expect.like("Accounting", 0.5),
          "language": "en"
        },
        {
          "text": expect.like("Construct and interpret basic financial statements (balance sheets, income statements, the statement of cash flow, etc.)."),
          "competency_framework": expect.like("Accounting", 0.5),
          "language": "en"
        },
        {
          "text": expect.like("Identify and develop effective internal control systems."),
          "competency_framework": expect.like("Accounting", 0.5),
          "language": "en"
        },
        {
          "text": expect.like("Identify unethical accounting practices and describe the basic aspects of the Sarbane-Oxley Act as related to ethical accounting practices."),
          "competency_framework": expect.like("Accounting", 0.5),
          "language": "en"
        },
        {
          "text": expect.like("Utilize computer spreadsheet programs to record various types of accounting information and perform basic day-to-day accounting operations."),
          "competency_framework": expect.like("Accounting", 0.5),
          "language": "en"
        }
      ]);
    });
  });
}); 