import { describe, test } from "vitest";
import { assertExtraction, EXTRACTION_TIMEOUT } from "../..";
import {
  CatalogueType,
  LearningProgramStructuredData,
} from "../../../../common/types";

describe("Other / Unknown", { timeout: EXTRACTION_TIMEOUT }, () => {
  describe("Rio Salado College", () => {
    test("Standard Learning Program", async () => {
      await assertExtraction<LearningProgramStructuredData>(
        "https://www.riosalado.edu/degrees-certificates/behavioral-science-and-human-services/firearms-5971n-ccl",
        [
          {
            learning_program_id: "5971N",
            learning_program_name: "Firearms",
            learning_program_description: `The Certificate of Completion (CCL) in Firearms program is designed to provide students with the training required for firearms qualification. Courses will cover firearms safety and nomenclature, care and cleaning of firearms and basic firearms usage techniques, as well as ammunition procedures, shooting positions, and qualification course experience.`,
          },
        ],
        true,
        CatalogueType.LEARNING_PROGRAMS
      );
    });
  });

  describe("Camden County College", () => {
    test("Standard Learning Program", async () => {
      await assertExtraction<LearningProgramStructuredData>(
        "https://www.camdencc.edu/program/carpentry-technology/",
        [
          {
            learning_program_id: "Carpentry Technology",
            learning_program_name: "Carpentry Technology",
            learning_program_description: `This program offers both a hands-on and textbook instruction, which requires problem solving and logical thinking skills. All phases of residential carpentry are addressed. Units included are print drawing/reading, estimation time/material, frame construction, rooﬁng/ siding, drywall and ﬁnish carpentry. Graduates are limited only by their own inventiveness. Any one or part of one unit covered during this program could be expanded into a career. Planning, estimation, drafting, framing, siding/rooﬁng, drywall installation, trim/cabinet installation, painting, building supply or hardware store person are but a few possibilities.`,
          },
        ],
        true,
        CatalogueType.LEARNING_PROGRAMS
      );
    });
  });

  describe("Mercer County Community College", () => {
    test("Standard Learning Program", async () => {
      await assertExtraction<LearningProgramStructuredData>(
        "https://catalog.mccc.edu/programs/BUS.STUD.ENTR.AAS",
        [
          {
            learning_program_id: "BUS.STUD.ENTR.AAS",
            learning_program_name: "Business Studies - Entrepreneurship",
            learning_program_description: `Business Studies, a career and non-transferable degree program, provides opportunities for students to prepare for a wide variety of careers in business. Students have the option of pursuing a general degree in Business Studies or selecting one of four concentrations, each comprised of 15 credits and designed to prepare students for specialty areas: Business Systems, Entrepreneurship, Management, Software Professional. Students should contact the program coordinator for advisement.`,
          },
        ],
        true,
        CatalogueType.LEARNING_PROGRAMS
      );
    });
  });

  describe("Passaic County Community College", () => {
    test("Standard Learning Program", async () => {
      await assertExtraction<LearningProgramStructuredData>(
        "https://catalog.pccc.edu/program/136/",
        [
          {
            learning_program_id: "Fire Science Technology",
            learning_program_name: "Fire Science Technology",
            learning_program_description: `This Degree is for those students seeking positions as fire protection and prevention specialists, municipal public safety officers, arson investigators, industrial safety inspectors, or fire insurance and fire suppression system salespersons. This degree is also intended for those who seek advancement within their careers in the fire service.`,
          },
        ],
        true,
        CatalogueType.LEARNING_PROGRAMS
      );
    });
  });

  describe("Quinsigamond Community College", () => {
    test("Standard Learning Program", async () => {
      await assertExtraction<LearningProgramStructuredData>(
        "https://www.qcc.edu/healthcare/radiologic-technology",
        [
          {
            learning_program_id: "Radiologic Technology",
            learning_program_name: "Radiologic Technology",
            learning_program_description: `Join the healthcare field with a degree in Radiologic Technology. Learn the basics of medical imaging, patient care, radiation safety and advancing medical imaging technologies through real world hands on training supported by technologists working in the field.`,
          },
        ],
        true,
        CatalogueType.LEARNING_PROGRAMS
      );
    });
  });

  describe("Rasmussen University", () => {
    test("Standard Learning Program", async () => {
      await assertExtraction<LearningProgramStructuredData>(
        "https://www.rasmussen.edu/degrees/technology/it-management/",
        [
          {
            learning_program_id: "Information Technology Management",
            learning_program_name: "Information Technology Management",
            learning_program_description: `The most valued leaders in the digital economy are those who lead by innovation. Our Bachelor's of Information Technology online provides you with advanced technical and analytical skills, leadership, project management and team management needed to be influential in this forward-looking field. Our online Bachelor’s degree-completion program allows you to train and gain business skills employers seek. It’s knowledge you get firsthand from our real-world projects.`,
          },
        ],
        true,
        CatalogueType.LEARNING_PROGRAMS
      );
    });
  });

  describe("Capella University", () => {
    test("Standard Learning Program", async () => {
      await assertExtraction<LearningProgramStructuredData>(
        "https://www.capella.edu/online-education-degrees/ms-education-program/masters-early-childhood-education-studies/",
        [
          {
            learning_program_id: "Early Childhood Education Studies",
            learning_program_name: "Early Childhood Education Studies",
            learning_program_description: `You can help make a meaningful difference in children’s lives. A deeper understanding of their early development can give you the key to support their growth and well-being in a changing world. The online MS in Education, Early Childhood Education Studies from Capella University is a way to establish these vital skills. You’ll develop an advanced understanding of how young children learn, what exceptional children need, and how family relationships play a role in childhood education. This degree program can prepare you for a variety of professional roles in the diverse field of early childhood education.`,
          },
        ],
        true,
        CatalogueType.LEARNING_PROGRAMS
      );
    });
  });
});
