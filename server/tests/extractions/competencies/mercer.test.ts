import { describe, test, expect } from "vitest";
import { extractCompetencies, EXTRACTION_TIMEOUT } from "../..";

describe("Mercer", { timeout: EXTRACTION_TIMEOUT }, () => {
  describe("Mercer County Community College", () => {
    test("Architecture Program Learning Outcomes", async () => {
      const extractions = await extractCompetencies(
        "https://catalog.mccc.edu/programs/ARCH.AS"
      );
      
      // Variations occur between "Architecture" and "Architectural Program Outcomes"
      // for the competency framework - we reduce the threshold to 0.5 to account for this
      expect(extractions).arrayContaining([
        {
          "text": expect.like("Use analytical skills to determine the major elements of a work of architecture and/or an architectural design project"),
            "competency_framework": expect.like("Architecture", 0.5),
            "language": "en"
          },
          {
            "text": expect.like("Comprehend and apply the various stages of the creative thought process to produce an architectural design"),
            "competency_framework": expect.like("Architecture", 0.5),
            "language": "en"
          },
          {
            "text": expect.like("Understand and apply the basic principles of sustainable design"),
            "competency_framework": expect.like("Architecture", 0.5),
            "language": "en"
          },
          {
            "text": expect.like("Use two- and three-dimensional visual communication skills (freehand, traditional, and computer-generated drawings and physical models) to convey a complete architectural idea"),
            "competency_framework": expect.like("Architecture", 0.5),
            "language": "en"
          },
          {
            "text": expect.like("Demonstrate knowledge of the important buildings and stages in the history of architecture and the social and technological factors that influenced them"),
            "competency_framework": expect.like("Architecture", 0.5),
            "language": "en"
          },
          {
            "text": expect.like("Critically evaluate the built environment – its relationship to the natural world and the reciprocal sociological and psychological influences on man"),
            "competency_framework": expect.like("Architecture", 0.5),
            "language": "en"
          },
          {
            "text": expect.like("Demonstrate knowledge of architectural materials and structural systems and their appropriate applications in building construction"),
            "competency_framework": expect.like("Architecture", 0.5),
            "language": "en"
          }
        ]
      );
    });
  });
}); 