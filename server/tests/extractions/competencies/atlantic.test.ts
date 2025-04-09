import { describe, test, expect } from "vitest";
import { extractCompetencies, EXTRACTION_TIMEOUT } from "../..";

describe("Atlantic Cape Community College", { timeout: EXTRACTION_TIMEOUT }, () => {
  describe("Atlantic Cape Community College", () => {
    test("ACE Personal Trainer with Fitness/Health Internship", async () => {
      const extractions = await extractCompetencies(
        "https://careertraining.atlanticcape.edu/training-programs/ace-personal-trainer-with-fitness-health-internship/"
      );
      expect(extractions).arrayContaining(
        [
          {
            "text": expect.like("Functional Training: Assessments, Programming, and Progressions for Posture, Movement, Core, Balance, and Flexibility"),
            "competency_framework": expect.like("ACE Personal Trainer with Fitness and Health Internship", 0.5),
            "language": "en"
          },
          {
            "text": expect.like("Professional and Legal Responsibilities, Scope of Practice, and Business Strategies for Personal Trainers"),
            "competency_framework": expect.like("ACE Personal Trainer with Fitness and Health Internship", 0.5),
            "language": "en"
          },
          {
            "text": expect.like("Special Exercise Programming Topics: Mind-body Exercise, Special Populations, and Exercise Implications of Common Musculoskeletal Injuries"),
            "competency_framework": expect.like("ACE Personal Trainer with Fitness and Health Internship", 0.5),
            "language": "en"
          },
          {
            "text": expect.like("Physiological Assessments"),
            "competency_framework": expect.like("ACE Personal Trainer with Fitness and Health Internship", 0.5),
            "language": "en"
          },
          {
            "text": expect.like("Cardiorespiratory Training: Programming and Progressions"),
            "competency_framework": expect.like("ACE Personal Trainer with Fitness and Health Internship", 0.5),
            "language": "en"
          },
          {
            "text": expect.like("Resistance Training: Programming and Progressions"),
            "competency_framework": expect.like("ACE Personal Trainer with Fitness and Health Internship", 0.5),
            "language": "en"
          }
        ]
      );
    });
  });
});
