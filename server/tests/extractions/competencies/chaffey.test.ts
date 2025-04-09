import { describe, test, expect } from "vitest";
import { extractCompetencies, EXTRACTION_TIMEOUT } from "../..";

describe("Chaffey", { timeout: EXTRACTION_TIMEOUT }, () => {
  describe("Chaffey College", () => {
    // TODO: Fix the extraction returning empty for this program
    test.skip("Program Competencies", async () => {
      const extractions = await extractCompetencies(
        "https://chaffey.programmapper.com/academics/interest-clusters/8c518b91-3ad0-41d1-b679-f14328f09ee2/programs/00f85d93-cb4e-59f2-585a-34ef88878c68"
      );
      
      expect(extractions).arrayContaining([
        {
          "text": expect.like("Demonstrate professional and creative operation of cinema cameras."),
          "competency_framework": expect.like("Cinema", 0.5),
          "language": "en"
        },
        {
          "text": expect.like("Demonstrate professional and creative competencies with microphone placement and audio operation."),
          "competency_framework": expect.like("Cinema", 0.5),
          "language": "en"
        },
        {
          "text": expect.like("Demonstrate professional and creative theories of lighting a set."),
          "competency_framework": expect.like("Cinema", 0.5),
          "language": "en"
        },
        {
          "text": expect.like("Demonstrate professional and creative theories of set design."),
          "competency_framework": expect.like("Cinema", 0.5),
          "language": "en"
        }
      ]);
    });
  });
}); 
