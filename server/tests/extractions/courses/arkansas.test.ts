import { describe, test } from "vitest";
import { assertExtraction, EXTRACTION_TIMEOUT } from "../..";

describe("Arkansas Department of Education", { timeout: EXTRACTION_TIMEOUT }, () => {
  describe("Course Catalog", () => {
    test("World History Course", async () => {
      await assertExtraction(
        "https://adedata.arkansas.gov/ccms/CourseCatalog",
        [
          {
            course_id: "571000",
            course_name: "World History",
            course_description: "Differentiates deep geographic reasoning, knowledge, and skills as students focus on spatial relationships, places, regions, and human systems including the application of geographic thinking skills to students' immediate world around them, as well as in their local communities and cities. Assembles spatial and environmental perspectives and explores available geospatial technologies to analyze and interpret a variety of geographic representations, pictorial and graphic evidence, and data.",
            course_credits_min: 1,
            course_credits_max: 1,
            course_credits_type: undefined,
            course_grade_range: {
              min: 9,
              max: 12
            }
          }
        ]
      );
    });
  });
}); 