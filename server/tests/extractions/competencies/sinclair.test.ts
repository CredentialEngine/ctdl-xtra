import { describe, test, expect } from "vitest";
import { extractCompetencies, EXTRACTION_TIMEOUT } from "../..";

describe("Sinclair", { timeout: EXTRACTION_TIMEOUT }, () => {
  describe("Sinclair Community College", () => {
    test("Accounting Program Learning Outcomes", async () => {
      const extractions = await extractCompetencies(
        "https://www.sinclair.edu/program/params/programCode/ACC-S-AAS/"
      );
      
      expect(extractions).arrayContaining([
        {
          "text": expect.like("Demonstrate effective verbal and written communication."),
          "competency_framework": expect.like("Accounting", 0.5),
          "language": "en"
        },
        {
          "text": expect.like("Describe and apply general business knowledge skills and computer skills."),
          "competency_framework": expect.like("Accounting", 0.5),
          "language": "en"
        },
        {
          "text": expect.like("Apply analytical problem-solving skills."),
          "competency_framework": expect.like("Accounting", 0.5),
          "language": "en"
        },
        {
          "text": expect.like("Apply mathematical skills to formulas and solve problems."),
          "competency_framework": expect.like("Accounting", 0.5),
          "language": "en"
        },
        {
          "text": expect.like("Apply the principles of financial, managerial, cost and tax accounting."),
          "competency_framework": expect.like("Accounting", 0.5),
          "language": "en"
        },
        {
          "text": expect.like("Apply principles of human creativity and its relation to society."),
          "competency_framework": expect.like("Accounting", 0.5),
          "language": "en"
        }
      ]);
    });
  });
});