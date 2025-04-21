import { describe, test, expect } from "vitest";
import { extractCompetencies, EXTRACTION_TIMEOUT } from "../..";

describe("Passaic County Community College", { timeout: EXTRACTION_TIMEOUT }, () => {
  describe("Passaic County Community College", () => {
    test("Accounting", async () => {
      const extractions = await extractCompetencies(
        "https://catalog.pccc.edu/program/178/"
      );

      expect(extractions).arrayContaining([
        {
          "text": expect.like("Implement the accounting cycle."),
          "competency_framework": expect.like("Accounting", 0.5),
          "language": "en"
        },
        {
          "text": expect.like("Analyze a company's financial position."),
          "competency_framework": expect.like("Accounting", 0.5),
          "language": "en"
        },
        {
          "text": expect.like("Create an accounting system for a company using accounting software."),
          "competency_framework": expect.like("Accounting", 0.5),
          "language": "en"
        },
        {
          "text": expect.like("Prepare federal and state personal income tax returns using tax software."),
          "competency_framework": expect.like("Accounting", 0.5),
          "language": "en"
        },
        {
          "text": expect.like("Evaluate ethical concepts inherent in an accounting environment."),
          "competency_framework": expect.like("Accounting", 0.5),
          "language": "en"
        },
        {
          "text": expect.like("Develop operating and cash budgets."),
          "competency_framework": expect.like("Accounting", 0.5),
          "language": "en"
        },
        {
          "text": expect.like("Develop supporting documents using Microsoft Excel."),
          "competency_framework": expect.like("Accounting", 0.5),
          "language": "en"
        }
      ]);
    });
  });
});
