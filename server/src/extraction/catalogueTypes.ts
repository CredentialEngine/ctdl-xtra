import { CatalogueType } from "@common/types";

export interface CatalogueTypeDefinition {
  name: string;
  pluralName: string;
  description: string;
  detailDescription: string;
  categoryDescription: string;
  linkDescription: string;
  exampleIdentifier: string;
  exampleName: string;
  exampleDescription: string;
  properties: {
    [key: string]: {
      description: string;
      required: boolean;
    };
  };
}

export const catalogueTypes: Record<CatalogueType, CatalogueTypeDefinition> = {
  [CatalogueType.COURSES]: {
    name: "course",
    pluralName: "courses",
    description: "educational courses offered by an institution",
    detailDescription:
      "It has details for the courses of an institution directly in the page.",
    categoryDescription:
      "It has links to programs, careers, degrees, or course category pages.",
    linkDescription: "It has links to the courses of an institution.",
    exampleIdentifier: "ACCT 101",
    exampleName: "Financial Accounting",
    exampleDescription:
      "A study of the underlying theory and application of financial accounting concepts.",
    properties: {
      course_id: {
        description: 'code/identifier for the course (example: "AGRI 101")',
        required: true,
      },
      course_name: {
        description: 'name for the course (for example "Landscape Design")',
        required: true,
      },
      course_description: {
        description:
          "the full description of the course. If there are links, only extract the text.",
        required: true,
      },
      course_prerequisites: {
        description: `if the text explicitly mentions any course prerequisite(s) or course requirements,
          extract them as is - the full text for prerequisites, as it may contain observations.
          (If there are links in the text, only extract the text without links.)
          - If it mentions course corequisites, leave blank.
          - If it mentions mutually exclusive courses, leave blank.
          - If it mentions courses that must be taken concurrently, leave blank.
          - Only extract the text if it's explicitly stated that the course has prerequisites/requirements.
          - Otherwise leave blank.
          `,
        required: false,
      },
      course_credits_min: {
        description: "min credit",
        required: false,
      },
      course_credits_max: {
        description:
          "max credit (if the page shows a range). If there is only a single credit information in the page, set it as the max.",
        required: false,
      },
      course_credits_type: {
        description: `type of credits, infer it from the page.
          IMPORTANT:
            - Only infer the type if it's CLEARLY stated in the page somewhere.
            - If you can't infer the type, set it as "UNKNOWN"
            - MUST BE either UNKNOWN or: AcademicYear, CarnegieUnit, CertificateCredit, ClockHour, CompetencyCredit, ContactHour, DegreeCredit, DualCredit, QuarterHour, RequirementCredit, SecondaryDiplomaCredit, SemesterHour, TimeBasedCredit, TypeBasedCredit, UNKNOWN
            - Sometimes the course has a special type of credit: CEUs (Continuing Education Units).
              (If you see "CEU" values in the page, that's the same as Continuing Education Units)
            - In that case, there's a separate field: course_ceu_credits.
            - A course may have both normal credits like the types we mentioned above, and CEUs.

          It is ok to have the course credits set to a number and the course credits type set to "UNKNOWN"
          if the content shows the credits value but doesn't mention the type.

          It is ok to have CEUs and course credits type set to "UNKNOWN" if the page doesn't mention the type
          but does mention CEUs.

          EVEN MORE IMPORTANT REGARDING COURSE CREDITS:

          IF THERE ARE NO CLEARLY STATED COURSE CREDITS INFORMATION, LEAVE ALL COURSE CREDITS FIELDS BLANK.
          ONLY INCLUDE COURSE CREDITS INFORMATION IF IT'S EXPLICITLY STATED IN THE PAGE!
        `,
        required: false,
      },
      course_ceu_credits: {
        description: "CEU credits",
        required: false,
      },
    },
  },
  [CatalogueType.LEARNING_PROGRAMS]: {
    name: "learning program",
    pluralName: "learning programs",
    description: "educational programs offered by an institution",
    detailDescription:
      "It has details for the learning programs of an institution directly in the page.",
    categoryDescription:
      "It has links to departments, schools, or learning program category pages.",
    linkDescription: "It has links to the learning programs of an institution.",
    exampleIdentifier: "BSCS",
    exampleName: "Bachelor of Science in Computer Science",
    exampleDescription:
      "A comprehensive program that prepares students for careers in software development and computer systems.",
    properties: {
      program_id: {
        description: 'code/identifier for the program (example: "BSCS")',
        required: true,
      },
      program_name: {
        description:
          'name for the program (for example "Bachelor of Science in Computer Science")',
        required: true,
      },
      program_description: {
        description:
          "the full description of the program. If there are links, only extract the text.",
        required: true,
      },
    },
  },
  [CatalogueType.COMPETENCIES]: {
    name: "competency",
    pluralName: "competencies",
    description: "skills and competencies defined by an institution",
    detailDescription:
      "It has details for the competencies of an institution directly in the page.",
    categoryDescription:
      "It has links to skill areas, domains, or competency category pages.",
    linkDescription: "It has links to the competencies of an institution.",
    exampleIdentifier: "COMP-101",
    exampleName: "Critical Thinking",
    exampleDescription:
      "The ability to analyze information objectively and make reasoned judgments.",
    properties: {
      competency_id: {
        description: 'code/identifier for the competency (example: "COMP-101")',
        required: true,
      },
      competency_name: {
        description:
          'name for the competency (for example "Critical Thinking")',
        required: true,
      },
      competency_description: {
        description:
          "the full description of the competency. If there are links, only extract the text.",
        required: true,
      },
    },
  },
};

export function getCatalogueTypeDefinition(
  catalogueType: CatalogueType
): CatalogueTypeDefinition {
  return catalogueTypes[catalogueType];
}
