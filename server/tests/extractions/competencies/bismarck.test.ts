import { describe, test, expect } from "vitest";
import { extractCompetencies, EXTRACTION_TIMEOUT } from "../..";

describe("Bismarck", { timeout: EXTRACTION_TIMEOUT }, () => {
  describe("Bismarck State College", () => {
    test("Agribusiness Program Learning Outcomes", async () => {
      const extractions = await extractCompetencies(
        "https://bismarckstate.edu/academics/programs/Agribusiness/"
      );
      
      expect(extractions).arrayContaining([
        {
          "text": expect.like("Organize, interpret and analyze data using mathematical and statistical principles as well as calculate solutions to production related scenarios. Students will then relate these and other agricultural finance concepts to business management and marketing."),
          "competency_framework": expect.like("Agribusiness", 0.5),
          "language": "en"
        },
        {
          "text": expect.like("Apply knowledge & comprehension of plant/soil science and agribusiness knowledge to evaluate various novel production options and develop a new product, service, or management practice."),
          "competency_framework": expect.like("Agribusiness", 0.5),
          "language": "en"
        },
        {
          "text": expect.like("Communicate effectively regarding agriculture issues. Students will demonstrate workplace readiness through an ability to communicate effectively through oral communication, written communication and information literacy."),
          "competency_framework": expect.like("Agribusiness", 0.5),
          "language": "en"
        },
        {
          "text": expect.like("Demonstrate critical thinking and problem-solving skills as they apply to a variety of agriculture systems."),
          "competency_framework": expect.like("Agribusiness", 0.5),
          "language": "en"
        }
      ]);
    });
  });
}); 