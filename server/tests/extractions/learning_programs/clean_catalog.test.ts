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

  describe("Bristol Community College", () => {
    test("Standard Learning Program", async () => {
      await assertExtraction<LearningProgramStructuredData>(
        "https://catalog.bristolcc.edu/occupational-therapy/occupational-therapy-assistant",
        [
          {
            learning_program_id: "Occupational Therapy Assistant",
            learning_program_name: "Occupational Therapy Assistant",
            learning_program_description: `The mission of the Occupational Therapy Assistant Program advances the mission of Bristol Community College by providing an accessible, innovative, and inclusive education that prepares students to navigate and succeed in our ever-changing world. The program prepares generalist, entry-level occupational therapy assistants to practice under the supervision of registered occupational therapists in a variety of health care, home, school, workplace, community, and other settings. The OTA program prepares graduates to help people of all ages with physical, cognitive, psychosocial, sensory, emotional, and other challenges regain, develop, or master everyday skills in order to participate in meaningful occupations and live independent, productive and satisfying lives. The OTA program embraces the institutional values of student success, communication, respect, inclusion and innovation and conducts the program in a supportive community that values professionalism, evidence-based practice and lifelong learning, respects diversity and prepares well-rounded learners for employment.`,
          },
        ],
        true,
        CatalogueType.LEARNING_PROGRAMS
      );
    });
  });
});
