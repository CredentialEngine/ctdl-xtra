import { describe, test } from "vitest";
import { assertExtraction, EXTRACTION_TIMEOUT } from "../..";
import {
  CatalogueType,
  LearningProgramStructuredData,
} from "../../../../common/types";

describe("ACALOG", { timeout: EXTRACTION_TIMEOUT }, () => {
  describe("Houston Community College", () => {
    test("Standard Learning Program", async () => {
      await assertExtraction<LearningProgramStructuredData>(
        "https://www.hccs.edu/programs/areas-of-study/liberal-arts--humanities/child-development/",
        [
          {
            learning_program_id: "Child Development",
            learning_program_name: "Child Development",
            learning_program_description:
              "The Child Development AAS Degree Program is designed to provide academic background and practical work experience necessary for successful care and guidance of young children. Our mission is to provide both the academic background and practical work experience that prepares early childhood educators in their work with individual young children and their diverse families in the 21st century.",
          },
        ],
        true,
        CatalogueType.LEARNING_PROGRAMS
      );
    });
  });

  describe("Ivy Tech Community College", () => {
    test("Standard Learning Program", async () => {
      await assertExtraction<LearningProgramStructuredData>(
        "https://catalog.ivytech.edu/preview_entity.php?catoid=9&ent_oid=1012&returnto=1039",
        [
          {
            learning_program_id: "Biotechnology",
            learning_program_name: "Biotechnology",
            learning_program_description:
              "The biotechnology program at Ivy Tech is taught by instructors with real-world experience. Students will use state-of-the-art laboratories that are equipped with instrumentation, supplies and equipment for an effective hands-on laboratory experience. Classes focus on teaching a variety of procedures necessary to execute laboratory projects assigned in the student’s chosen field. Students will spend a significant amount of class time working hands-on doing laboratory activities either by themselves or in small groups with the ability to have one-on-one time with the instructor.",
          },
        ],
        true,
        CatalogueType.LEARNING_PROGRAMS
      );
    });
  });

  describe("Indiana State University", () => {
    test("Standard Learning Program", async () => {
      await assertExtraction<LearningProgramStructuredData>(
        "https://catalog.indstate.edu/preview_program.php?catoid=60&poid=10822&returnto=3288",
        [
          {
            learning_program_id: "Kinesiology",
            learning_program_name: "Kinesiology",
            learning_program_description:
              "The Kinesiology major teaches students how the body functions and responds to exercise. Students also learn to develop, implement, and interpret fitness health assessments and maintenance programs for wide range of individuals and groups.",
          },
        ],
        true,
        CatalogueType.LEARNING_PROGRAMS
      );
    });
  });

  describe("Sinclair College", () => {
    test("Standard Learning Program", async () => {
      await assertExtraction<LearningProgramStructuredData>(
        "https://www.sinclair.edu/program/params/programCode/CS-S-AS/",
        [
          {
            learning_program_id: "Computer Science",
            learning_program_name: "Computer Science",
            learning_program_description:
              "Course work will focus on giving students a foundational knowledge of computer science concepts such as mathematics and programming skills. Furthermore, this Associate of Science degree will provide students a much needed transfer pathway to Computer Science Bachelor Degrees at four-year universities. As part of this degree program, students must complete the requirements of the Ohio Transfer 36 in order to graduate.",
          },
        ],
        true,
        CatalogueType.LEARNING_PROGRAMS
      );
    });
  });

  describe("Bergen Community College", () => {
    test("Standard Learning Program", async () => {
      await assertExtraction<LearningProgramStructuredData>(
        "https://catalog.bergen.edu/preview_program.php?catoid=7&poid=1008&returnto=304",
        [
          {
            learning_program_id: "AFA.THR",
            learning_program_name: "Theatre AFA",
            learning_program_description: `The Associate of Fine Arts (AFA) in Theatre concentrates student learning on theatre skills and knowledge, preparing students for further academic study of Theatre in either performance-based or technical-based areas - or both. The program will prepare them to compete a variety of theatre applications such as acting, directing, producing, stage management, lighting and scenic design and theatre education. Through applied and theoretical courses, students will develop the basic competencies of showmanship, knowledge acquisition, critical thinking, and analytic oral and written communication skills that potentially encompass a wide range of degree possibilities. The theatre course variety potentially includes performance, design, critical thinking and listening, and theoretical skill sets necessary for a pathway toward a bachelor’s degree in theatre arts.`,
          },
        ],
        true,
        CatalogueType.LEARNING_PROGRAMS
      );
    });
  });
});
