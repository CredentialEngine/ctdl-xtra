import { randomUUID } from "crypto";
import { format } from "fast-csv";
import { Transform } from "stream";
import {
  CatalogueType,
  CompetencyStructuredData,
  CourseStructuredData,
  CredentialStructuredData,
  LearningProgramStructuredData,
} from "../../common/types";
import { findDataItems, findDataItemsWithSameUrlAcrossExtractions } from "./data/datasets";
import { findAllLatestExtractionsForHostname, findExtractionById } from "./data/extractions";

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

const getRelatedCompetencyFrameworks = (
  relatedItems: Awaited<ReturnType<typeof findDataItemsWithSameUrlAcrossExtractions>>,
  state: Record<string, any>
) => {
  const competencies = relatedItems
    .filter((item) => item.catalogueType === CatalogueType.COMPETENCIES);
  const competenciesCSV = competencies.map(item => getCompetencyRow(item, 0, '', state))
    .flat();
  return competenciesCSV.filter(item => item["@type"] === "ceasn:CompetencyFramework");
}

function getCourseRow(
  item: Awaited<ReturnType<typeof findDataItems>>["items"][number],
  textVerificationAverage: number,
  textVerificationDetails: string,
  state: Record<string, any>
) {
  const structuredData = item.structuredData as CourseStructuredData;
  const creditRange =
    structuredData.course_credits_max &&
    structuredData.course_credits_min &&
    structuredData.course_credits_max > structuredData.course_credits_min;

  const relatedItems = (state?.relatedItems || []) as
    Awaited<ReturnType<typeof findDataItemsWithSameUrlAcrossExtractions>>;
  const competencyFrameworks = getRelatedCompetencyFrameworks(relatedItems, state);
  const [learningPrograms] = relatedItems.filter(item => item.catalogueType === CatalogueType.LEARNING_PROGRAMS) || [];
  
  let isPartOf = "";
  if (learningPrograms) {
    isPartOf = learningPrograms.uuid || '';
  }

  return {
    "UUID": item.uuid || '',
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
    "Teaches Competency Framework": competencyFrameworks.map(item => item["@id"]).join("|"),
    "Is Part Of": isPartOf,
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
  textVerificationDetails: string,
  state: Record<string, any>
) {
  // columns are:
  // External Identifier,	Learning Type,	Learning Opportunity Name,	Description	Subject Webpage,	Life Cycle, Status, Type,	Language,	Available Online At
  // example row:
  // Academic Curriculum	Learning Program	Academic Curriculum	The Associate in Arts and the Associate in Science degrees can give you a good start before transferring to a four-year university.	https://www.hccs.edu/programs/areas-of-study/academic-curriculum/	Active	English	https://www.hccs.edu/programs/areas-of-study/academic-curriculum/

  const relatedItems = (state?.relatedItems || []) as
    Awaited<ReturnType<typeof findDataItemsWithSameUrlAcrossExtractions>>;
  const courseRows = relatedItems
    .filter((item) => item.catalogueType === CatalogueType.COURSES)
    .map(item => getCourseRow(item, textVerificationAverage, textVerificationDetails, state))
    .flat();
  const courseIds = courseRows.map(item => item["External Identifier"]).join("|");
  const competencyFrameworks = getRelatedCompetencyFrameworks(relatedItems, state);

  const structuredData = item.structuredData as LearningProgramStructuredData;
  return {
    "UUID": item.uuid || '',
    "External Identifier": structuredData.learning_program_id,
    "Learning Type": "Learning Program",
    "Learning Opportunity Name": structuredData.learning_program_name,
    Description: structuredData.learning_program_description,
    "Subject Webpage": item.url,
    "Life Cycle Status Type": "Active",
    Language: "English",
    "Available Online At": item.url,
    "Has Part (External Identifier)": courseIds,
    "Has Part (UUID)": courseRows.map(item => item["UUID"]).join("|"),
    "Teaches Competency Framework": competencyFrameworks.map(item => item["@id"]).join("|"),
    "Text Verification Average": (textVerificationAverage * 100).toFixed(2),
    "Text Verification Details": textVerificationDetails,
  };
}

type Framework = { name: string; id: string };

function getCompetencyRow(
  item: Awaited<ReturnType<typeof findDataItems>>["items"][number],
  textVerificationAverage: number,
  textVerificationDetails: string,
  state: Record<string, any>
) {
  const entityData = item.structuredData as CompetencyStructuredData;
  const frameworks = state?.frameworks || [];

  const result = [];

  let framework: Framework = frameworks.find(
    (item: typeof framework) => item?.name === entityData.competency_framework
  );
  if (!framework) {
    framework = {
      name: entityData.competency_framework,
      id: item.uuid || '',
    };
    frameworks.push(framework);
    state.frameworks = frameworks;

    const frameworkItem = makeCompetencyRow(
      {
        text: framework.name,
        language: entityData.language,
        competency_framework: "",
        uuid: item.uuid || '',
      },
      { textVerificationAverage, textVerificationDetails }
    );
    result.push(frameworkItem);
  }

  const competencyItem = makeCompetencyRow(
    {
      text: entityData.text,
      language: entityData.language,
      competency_framework: framework.id,
      uuid: item.uuid || '',
    },
    { textVerificationAverage, textVerificationDetails },
    framework
  );
  result.push(competencyItem);
  return result;
}

function makeCompetencyRow(
  entity: CompetencyStructuredData,
  verification: {
    textVerificationAverage: number;
    textVerificationDetails: string;
  },
  parent?: Framework
) {
  const type = parent ? "ceasn:Competency" : "ceasn:CompetencyFramework";
  const id = parent ? randomUUID() : entity.uuid || '';
  const name = !parent ? entity.text : "";
  const text = parent ? entity.text : "";
  const description = parent
    ? ""
    : `These are the competencies associated with ${entity.text}`;
  const language = entity.language;
  const isPartOf = parent ? parent.id : "";
  const result = {
    "@type": type,
    "@id": id,
    "ceasn:name": name,
    "ceasn:competencyText": text,
    "ceasn:description": description,
    "ceasn:inLanguage": language,
    "ceasn:publisher": "",
    "ceasn:isPartOf": isPartOf,
  };

  return result;
}

function getCredentialRow(
  item: Awaited<ReturnType<typeof findDataItems>>["items"][number],
  textVerificationAverage: number,
  textVerificationDetails: string,
  state: Record<string, any>
) {
  const structuredData = item.structuredData as CredentialStructuredData;
  
  return {
    "External Identifier": item.uuid || '',
    "Credential Name": structuredData.credential_name,
    "Description": structuredData.credential_description,
    "Language": structuredData?.language || "English",
    "Credential Type": structuredData.credential_type || "Unknown",
    "In Catalog": item.url,
    "Text Verification Average": (textVerificationAverage * 100).toFixed(2),
    "Text Verification Details": textVerificationDetails,
  };
}

function getBulkUploadTemplateRow<T>(
  item: Awaited<ReturnType<typeof findDataItems>>["items"][number],
  catalogueType: CatalogueType,
  state: Record<string, any>
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
    return getCourseRow(item, textVerificationAverage, textVerificationDetails, state);
  } else if (catalogueType === CatalogueType.LEARNING_PROGRAMS) {
    return getLearningProgramRow(
      item,
      textVerificationAverage,
      textVerificationDetails,
      state
    );
  } else if (catalogueType === CatalogueType.COMPETENCIES) {
    return getCompetencyRow(
      item,
      textVerificationAverage,
      textVerificationDetails,
      state
    );
  } else if (catalogueType === CatalogueType.CREDENTIALS) {
    return getCredentialRow(
      item,
      textVerificationAverage,
      textVerificationDetails,
      state
    );
  } else {
    throw new Error(`Unknown catalogue type: ${catalogueType}`);
  }
}

const idColumns = {
  [CatalogueType.COURSES]: "course_id",
  [CatalogueType.LEARNING_PROGRAMS]: "learning_program_id",
  [CatalogueType.COMPETENCIES]: "competency_framework",
  [CatalogueType.CREDENTIALS]: "credential_id",
};

export async function buildCsv(csvStream: Transform, extractionId: number) {
  try {
    let offset = 0;
    let limit = 100;
    let state: Record<string, any> = {};

    const extraction = await findExtractionById(extractionId);
    if (!extraction) {
      throw new Error("Extraction not found");
    }

    const catalogueHostname = new URL(extraction?.recipe.url || "").hostname;
    const latestExtractions = await findAllLatestExtractionsForHostname(catalogueHostname);

    const idMap = new Map<string, number>();
    const idColumn =
      idColumns[extraction.recipe.catalogue.catalogueType as CatalogueType];

    while (true) {
      const { items } = await findDataItems(extractionId, limit, offset, true);
      if (!items.length) {
        break;
      }
      for (let item of items) {
        const itemSourceUrl = item.url;
        const latestExtractionIds = latestExtractions.map((extraction) => +extraction.id);
        const relatedItems = await findDataItemsWithSameUrlAcrossExtractions(latestExtractionIds, itemSourceUrl);
        const rowId: string | undefined = (item.structuredData as any)[
          idColumn
        ];
        if (rowId) {
          let rowNumber = idMap.get(rowId);
          if (rowNumber) {
            rowNumber += 1;
            item = {
              ...item,
              structuredData: {
                ...item.structuredData,
                [idColumn]: `${rowId}-${rowNumber}`,
                uuid: item.uuid || '',
              },
            };
          } else {
            rowNumber = 1;
          }
          idMap.set(rowId, rowNumber);
        }
        const records = getBulkUploadTemplateRow(
          item,
          extraction.recipe.catalogue.catalogueType as CatalogueType,
          {
            ...state,
            relatedItems,
          }
        );

        if (Array.isArray(records) && records?.length) {
          records.map((entry) => csvStream.write(entry));
        } else {
          csvStream.write(records);
        }
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
