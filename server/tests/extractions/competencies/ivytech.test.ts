import { describe, test, expect } from "vitest";
import { extractCompetencies, EXTRACTION_TIMEOUT } from "../..";

describe("IvyTech", { timeout: EXTRACTION_TIMEOUT }, () => {
  describe("IvyTech CC", () => {
    test("Advanced Automation and Robotics Technology", async () => {
      const extractions = await extractCompetencies(
        "https://catalog.ivytech.edu/preview_course_nopop.php?catoid=9&coid=32130"
      );

      expect(extractions).arrayContaining([
        {
          "text": expect.like("Conduct assigned tasks in a safe and professional manner while working either independently or in small groups."),
          "competency_framework": expect.like("Advanced Automation and Robotics Technology"),
          "language": "en"
        },
        {
          "text": expect.like("Identify basic manufacturing processes and major types of production systems."),
          "competency_framework": expect.like("Advanced Automation and Robotics Technology"),
          "language": "en"
        },
        {
          "text": expect.like("Define common properties of industrial materials, their application, testing and enhancement."),
          "competency_framework": expect.like("Advanced Automation and Robotics Technology"),
          "language": "en"
        },
        {
          "text": expect.like("Describe the design, tooling and production aspects of manufacturing."),
          "competency_framework": expect.like("Advanced Automation and Robotics Technology"),
          "language": "en"
        },
        {
          "text": expect.like("Demonstrate a general knowledge of non-traditional manufacturing processes and automation."),
          "competency_framework": expect.like("Advanced Automation and Robotics Technology"),
          "language": "en"
        },
        {
          "text": expect.like("Explain the basic concepts of electrical, hydraulic and pneumatic power systems."),
          "competency_framework": expect.like("Advanced Automation and Robotics Technology"),
          "language": "en"
        },
        {
          "text": expect.like("Identify the common types and operation of bearing, coupling, belt, and chain systems."),
          "competency_framework": expect.like("Advanced Automation and Robotics Technology"),
          "language": "en"
        },
        {
          "text": expect.like("Identify physical principles including: force, torque, simple machines, and mechanical drives."),
          "competency_framework": expect.like("Advanced Automation and Robotics Technology"),
          "language": "en"
        },
        {
          "text": expect.like("Describe the basic concepts of machine control, machine automation, and electrical control."),
          "competency_framework": expect.like("Advanced Automation and Robotics Technology"),
          "language": "en"
        },
        {
          "text": expect.like("Communicate effectively using listening, speaking, reading, and writing skills."),
          "competency_framework": expect.like("Advanced Automation and Robotics Technology"),
          "language": "en"
        },
        {
          "text": expect.like("Use quantitative analytical skills to evaluate and process numerical data."),
          "competency_framework": expect.like("Advanced Automation and Robotics Technology"),
          "language": "en"
        },
        {
          "text": expect.like("Solve problems using critical and creative thinking skills."),
          "competency_framework": expect.like("Advanced Automation and Robotics Technology"),
          "language": "en"
        },
        {
          "text": expect.like("Utilizing and applying software where appropriate to the course."),
          "competency_framework": expect.like("Advanced Automation and Robotics Technology"),
          "language": "en"
        },
        {
          "text": expect.like("Attempt to earn a nationally recognized certification from MSSC Processes and Production and Maintenance Awareness."),
          "competency_framework": expect.like("Advanced Automation and Robotics Technology"),
          "language": "en"
        },
        {
          "text": expect.like("Demonstrate ability to read and interpret technical documents."),
          "competency_framework": expect.like("Advanced Automation and Robotics Technology"),
          "language": "en"
        },
        {
          "text": expect.like("Demonstrate ability to use various types of software applicable to course."),
          "competency_framework": expect.like("Advanced Automation and Robotics Technology"),
          "language": "en"
        }
      ]);
    });

    test("Health & Wellness Lifespan", async () => {
      const extractions = await extractCompetencies(
        "https://catalog.ivytech.edu/preview_course_nopop.php?catoid=9&coid=40320"
      );

      expect(extractions).arrayContaining(
        [
          {
            "text": expect.like("Identify therapeutic communication techniques that develop the nurse-patient relationship and promote intra- and interprofessional collaboration with health care teams."),
            "competency_framework": "Health & Wellness Lifespan",
            "language": "en"
          },
          {
            "text": expect.like("Demonstrate knowledge in assessment of patients across the lifespan, understanding normal and abnormal variations of findings while recognizing patients and their families as unique individuals with varied preferences, values, and needs."),
            "competency_framework": "Health & Wellness Lifespan",
            "language": "en"
          },
          {
            "text": expect.like("Discuss the impact of health promotion, disease prevention, and health disparities to promote healthy outcomes in a variety of diverse groups across the lifespan."),
            "competency_framework": "Health & Wellness Lifespan",
            "language": "en"
          },
          {
            "text": expect.like("Describe concepts utilized to promote diversity and a culture of caring and advocacy that demonstrates respect for individual patient preferences and respect for individual values and needs."),
            "competency_framework": "Health & Wellness Lifespan",
            "language": "en"
          },
          {
            "text": expect.like("Identify basic nutritional concepts of patients across the lifespan."),
            "competency_framework": "Health & Wellness Lifespan",
            "language": "en"
          },
          {
            "text": expect.like("Identify cognitive and psychosocial development across the lifespan and the nurse’s role when caring for patients with alterations in growth and development."),
            "competency_framework": "Health & Wellness Lifespan",
            "language": "en"
          },
          {
            "text": expect.like("Describe the role of the nurse as an educator, counselor, and facilitator in patient centered care."),
            "competency_framework": "Health & Wellness Lifespan",
            "language": "en"
          },
          {
            "text": expect.like("Demonstrate knowledge of factors that affect patient mobility and interventions that promote safe patient handling and movement across the life span."),
            "competency_framework": "Health & Wellness Lifespan",
            "language": "en"
          }
        ]
      );
    });
  });
});
