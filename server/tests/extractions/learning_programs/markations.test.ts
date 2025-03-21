import { describe, test } from "vitest";
import { assertExtraction, EXTRACTION_TIMEOUT } from "../..";
import {
  CatalogueType,
  LearningProgramStructuredData,
} from "../../../../common/types";

describe("Markations", { timeout: EXTRACTION_TIMEOUT }, () => {
  describe("Middlesex College", () => {
    test("Standard Learning Program", async () => {
      await assertExtraction<LearningProgramStructuredData>(
        "https://www.course-catalog.com/mcc/C/2024-2025/degree/58",
        [
          {
            learning_program_id: "Liberal Arts - Dance",
            learning_program_name: "Liberal Arts - Dance",
            learning_program_description: `This program provides graduates a foundation for lifelong intellectual development and college transfer following associate’s degree completion. A Liberal Arts degree also develops a set of critical thinking skills students may use over the course of their professional careers.`,
          },
        ],
        true,
        CatalogueType.LEARNING_PROGRAMS
      );
    });
  });
});
