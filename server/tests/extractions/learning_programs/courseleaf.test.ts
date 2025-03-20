import { describe, test } from "vitest";
import { assertExtraction, EXTRACTION_TIMEOUT } from "../..";
import {
  CatalogueType,
  LearningProgramStructuredData,
} from "../../../../common/types";

describe("Courseleaf", { timeout: EXTRACTION_TIMEOUT }, () => {
  describe("North Dakota State University", () => {
    test("Standard Learning Program", async () => {
      await assertExtraction<LearningProgramStructuredData>(
        "https://www.ndsu.edu/programs/graduate/accountancy",
        [
          {
            learning_program_id: "Accountancy",
            learning_program_name: "Accountancy",
            learning_program_description:
              "The Master of Accountancy (MAcc) program at North Dakota State University (NDSU) is designed for students wishing to begin and/or accelerate their careers in public accounting, private industry, fraud investigation, and/or cost management. The MAcc program is a non-thesis, professional program delivered face-to-face in Barry Hall, located in downtown Fargo.  This program emphasizes the technical competency, critical thinking, and analytical skills necessary for students to start and advance in their accounting careers.  Students will be prepared to identify accounting issues, research the appropriate standards and tax law, analyze data, present possible solutions and recommend actions.  In addition, students will enhance their ability to pass professional certiﬁcations, such as the Certiﬁed Public Accountant (CPA), Certiﬁed Management Accountant (CMA), and Certiﬁed Fraud Examiner (CFE).",
          },
        ],
        true,
        CatalogueType.LEARNING_PROGRAMS
      );
    });
  });

  describe("Bismarck State College", () => {
    test("Standard Learning Program", async () => {
      await assertExtraction<LearningProgramStructuredData>(
        "https://bismarckstate.edu/academics/programs/entrepreneur/",
        [
          {
            learning_program_id: "Entrepreneurship",
            learning_program_name: "Entrepreneurship",
            learning_program_description:
              "Students in BSC's Management Entrepreneurship program will obtain the skills, tools and experiences necessary to assist in the creation and management of a new business venture. The backbone of this curriculum focuses on satisfactorily completing a business plan and financial analysis. Study involves a combination of general education, business and marketing coursework.",
          },
        ],
        true,
        CatalogueType.LEARNING_PROGRAMS
      );
    });
  });
});
