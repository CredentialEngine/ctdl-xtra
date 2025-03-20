import { describe, test } from "vitest";
import { assertExtraction, EXTRACTION_TIMEOUT } from "../..";
import {
  CatalogueType,
  LearningProgramStructuredData,
} from "../../../../common/types";

describe("Clean Catalog", { timeout: EXTRACTION_TIMEOUT }, () => {
  describe("Atlantic Cape Community College", () => {
    test("Standard Learning Program", async () => {
      await assertExtraction<LearningProgramStructuredData>(
        "https://catalog.atlanticcape.edu/aviation/flight-instructor",
        [
          {
            learning_program_id: "Flight Instructor",
            learning_program_name: "Flight Instructor",
            learning_program_description: `The Flight Instructor Certificate provides students with an opportunity to obtain the knowledge, expertise, and aeronautical proficiency necessary to meet the requirements for a commercial rating with an airplane or a helicopter category and a single-engine land class rating, and a flight instructor certificate with an airplane category rating and single-engine class rating.`,
          },
        ],
        true,
        CatalogueType.LEARNING_PROGRAMS
      );
    });
  });
});
