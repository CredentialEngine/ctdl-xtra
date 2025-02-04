import { TextInclusion } from "@common/types";
import { format } from "fast-csv";
import { Transform } from "stream";
import { findDataItems } from "./data/datasets";

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

function getBulkUploadTemplateRow(
  item: Awaited<ReturnType<typeof findDataItems>>["items"][number]
) {
  const creditRange =
    item.structuredData.course_credits_max &&
    item.structuredData.course_credits_min &&
    item.structuredData.course_credits_max >
      item.structuredData.course_credits_min;

  const textInclusion = item.textInclusion;
  let textVerificationAverage = 0;
  let textVerificationDetails = "";

  if (textInclusion) {
    const textVerificationFields = Object.keys(textInclusion);
    textVerificationAverage =
      textVerificationFields.length > 0
        ? textVerificationFields.reduce(
            (sum, field) =>
              sum + (textInclusion[field as keyof TextInclusion]?.full ? 1 : 0),
            0
          ) / textVerificationFields.length
        : 0;
    textVerificationDetails = textVerificationFields
      .map(
        (field) =>
          `${field}: ${textInclusion[field as keyof TextInclusion]?.full ? "Present" : "Not present"}`
      )
      .join("\n");
  }

  return {
    "External Identifier": item.structuredData.course_id,
    "Coded Notation": item.structuredData.course_id,
    "Learning Type": "Course",
    "Learning Opportunity Name": item.structuredData.course_name,
    Description: item.structuredData.course_description,
    Language: "English",
    "Life Cycle Status Type": "Active",
    "In Catalog": item.url,
    "Credit Unit Value": item.structuredData.course_credits_min,
    "Credit Unit Max Value": creditRange
      ? item.structuredData.course_credits_max
      : undefined,
    "Credit Unit Type": item.structuredData.course_credits_type,
    "Credit Unit Type Description": item.structuredData.course_credits_type
      ? undefined
      : noCreditUnitTypeDescription,
    "Text Verification Average": (textVerificationAverage * 100).toFixed(2),
    "Text Verification Details": textVerificationDetails,
    "ConditionProfile: External Identifier": item.structuredData.course_id,
    "ConditionProfile: Type": "Requires",
    "ConditionProfile: Name": "Prerequisites",
    "ConditionProfile: Description": item.structuredData.course_prerequisites,
  };
}

async function buildCsv(csvStream: Transform, extractionId: number) {
  try {
    let offset = 0;
    let limit = 100;

    while (true) {
      const { items } = await findDataItems(extractionId, limit, offset, true);
      if (!items.length) {
        break;
      }
      for (const item of items) {
        csvStream.write(getBulkUploadTemplateRow(item));
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
