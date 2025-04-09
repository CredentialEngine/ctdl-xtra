import { describe, test, expect } from "vitest";
import { extractCompetencies, EXTRACTION_TIMEOUT } from "../..";

describe("Quinsigamond Community College", { timeout: EXTRACTION_TIMEOUT }, () => {
  describe("Quinsigamond Community College", () => {
    test("Computer Information Systems - Transfer Option", async () => {
      const extractions = await extractCompetencies(
        "https://www.qcc.edu/computer-and-information-technology/computer-information-systems-transfer-option"
      );
      expect(extractions).arrayContaining(
        [
          {
            "text": expect.like("Analyze and design information systems and database applications solutions to achieve business/organizational goals."),
            "competency_framework": "Computer Information Systems - Transfer Option",
            "language": "en"
          },
          {
            "text": expect.like("Implement a designed solution to solve business Information Systems (IS) problems using state-of-the-art programming techniques and application software."),
            "competency_framework": "Computer Information Systems - Transfer Option",
            "language": "en"
          },
          {
            "text": expect.like("Apply end user basic software to develop word processing documents, spreadsheets, and presentations."),
            "competency_framework": "Computer Information Systems - Transfer Option",
            "language": "en"
          },
          {
            "text": expect.like("Apply knowledge to computing and mathematics appropriate to the discipline."),
            "competency_framework": "Computer Information Systems - Transfer Option",
            "language": "en"
          },
          {
            "text": expect.like("Think critically and apply the scientific method."),
            "competency_framework": "Computer Information Systems - Transfer Option",
            "language": "en"
          },
          {
            "text": expect.like("Present technical solutions effectively."),
            "competency_framework": "Computer Information Systems - Transfer Option",
            "language": "en"
          },
          {
            "text": expect.like("Exhibit professional, legal, and ethical behavior."),
            "competency_framework": "Computer Information Systems - Transfer Option",
            "language": "en"
          }
        ]
      );
    });
  });
});
