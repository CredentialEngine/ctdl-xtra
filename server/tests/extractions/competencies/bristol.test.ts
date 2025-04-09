import { describe, test, expect } from "vitest";
import { extractCompetencies, EXTRACTION_TIMEOUT } from "../..";

describe("Bristol", { timeout: EXTRACTION_TIMEOUT }, () => {
  describe("Bristol Community College", () => {
    test("Competencies for Critical Thinking", async () => {
      const extractions = await extractCompetencies(
        "https://catalog.bristolcc.edu/critical-thinking"
      );
      expect(extractions).arrayContaining(
        [
          {
            "text": expect.like("Identify and summarize a problem or issue comprehensively, delivering relevant information needed for understanding."),
            "competency_framework": "Critical Thinking",
            "language": "en"
          },
          {
            "text": expect.like("State own and others' perspectives and limits of positions, as related to the problem/issue."),
            "competency_framework": "Critical Thinking",
            "language": "en"
          },
          {
            "text": expect.like("Identify the key assumptions that underlie the issue."),
            "competency_framework": "Critical Thinking",
            "language": "en"
          },
          {
            "text": expect.like("Assess the quality of supporting data/evidence to support conclusions and implications or consequences."),
            "competency_framework": "Critical Thinking",
            "language": "en"
          },
          {
            "text": expect.like("Evaluate information and arguments for validity and sound reasoning."),
            "competency_framework": "Critical Thinking",
            "language": "en"
          }
        ]
      );
    });

    test("Competencies for Oral Communication", async () => {
      const extractions = await extractCompetencies(
        "https://catalog.bristolcc.edu/oral-communication"
      );

      expect(extractions).arrayContaining(
        [
          {
            "text": expect.like("Follow a consistent organizational pattern that presents ideas in a clear, articulate manner."),
            "competency_framework": "Oral Communication",
            "language": "en"
          },
          {
            "text": expect.like("Make language choices that are effective for the presentation and engage diverse audiences."),
            "competency_framework": "Oral Communication",
            "language": "en"
          },
          {
            "text": expect.like("Deliver presentations using appropriate posture, eye contact, vocal expression, and other body language."),
            "competency_framework": "Oral Communication",
            "language": "en"
          },
          {
            "text": expect.like("Use a variety of supporting materials that establish their credibility."),
            "competency_framework": "Oral Communication",
            "language": "en"
          },
          {
            "text": expect.like("Listen respectfully and critically to other speakers while focusing on their verbal and nonverbal messages."),
            "competency_framework": "Oral Communication",
            "language": "en"
          },
          {
            "text": expect.like("Evaluate, interpret, and critique a speaker's central message."),
            "competency_framework": "Oral Communication",
            "language": "en"
          }
        ]
      );
    });

    test("Quantitative and Symbolic Reasoning Competencies", async () => {
      const extractions = await extractCompetencies(
        "https://catalog.bristolcc.edu/quantitative-and-symbolic-reasoning"
      );

      expect(extractions).arrayContaining(
        [
          {
            "text": expect.like("Explain information represented in mathematical, symbolic, and/or graphical form."),
            "competency_framework": expect.like("Quantitative And Symbolic Reasoning"),
            "language": "en"
          },
          {
            "text": expect.like("Display information and data in graphs, charts, and other appropriate ways."),
            "competency_framework": expect.like("Quantitative And Symbolic Reasoning"),
            "language": "en"
          },
          {
            "text": expect.like("Perform mathematical calculations accurately to solve problems."),
            "competency_framework": expect.like("Quantitative And Symbolic Reasoning"),
            "language": "en"
          },
          {
            "text": expect.like("Identify, understand, and engage in mathematics as well as make well-founded mathematical judgments as a constructive, concerned, reflective citizen."),
            "competency_framework": expect.like("Quantitative And Symbolic Reasoning"),
            "language": "en"
          },
          {
            "text": expect.like("Use deductive thinking to solve mathematical problems and to determine the reasonableness of the results."),
            "competency_framework": expect.like("Quantitative And Symbolic Reasoning"),
            "language": "en"
          },
          {
            "text": expect.like("Compose explanations, using supporting mathematical language and symbolism from individually constructed data and/or graphs."),
            "competency_framework": expect.like("Quantitative And Symbolic Reasoning"),
            "language": "en"
          }
        ]
      );
    });
  });
});
