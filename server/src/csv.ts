import {
  CatalogueType,
  CourseStructuredData,
  LearningProgramStructuredData,
} from "@common/types";
import { format } from "fast-csv";
import { Transform } from "stream";
import { findDataItems } from "./data/datasets";
import { findExtractionById } from "./data/extractions";

/*
  Ref.
  https://docs.google.com/spreadsheets/d/1o50bQ7rhqc1m38a-ZYZBEjz7MQDMt6MiDyQIwvQn2MI
  https://docs.google.com/spreadsheets/d/182TnqnwLzbw0ETIxV2U0KcMvRPqD1q2jwQksNYc4gPo
  https://github.com/CredentialEngine/ai-course-crawler/issues/20

  Order doesn't matter for the fields - what's important is the header name.

  Required fields:

  - External Identifier = Course number/ID
  - Coded Notation = Couse number/ID
  - Learning Type = Course?
  - Learning Opportunity Name = Course Name (e.g., Financial Literacy)
  - Description
  - Language = English
  - Life Cycle Status Type = Active
  - In Catalog = URL for the course catalog page or URL for the Course

  Expected fields:

  - Credit Unit Value = Enter number of either credit units awarded for college credit or continuing education units for successful completion of the learning opportunity or assessment. (e.g. for Financial Literacy the Credit Unit Value = 10
  - Credit Unity Type = Contact Hour (https://credreg.net/ctdl/terms/lifeCycleStatusType#CreditUnit)
  - ConditionProfile: Description = Entrance Requirements

*/

const noCreditUnitTypeDescription =
  "This has credit value, but the type cannot be determined";

function getCourseRow(
  item: Awaited<ReturnType<typeof findDataItems>>["items"][number],
  textVerificationAverage: number,
  textVerificationDetails: string
) {
  const structuredData = item.structuredData as CourseStructuredData;
  const creditRange =
    structuredData.course_credits_max &&
    structuredData.course_credits_min &&
    structuredData.course_credits_max > structuredData.course_credits_min;

  return {
    "External Identifier": structuredData.course_id,
    "Coded Notation": structuredData.course_id,
    "Learning Type": "Course",
    "Learning Opportunity Name": structuredData.course_name,
    Description: structuredData.course_description,
    Language: "English",
    "Life Cycle Status Type": "Active",
    "In Catalog": item.url,
    "Credit Unit Value": structuredData.course_credits_min,
    "Credit Unit Max Value": creditRange
      ? structuredData.course_credits_max
      : undefined,
    "Credit Unit Type": structuredData.course_credits_type,
    "Credit Unit Type Description": structuredData.course_credits_type
      ? undefined
      : noCreditUnitTypeDescription,
    "Text Verification Average": (textVerificationAverage * 100).toFixed(2),
    "Text Verification Details": textVerificationDetails,
    "ConditionProfile: External Identifier": structuredData.course_id,
    "ConditionProfile: Type": "Requires",
    "ConditionProfile: Name": "Prerequisites",
    "ConditionProfile: Description": structuredData.course_prerequisites,
  };
}

function getLearningProgramRow(
  item: Awaited<ReturnType<typeof findDataItems>>["items"][number],
  textVerificationAverage: number,
  textVerificationDetails: string
) {
  // columns are:
  // External Identifier,	Learning Type,	Learning Opportunity Name,	Description	Subject Webpage,	Life Cycle, Status, Type,	Language,	Available Online At
  // example row:
  // Academic Curriculum	Learning Program	Academic Curriculum	The Associate in Arts and the Associate in Science degrees can give you a good start before transferring to a four-year university.	https://www.hccs.edu/programs/areas-of-study/academic-curriculum/	Active	English	https://www.hccs.edu/programs/areas-of-study/academic-curriculum/

  const structuredData = item.structuredData as LearningProgramStructuredData;
  return {
    "External Identifier": structuredData.learning_program_id,
    "Learning Type": "Learning Program",
    "Learning Opportunity Name": structuredData.learning_program_name,
    Description: structuredData.learning_program_description,
    "Subject Webpage": item.url,
    "Life Cycle Status Type": "Active",
    Language: "English",
    "Available Online At": item.url,
    "Text Verification Average": (textVerificationAverage * 100).toFixed(2),
    "Text Verification Details": textVerificationDetails,
  };
}

function getCompetencyRow(
  item: Awaited<ReturnType<typeof findDataItems>>["items"][number],
  textVerificationAverage: number,
  textVerificationDetails: string
) {
  throw new Error("Not implemented");
}

function getBulkUploadTemplateRow(
  item: Awaited<ReturnType<typeof findDataItems>>["items"][number],
  catalogueType: CatalogueType
) {
  const textInclusion = item.textInclusion;
  let textVerificationAverage = 0;
  let textVerificationDetails = "";

  if (textInclusion) {
    const textVerificationFields = Object.keys(textInclusion);
    textVerificationAverage =
      textVerificationFields.length > 0
        ? textVerificationFields.reduce(
            (sum, field) => sum + (textInclusion[field]?.full ? 1 : 0),
            0
          ) / textVerificationFields.length
        : 0;
    textVerificationDetails = textVerificationFields
      .map(
        (field) =>
          `${field}: ${textInclusion[field]?.full ? "Present" : "Not present"}`
      )
      .join("\n");
  }

  if (catalogueType === CatalogueType.COURSES) {
    return getCourseRow(item, textVerificationAverage, textVerificationDetails);
  } else if (catalogueType === CatalogueType.LEARNING_PROGRAMS) {
    return getLearningProgramRow(
      item,
      textVerificationAverage,
      textVerificationDetails
    );
  } else if (catalogueType === CatalogueType.COMPETENCIES) {
    return getCompetencyRow(
      item,
      textVerificationAverage,
      textVerificationDetails
    );
  } else {
    throw new Error(`Unknown catalogue type: ${catalogueType}`);
  }
}

async function buildCsv(csvStream: Transform, extractionId: number) {
  try {
    let offset = 0;
    let limit = 100;

    while (true) {
      const extraction = await findExtractionById(extractionId);
      if (!extraction) {
        throw new Error("Extraction not found");
      }

      const { items } = await findDataItems(extractionId, limit, offset, true);
      if (!items.length) {
        break;
      }
      for (const item of items) {
        csvStream.write(
          getBulkUploadTemplateRow(
            item,
            extraction.recipe.catalogue.catalogueType as CatalogueType
          )
        );
      }
      offset += limit;
    }

    csvStream.end();
  } catch (err) {
    csvStream.emit("error", err);
  } finally {
    csvStream.end();
  }
}

export function streamCsv(extractionId: number) {
  const csvStream = format({ headers: true });
  buildCsv(csvStream, extractionId);
  return csvStream;
}
