import { describe, test, expect } from "vitest";
import { extractCompetencies, EXTRACTION_TIMEOUT } from "../..";

describe("RioSalado", { timeout: EXTRACTION_TIMEOUT }, () => {
  describe("Rio Salado College", () => {
    test("Accounting Certificate Program Learning Outcomes", async () => {
      const extractions = await extractCompetencies(
        "https://www.riosalado.edu/degrees-certificates/business-entrepreneurialism-and-management/accounting-5665-ccl"
      );
      
      expect(extractions).arrayContaining([
        {
          "text": expect.like("Use basic mathematics and accounting principles to report the financial position of an organization."),
          "competency_framework": expect.like("Accounting", 0.5),
          "language": "en"
        },
        {
          "text": expect.like("Apply current technology to specific business tasks."),
          "competency_framework": expect.like("Accounting", 0.5),
          "language": "en"
        },
        {
          "text": expect.like("Evaluate the legal, ethical and social implications of business decisions and their impact on various individuals, groups and societies."),
          "competency_framework": expect.like("Accounting", 0.5),
          "language": "en"
        },
        {
          "text": expect.like("Demonstrate critical thinking through written and oral formats."),
          "competency_framework": expect.like("Accounting", 0.5),
          "language": "en"
        },
        {
          "text": expect.like("Apply functions of modern business, including business principles, marketing, labor relations, and risk to business situations."),
          "competency_framework": expect.like("Accounting", 0.5),
          "language": "en"
        },
        {
          "text": expect.like("Apply principles and practices of accounting to analyze and interpret general purpose financial statements."),
          "competency_framework": expect.like("Accounting", 0.5),
          "language": "en"
        },
        {
          "text": expect.like("Apply basic rules of financial accounting to business transactions."),
          "competency_framework": expect.like("Accounting", 0.5),
          "language": "en"
        },
        {
          "text": expect.like("Apply basic rules of managerial accounting to business decision making."),
          "competency_framework": expect.like("Accounting", 0.5),
          "language": "en"
        },
        {
          "text": expect.like("Apply appropriate procedures to prepare individual, partnership, and corporate taxes, including tax reporting for income, payroll, sales, and personal property."),
          "competency_framework": expect.like("Accounting", 0.5),
          "language": "en"
        },
        {
          "text": expect.like("Demonstrate an understanding of compliance in accounting, reporting and tax."),
          "competency_framework": expect.like("Accounting", 0.5),
          "language": "en"
        }
      ]);
    });
  });
}); 