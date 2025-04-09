import { CatalogueType } from "../../../common/types";

export interface CatalogueTypeDefinition {
  name: string;
  pluralName: string;
  description: string;
  detailDescription: string;
  categoryDescription: string;
  linkDescription: string;

  /**
   * If specified it will tell the LLM what is
   * the desired output. Example values:
   * - 'An array of strings with all the animals mentioned in the page'
   * - 'An array of JSON objects having x, y, z attributes.'
   * 
   * If not specified, the LLM will be instructed
   * to give us structured output for the defined
   * data in the `properties` field.
   */
  desiredOutput?: string;

  /**
   * When set to true, we will ask the LLM for additional 
   * URLs that could indicate sub pages where we could find
   * entites when the page extracted does not yield any of 
   * the targeted entities.
   */
  exploreDuringExtraction?: boolean;

  /**
   * When set to true, filter the exploration URLs to
   * only include URLs that are on the same origin as the page.
   * This helps to avoid extracting URLs that are external
   * such as links to social media, external blogs,
   * our outside the catalogue.
   */
  exploreSameOrigin?: boolean

  /**
   * Textual prompt set to the LLM to yield additional URLs
   * from the page content.
   */
  explorationPrompt?: string;
  exampleIdentifier: string;
  exampleName: string;
  exampleDescription: string;
  properties: {
    [key: string]: {
      description: string;
      required: boolean;
    };
  };
  identifierProperty: string;
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
    identifierProperty: "course_id",
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
      "It has links to learning program category pages. For example, it might have a link to an 'Arts' category that will then have links to various art-related programs.",
    linkDescription:
      "It has links to the learning programs of an institution. For example, it links directly to a Bachelor of Science in Computer Science learning program, a Bachelor of Science in Nursing learning program, etc.",
    exampleIdentifier: "BSCS",
    exampleName: "Bachelor of Science in Computer Science",
    exampleDescription:
      "A comprehensive program that prepares students for careers in software development and computer systems.",
    identifierProperty: "learning_program_id",
    properties: {
      learning_program_id: {
        description:
          "code/identifier for the learning program. Unless it is clearly identified as such in the page, default to the name of the learning program.",
        required: true,
      },
      learning_program_name: {
        description:
          'name for the learning program (example: "Bachelor of Science in Computer Science")',
        required: true,
      },
      learning_program_description: {
        description: `the full description of the learning program.
           Pages often include other sections aside from the basic description, for example containing program requirements,
           restrictions, etc. We don't want any of that - we only want the program description (directly extracted from the page).
           If there are links, only extract the text.
          `,
        required: true,
      },
    },
  },
  [CatalogueType.COMPETENCIES]: {
    name: "skill, competency or learning outcome",
    pluralName: "skills, competencies or learning outcomes",
    description: "skills, competencies or learning outcomes",
    detailDescription:
      "It contains one or more competencies, skills or learning outcomes directly in the page.",
    categoryDescription:
      "It has links to skill areas, domains, or competency category pages.",
    linkDescription: "It has links to the competencies of an institution.",
    exampleIdentifier: "",
    exampleName: "Critical Thinking",
    exampleDescription:
      "The ability to analyze information objectively and make reasoned judgments.",
    identifierProperty: "competency_id",
    desiredOutput:
      'We are looking for a list of skills that are gained after taking the course described in the page. ' +
      'If found, take each item exactly as it is in the page and return them. Skip everything else, just the skill list.' +
      'Do not confuse skills with courses or tools or technologies used. Return the skills that result after the course is completed.' +
      'Do not return skills required for taking the course. Return only the skills that are gained after taking the course.',
    properties: {
      text: {
        description:
          'text of the skill item of the list (for example "Critical Thinking"). ' +
          'The information should be EXACTLY as in the page AND the FULL PHRASE. DO NOT break phrases. ',
        required: true,
      },
      competency_framework: {
        description:
          "The name of the encompassing or overarching skill or competency or learning program or course that will lead " +
          "to obtaining the skill or competency or learning outcome. " +
          "Usually this value is the same for the entire list but should be set " +
          "according to the hierarchy structure of the page. This is usually shorter. " +
          'Sometimes, this might contain descriptive language about the skill - we should only keep the ' +
          'name of the skill and trim phrases such as "competency" or "learning outcome".' +
          'This field should be in title case. If it contains roman numerals, they use use uppercase.',
        required: false,
      },
      language: {
        description:
          "ISO code of the language in which the name property is expressed. Examples - 'en' for English, 'es' for Spanish, 'de' for German, etc.",
        required: false,
      },
    },
    exploreDuringExtraction: true,
    exploreSameOrigin: true,
    explorationPrompt: 
      "In the page markdown given below, look for all links or URL like information " +
      "that point to pages with information about skills or learning outcomes or competencies obtained. " +
      "The link we are looking for is related to the course presented in the page, general links like navigation should be ignored. " +
      "IT IS IMPORTANT THAT THE LINK IS RELATED TO OUTCOMES FOR THE CURRENT COURSE, NOT OTHER COURSES OR PROGRAMS. " +
      "We are ONLY looking for links within the same domain as the page or relative to the page. " +
      "PAY ATTENTION to extract only the link and not markdown specific information like [link](url). " +
      "If there are no instances of links that CLEARLY point to skills or learning outcomes or competencies, yield an empty list.",
  },
};

export function getCatalogueTypeDefinition(
  catalogueType: CatalogueType
): CatalogueTypeDefinition {
  return catalogueTypes[catalogueType];
}
