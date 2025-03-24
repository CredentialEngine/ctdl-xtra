import { describe, test } from "vitest";
import { assertExtraction, EXTRACTION_TIMEOUT } from "../..";

describe("Kuali", { timeout: EXTRACTION_TIMEOUT }, () => {
  describe("BYU-Idaho", async () => {
    test("Course details - no prerequisites", async () => {
      await assertExtraction(
        "https://www.byui.edu/catalog/#/courses/414Six2j-?bc=true&bcCurrent=ACCTG100%20-%20Introduction%20to%20Accounting&bcGroup=Accounting&bcItemType=courses",
        [
          {
            course_id: "ACCTG100",
            course_name: "Introduction to Accounting",
            course_description:
              "This course is the first university-level accounting course most accounting students will take.  It highlights the five major fields of accounting: the accounting cycle, business decision-making, taxation, fraud detection and prevention, and financial statement analysis.  Students gain knowledge and practice in each of these fundamental fields as part of a learning team using case studies and experiential learning." +
              "Upon completion of this course, students will have a clear understanding of the opportunities available to graduates with a degree in accounting, the different career paths available, and the effort required to successfully complete the accounting major at BYU-Idaho.",
            course_credits_min: 2,
            course_credits_max: 2,
            course_credits_type: undefined,
          },
        ]
      );
    });

    test("Course details - with prerequisites", async () => {
      await assertExtraction(
        "https://www.byui.edu/catalog/#/courses/418holno-?group=Chemistry&bc=true&bcCurrent=CHEM106%20-%20General%20Chemistry%20II&bcGroup=Chemistry&bcItemType=courses",
        [
          {
            course_id: "CHEM106",
            course_name: "General Chemistry II",
            course_description:
              "This is the second in a two-semester course designed to meet the general chemistry requirements in engineering, science, and pre-professional majors.",
            course_prerequisites:
              "Complete all of the following Take the following: CHEM105 - General Chemistry I (3) Take 1 of the following: MATH112X - Calculus I (4) MATH109 - Precalculus (5) MATH113 - Calculus II (3) MATH119 - Applied Calculus for Data Analysis (4) MATH110X - College Algebra (3) The math requirement can be waived with an ALEKS score of 70 or higher.",
          },
        ],
        true
      );
    });
  });
});
