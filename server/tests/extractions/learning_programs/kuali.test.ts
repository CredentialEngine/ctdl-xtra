import { describe, test } from "vitest";
import { assertExtraction, EXTRACTION_TIMEOUT } from "../..";
import {
  CatalogueType,
  LearningProgramStructuredData,
} from "../../../../common/types";

describe("Kuali", { timeout: EXTRACTION_TIMEOUT }, () => {
  describe("Arizona State University Online", () => {
    test("Standard Learning Program", async () => {
      await assertExtraction<LearningProgramStructuredData>(
        "https://asuonline.asu.edu/online-degree-programs/undergraduate/bachelor-science-engineering-electrical-engineering/",
        [
          {
            learning_program_id:
              "Bachelor of Science in Engineering in Electrical Engineering",
            learning_program_name:
              "Bachelor of Science in Engineering in Electrical Engineering",
            learning_program_description: `In Arizona State University’s Bachelor of Science in Engineering in electrical engineering online, you’ll develop engineering skills with a focus on the design of electric power systems, electronics, signal processing algorithms, antennas and semiconductor devices. Upon graduation, you’ll be prepared for careers that pioneer new technologies in robotics, computing, the energy sector and more.`,
          },
        ],
        true,
        CatalogueType.LEARNING_PROGRAMS
      );
    });
  });
});
