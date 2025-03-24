import { describe, test } from "vitest";
import { assertExtraction, EXTRACTION_TIMEOUT } from "../..";

describe("ACALOG", { timeout: EXTRACTION_TIMEOUT }, () => {
  describe("Ivy Tech Community College", () => {
    test("Course with text prerequisites", async () => {
      await assertExtraction(
        "https://catalog.ivytech.edu/preview_course_nopop.php?catoid=7&coid=23627",
        [
          {
            course_id: "AGRI 112",
            course_name: "Fundamentals of Horticulture",
            course_description:
              "Examines the biology and technology involved in the production, storage, processing, and marketing of horticultural plants and products. Laboratories include experiments demonstrating both the theoretical and practical aspects of horticultural plant growth and development.",
            course_credits_min: 3,
            course_credits_max: 3,
            course_credits_type: undefined,
            course_prerequisites:
              "Demonstrated readiness for college-level English; and Demonstrated readiness for QUANT, TECH, or STEM Path Math Ready.",
          },
        ]
      );
    });

    test("Course with course prerequisites", async () => {
      await assertExtraction(
        "https://catalog.ivytech.edu/preview_course_nopop.php?catoid=9&coid=34237",
        [
          {
            course_id: "VISC 206",
            course_name: "Interdisciplinary Studies",
            course_description:
              "Offers students the opportunity to complete selected projects while working in a team environment with students of other disciplines. Simulates situations found in industry.",
            course_prerequisites:
              "VISC 210 - Web Design I or VISC 217 - Graphic Design II or PHOT 209 - Studio Lighting or VIDT 202 - Studio and Field Production II",
            course_credits_min: 3,
            course_credits_max: 3,
            course_credits_type: undefined,
          },
        ]
      );
    });
  });

  describe("Syracuse University", () => {
    test("No prerequisites", async () => {
      await assertExtraction(
        "http://coursecatalog.syr.edu/preview_course_nopop.php?catoid=38&coid=257941",
        [
          {
            course_id: "EAR 225",
            course_name: "Volcanoes and Earthquakes",
            course_description:
              "Examination of the geologic nature of volcanoes and earthquakes as they are related to plate tectonic activity in the Earth. Discussion of related societal hazards.",
            course_credits_min: 3,
            course_credits_max: 3,
            course_credits_type: undefined,
          },
        ]
      );
    });

    test("Single prerequisite", async () => {
      await assertExtraction(
        "http://coursecatalog.syr.edu/preview_course_nopop.php?catoid=38&coid=258319",
        [
          {
            course_id: "FAS 223",
            course_name: "Fashion Skills and Techniques IV",
            course_description:
              "Interpretation of advanced design concepts, using pattern making and elementary draping together as a system in the creation of shape and volume in garments.",
            course_prerequisites: "FAS 222",
            course_credits_min: 3,
            course_credits_max: 3,
            course_credits_type: undefined,
          },
        ]
      );
    });
  });

  describe("University of Pittsburgh", () => {
    test("No prerequisites", async () => {
      await assertExtraction(
        "https://catalog.upp.pitt.edu/preview_course.php?catoid=225&coid=1219821",
        [
          {
            course_id: "AFRCNA 1415",
            course_name: "RELIGION AND RACE",
            course_description:
              "This course examines the intersections of religion, race, and racism. Recently, scholars of religion have demonstrated that religious identities are often racialized as well. In this course, we will discover that religion and race are both modern categories rooted in post-enlightenment ideas about what it means to be human. We will see how the establishment of these religious and racial categories led to new hierarchies and inequalities. We will discuss how post-enlightenment thinkers linked religion and race, and how their ideas played a role in European imperialism. We will also investigate how the discipline of religious studies has developed its analytical tools with a racialized understanding of religion. The course will examine case studies in which religion has been racialized, and consider the political ramifications of these examples. In particular, we will think about the impact of white supremacy on black religion in the united states, the complicated relationship between antisemitism and Islamophobia, and contemporary Islamophobia in the US. Finally, we will explore the possibilities of anti-racism through faith-based scholarship and activism.",
            course_credits_min: 3,
            course_credits_max: 3,
            course_credits_type: undefined,
          },
        ]
      );
    });

    test("Prerequisites described as requirements", async () => {
      await assertExtraction(
        "https://catalog.upp.pitt.edu/preview_course.php?catoid=225&coid=1226408",
        [
          {
            course_id: "VIET 0102",
            course_name: "VIETNAMESE 2",
            course_description:
              "At the end of the second term of the first year of study the student should be able to produce all the significant sound patterns of the language, to recognize and use the major grammatical structures within a limited core vocabulary. The student should be able a) to engage in simple conversations with native speakers about a limited number of everyday situations and b) to read and write simple material related to the situations presented.",
            course_prerequisites:
              "LING 0581 or VIET 0101; MIN GRADE: 'C' FOR LISTED COURSES",
            course_credits_min: 4,
            course_credits_max: 4,
            course_credits_type: undefined,
          },
        ]
      );
    });
  });

  describe("Houston Community College", () => {
    test("Course with CEUs and decimal places", async () => {
      await assertExtraction(
        "https://catalog.hccs.edu/preview_course_nopop.php?catoid=21&coid=38020",
        /*
        MDCA 1048 - Pharmacology & Administration of Medications
Credits: 0

Instruction in concepts and application of pharmacological principles. Focuses on drug classifications, principles and procedures of medication administration, mathematical systems and conversions, calculation of drug problems, and medico-legal responsibilities of the medical assistant.

9.6 CEUs
*/
        [
          {
            course_id: "MDCA 1048",
            course_name: "Pharmacology & Administration of Medications",
            course_description:
              "Instruction in concepts and application of pharmacological principles. Focuses on drug classifications, principles and procedures of medication administration, mathematical systems and conversions, calculation of drug problems, and medico-legal responsibilities of the medical assistant.",
            course_credits_min: undefined,
            course_credits_max: undefined,
            course_ceu_credits: 9.6,
            course_credits_type: undefined,
          },
        ]
      );
    });
  });

  describe("Indiana State University", () => {
    test("Course with hallucinated description", async () => {
      await assertExtraction(
        "https://catalog.indstate.edu/preview_course.php?catoid=60&coid=139879",
        [
          {
            course_id: "SOC 220",
            course_name: "Contemporary Social Problems",
            course_description:
              "Problems of social and individual maladjustment, the causes of maladjustment, and the attempted and planned efforts for the solution of these problems.",
            course_credits_min: 3,
            course_credits_max: 3,
            course_credits_type: undefined,
            course_ceu_credits: undefined,
          },
        ]
      );
    });
  });
});
