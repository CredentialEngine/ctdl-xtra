import { describe, test } from "vitest";
import { assertExtraction, EXTRACTION_TIMEOUT } from "../..";
import {
  CatalogueType,
  LearningProgramStructuredData,
} from "../../../../common/types";

describe("Other / Unknown", { timeout: EXTRACTION_TIMEOUT }, () => {
  describe("Rio Salado College", () => {
    test("Standard Learning Program", async () => {
      await assertExtraction<LearningProgramStructuredData>(
        "https://www.riosalado.edu/degrees-certificates/behavioral-science-and-human-services/firearms-5971n-ccl",
        [
          {
            learning_program_id: "5971N",
            learning_program_name: "Firearms",
            learning_program_description: `The Certificate of Completion (CCL) in Firearms program is designed to provide students with the training required for firearms qualification. Courses will cover firearms safety and nomenclature, care and cleaning of firearms and basic firearms usage techniques, as well as ammunition procedures, shooting positions, and qualification course experience.`,
          },
        ],
        true,
        CatalogueType.LEARNING_PROGRAMS
      );
    });
  });

  describe("Camden County College", () => {
    test("Standard Learning Program", async () => {
      await assertExtraction<LearningProgramStructuredData>(
        "https://www.camdencc.edu/program/carpentry-technology/",
        [
          {
            learning_program_id: "Carpentry Technology",
            learning_program_name: "Carpentry Technology",
            learning_program_description: `This program offers both a hands-on and textbook instruction, which requires problem solving and logical thinking skills. All phases of residential carpentry are addressed. Units included are print drawing/reading, estimation time/material, frame construction, rooﬁng/ siding, drywall and ﬁnish carpentry. Graduates are limited only by their own inventiveness. Any one or part of one unit covered during this program could be expanded into a career. Planning, estimation, drafting, framing, siding/rooﬁng, drywall installation, trim/cabinet installation, painting, building supply or hardware store person are but a few possibilities.`,
          },
        ],
        true,
        CatalogueType.LEARNING_PROGRAMS
      );
    });
  });

  describe("Mercer County Community College", () => {
    test("Standard Learning Program", async () => {
      await assertExtraction<LearningProgramStructuredData>(
        "https://catalog.mccc.edu/programs/BUS.STUD.ENTR.AAS",
        [
          {
            learning_program_id: "BUS.STUD.ENTR.AAS",
            learning_program_name: "Business Studies - Entrepreneurship",
            learning_program_description: `Business Studies, a career and non-transferable degree program, provides opportunities for students to prepare for a wide variety of careers in business. Students have the option of pursuing a general degree in Business Studies or selecting one of four concentrations, each comprised of 15 credits and designed to prepare students for specialty areas: Business Systems, Entrepreneurship, Management, Software Professional. Students should contact the program coordinator for advisement.`,
          },
        ],
        true,
        CatalogueType.LEARNING_PROGRAMS
      );
    });
  });
});
