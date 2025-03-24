import { describe, test } from "vitest";
import { assertExtraction, EXTRACTION_TIMEOUT } from "../..";
import {
  CatalogueType,
  LearningProgramStructuredData,
} from "../../../../common/types";

describe("CourseDog", { timeout: EXTRACTION_TIMEOUT }, () => {
  describe("Brookdale Community College", () => {
    test("Standard Learning Program", async () => {
      await assertExtraction<LearningProgramStructuredData>(
        "https://catalog.brookdalecc.edu/programs/HOSPM",
        [
          {
            learning_program_id: "HOSPM",
            learning_program_name: "Hospitality Management Program, A.S.",
            learning_program_description: `The Hospitality Management A.S. is a transfer program designed for students seeking a management position in the hospitality industry. This industry encompasses restaurants, hotels, event planning, theme parks, beach clubs, golf courses, resorts, cruise lines, casinos and sporting events. The program curricula includes coursework in business, management, marketing, and accounting in addition to hospitality courses in event planning, menu planning, travel and tourism and hotel operations. Monmouth County provides numerous opportunities for employment and advancement in the hospitality business. The objective of this program is to offer a new educational transfer program at Brookdale that provides career opportunities and aligns with local business and industry needs.`,
          },
        ],
        true,
        CatalogueType.LEARNING_PROGRAMS
      );
    });
  });

  describe("Commonwealth University-Bloomsburg", () => {
    test("Standard Learning Program", async () => {
      await assertExtraction<LearningProgramStructuredData>(
        "https://va-commonwealth.catalog.prod.coursedog.com/programs/SCUL-BFA-Concentration",
        [
          {
            learning_program_id: "SCUL-BFA-Concentration",
            learning_program_name: "Visual Arts BFA - Sculpture",
            learning_program_description: `The Bachelor of Fine Arts in Visual Arts will offer students a NASAD accredited professional degree in Visual Arts with a choice of concentration in multiple areas: and (BU/LHU/MU) Art History and Graphic Design; (BU only) Painting; Drawing; Fabric Design; Printmaking; Sculpture; Photography; (LHU/MU only) 2D Media; 3D Media.`,
          },
        ],
        true,
        CatalogueType.LEARNING_PROGRAMS
      );
    });
  });
});
