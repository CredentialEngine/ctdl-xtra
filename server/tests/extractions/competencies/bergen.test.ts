import { describe, test, expect } from "vitest";
import { extractCompetencies, EXTRACTION_TIMEOUT } from "../..";

describe("Bergen", { timeout: EXTRACTION_TIMEOUT }, () => {
  describe("Bergen Community College", () => {
    test("Radiation Therapy Technology Certificate Program Learning Outcomes", async () => {
      const extractions = await extractCompetencies(
        "https://catalog.bergen.edu/preview_program.php?catoid=8&poid=1185&returnto=367"
      );
      
      expect(extractions).arrayContaining([
        {
          "text": expect.like("Students will perform the tasks and responsibilities of a radiation therapist in a competent and knowledgeable manner."),
          "competency_framework": expect.like("Radiation Therapy Technology Certificate", 0.5),
          "language": "en"
        },
        {
          "text": expect.like("Students will demonstrate effective communication skills and participate as a collaborative team member with other medical professionals."),
          "competency_framework": expect.like("Radiation Therapy Technology Certificate", 0.5),
          "language": "en"
        },
        {
          "text": expect.like("Students will demonstrate problem solving and critical thinking skills essential to the practice of state-of-the-art radiation therapy."),
          "competency_framework": expect.like("Radiation Therapy Technology Certificate", 0.5),
          "language": "en"
        },
        {
          "text": expect.like("Students will demonstrate professional development and growth, and professional ethics in the clinical setting."),
          "competency_framework": expect.like("Radiation Therapy Technology Certificate", 0.5),
          "language": "en"
        }
      ]);
    });

    test("Machine Tooling Certificate of Achievement Program Learning Outcomes", async () => {
      const extractions = await extractCompetencies(
        "https://catalog.bergen.edu/preview_program.php?catoid=8&poid=1197&returnto=367"
      );
      
      expect(extractions).arrayContaining([
        {
          "text": expect.like("Express and implement all safety rules and procedures across the full scope of machining, welding and fabrication disciplines."),
          "competency_framework": expect.like("Machine Tooling Certificate of Achievement", 0.5),
          "language": "en"
        },
        {
          "text": expect.like("Recognize the theory and application of precision measurement and be able to apply these skills in a professional work environment."),
          "competency_framework": expect.like("Machine Tooling Certificate of Achievement", 0.5),
          "language": "en"
        },
        {
          "text": expect.like("Design, specify materials and construct fabricated mechanisms & structures using various measurements, machining, material-joining and fabrication techniques for application in a professional environment."),
          "competency_framework": expect.like("Machine Tooling Certificate of Achievement", 0.5),
          "language": "en"
        }
      ]);
    });
  });
}); 