import { describe, expect, test } from "vitest";
import { detectExploratoryPages, extractCompetencies, EXTRACTION_TIMEOUT } from "../..";

describe("Indiana", { timeout: EXTRACTION_TIMEOUT }, () => {
  describe("Indiana University", () => {
    test("Computer Science Minor", async () => {
      await expect(extractCompetencies(
        "https://catalog.indstate.edu/preview_program.php?catoid=60&poid=10533&returnto=3288",
      )).resolves.toEqual([]);

      await expect(detectExploratoryPages(
        "https://catalog.indstate.edu/preview_program.php?catoid=60&poid=10533&returnto=3288",
      )).resolves.toEqual([]);
    });

    // Results lack the numbering of competencies
    test.skip("Automation and Control Engineering Technology Major", async () => {
      await expect(extractCompetencies(
        "https://catalog.indstate.edu/preview_program.php?catoid=60&poid=10511&returnto=3288",
      )).resolves.toEqual([]);

      await expect(detectExploratoryPages(
        "https://catalog.indstate.edu/preview_program.php?catoid=60&poid=10511&returnto=3288",
      )).resolves.toEqual([
        "https://catalog.indstate.edu/content.php?catoid=60&navoid=3220#Student%20Outcomes",
      ]);

      await expect(extractCompetencies(
        "https://catalog.indstate.edu/content.php?catoid=60&navoid=3220#Student%20Outcomes",
      )).resolves.arrayContaining([
        {
          "competency_framework": expect.like("Automation And Control Engineering Technology"),
          "language": "en",
          "text": expect.like("an ability to apply knowledge, techniques, skills and modern tools of mathematics, science, engineering, and technology to solve broadly-defined engineering problems appropriate to the discipline"),
        },
        {
          "competency_framework": expect.like("Automation And Control Engineering Technology"),
          "language": "en",
          "text": expect.like("an ability to design systems, components, or processes meeting specified needs for broadly-defined engineering problems appropriate to the discipline"),
        },
        {
          "competency_framework": expect.like("Automation And Control Engineering Technology"),
          "language": "en",
          "text": expect.like("an ability to apply written, oral, and graphical communication in broadly-defined technical and non-technical environments; and an ability to identify and use appropriate technical literature"),
        },
        {
          "competency_framework": expect.like("Automation And Control Engineering Technology"),
          "language": "en",
          "text": expect.like("an ability to conduct standard tests, measurements, and experiments and to analyze and interpret the results to improve processes"),
        },
        {
          "competency_framework": expect.like("Automation And Control Engineering Technology"),
          "language": "en",
          "text": expect.like("an ability to function effectively as a member as well as a leader on technical teams"),
        },
      ]
      );
    });

    test("Accounting outcomes", async () => {
      await expect(extractCompetencies(
        "https://catalog.indstate.edu/content.php?catoid=60&navoid=3240",
      )).resolves.arrayContaining(
        [
          {
            "competency_framework": expect.like("Accounting Learning Outcomes"),
            "language": "en",
            "text": expect.like("1.1 Students are able to describe the language and procedures associated with financial accounting."),
          },
          {
            "competency_framework": expect.like("Accounting Learning Outcomes"),
            "language": "en",
            "text": expect.like("2.1 Students are able to define and identify cost accounting theory and concepts."),
          },
          {
            "competency_framework": expect.like("Accounting Learning Outcomes"),
            "language": "en",
            "text": expect.like("3.1 Students are able to define the terminology of tax accounting."),
          },
          {

            "competency_framework": expect.like("Accounting Learning Outcomes"),

            "language": "en",
            "text": expect.like("4.1 Students are able to identify audit and assurance concepts."),
          },
          {
            "competency_framework": expect.like("Accounting Learning Outcomes"),
            "language": "en",
            "text": expect.like("5.1 Students are able to analyze, evaluate, and synthesize information for financial reporting."),
          },
          {
            "competency_framework": expect.like("Accounting Learning Outcomes"),
            "language": "en",
            "text": expect.like("6.1 Students are able to analyze, evaluate, and synthesize information to solve cost accounting problems."),
          },
          {

            "competency_framework": expect.like("Accounting Learning Outcomes"),
            "language": "en",
            "text": expect.like("7.1 Students are able to analyze information and apply tax principles to solve taxation problems."),
          },
          {
            "competency_framework": expect.like("Accounting Learning Outcomes"),
            "language": "en",
            "text": expect.like("8.1 Students are able to properly plan an audit and assess the financial statements for the risk of material misstatement due to errors for fraud."),
          },
          {
            "competency_framework": expect.like("Accounting Learning Outcomes"),
            "language": "en",
            "text": expect.like("9.1 Students are able to determine technological threats to accounting systems and identify applicable controls to mitigate risks."),
          },
          {
            "competency_framework": expect.like("Accounting Learning Outcomes"),
            "language": "en",
            "text": expect.like("10.1 Students are able to use applicable technology tools to evaluate and present accounting information."),
          },
          {
            "competency_framework": expect.like("Accounting Learning Outcomes"),
            "language": "en",
            "text": expect.like("11.1 Students are able to execute business processes involved in an accounting cycle essential to using integrated accounting software."),
          },
          {
            "competency_framework": expect.like("Accounting Learning Outcomes"),
            "language": "en",
            "text": expect.like("12.1 Students are able to use generalized audit software to simulate audit processes."),
          },
        ]
      );
    });
  });

  describe("Indiana State University", () => {
    // To do: fix LLM prompt for entity presence detection
    // to yield no competencies
    test.skip("Computer Science Program Learning Outcomes", async () => {
      const result = await extractCompetencies(
        "https://catalog.indstate.edu/preview_program.php?catoid=60&poid=10695&returnto=3288"
      );

      expect(result).toEqual([]);
    });
  });
});
