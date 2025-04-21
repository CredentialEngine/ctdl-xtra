import { describe, test, expect } from "vitest";
import { extractCompetencies, EXTRACTION_TIMEOUT } from "../..";

describe("Camden County College", { timeout: EXTRACTION_TIMEOUT }, () => {
  test(
    "Accounting Program Learning Outcomes",
    async () => {
      const result = await extractCompetencies(
        "https://www.camdencc.edu/program/accounting/"
      );

      expect(result).arrayContaining(
        [
          {
            "text": expect.like("Maintain systematic and up-to-date records of business transactions."),
            "competency_framework": expect.like("Accounting"),
            "language": "en"
          },
          {
            "text": expect.like("Prepare financial statements, including income statements, statement of owner’s equity, balance sheets, and statement of cash flow."),
            "competency_framework": expect.like("Accounting"),
            "language": "en"
          },
          {
            "text": expect.like("Use computer software to design and maintain bookkeeping and accounting systems."),
            "competency_framework": expect.like("Accounting"),
            "language": "en"
          }
        ]
      );
    }
  );
}); 