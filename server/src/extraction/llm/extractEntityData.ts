import {
  CatalogueType,
  CompetencyStructuredData,
  CourseStructuredData,
  LearningProgramStructuredData,
} from "@common/types";
import {
  ChatCompletionContentPart,
  ChatCompletionMessageParam,
} from "openai/resources/chat/completions";
import { DefaultLlmPageOptions } from ".";
import { assertArray, simpleToolCompletion } from "../../openai";
import { getCatalogueTypeDefinition } from "../catalogueTypes";

export const validCreditUnitTypes = [
  "AcademicYear",
  "CarnegieUnit",
  "CertificateCredit",
  "ClockHour",
  "CompetencyCredit",
  "ContactHour",
  "DegreeCredit",
  "DualCredit",
  "QuarterHour",
  "RequirementCredit",
  "SecondaryDiplomaCredit",
  "SemesterHour",
  "TimeBasedCredit",
  "TypeBasedCredit",
  "UNKNOWN",
];

const parseCreditValue = (credit: string | number | undefined) => {
  if (typeof credit === "string" && credit.trim().length) {
    return parseFloat(credit);
  }
  return undefined;
};

function processCourseField(key: string, value: any) {
  if (key === "course_credits_type" && value) {
    const creditType = String(value).trim();
    if (
      !creditType ||
      creditType.toUpperCase() === "UNKNOWN" ||
      !validCreditUnitTypes.includes(creditType)
    ) {
      return undefined;
    }
    return creditType;
  }

  if (
    key === "course_credits_min" ||
    key === "course_credits_max" ||
    key === "course_ceu_credits"
  ) {
    return parseCreditValue(value);
  }

  return value;
}

function processProgramField(key: string, value: any) {
  if (key === "program_credits") {
    return parseCreditValue(value);
  }
  return value;
}

export function processEntity(
  entity: Record<string, any>,
  catalogueType: CatalogueType
) {
  const entityDef = getCatalogueTypeDefinition(catalogueType);
  const processedEntity: Record<string, any> = {};

  for (const [key, value] of Object.entries(entity)) {
    if (typeof value === "string") {
      processedEntity[key] = value.trim();
    } else {
      processedEntity[key] = value;
    }
    switch (catalogueType) {
      case CatalogueType.COURSES:
        processedEntity[key] = processCourseField(key, value);
        break;
      case CatalogueType.LEARNING_PROGRAMS:
        processedEntity[key] = processProgramField(key, value);
        break;
    }

    if (
      !entityDef.properties[key]?.required &&
      (processedEntity[key] === "" || processedEntity[key] === undefined)
    ) {
      processedEntity[key] = undefined;
    }
  }

  if (catalogueType === CatalogueType.COURSES) {
    return processedEntity as CourseStructuredData;
  } else if (catalogueType === CatalogueType.LEARNING_PROGRAMS) {
    return processedEntity as LearningProgramStructuredData;
  } else if (catalogueType === CatalogueType.COMPETENCIES) {
    return processedEntity as CompetencyStructuredData;
  }

  return processedEntity;
}

export function getBasePrompt(catalogueType: CatalogueType): string {
  const entityDef = getCatalogueTypeDefinition(catalogueType);

  let prompt = `
We are looking for the following fields:
`;

  for (const [key, prop] of Object.entries(entityDef.properties)) {
    prompt += `
${key}: ${prop.description}${prop.required ? " (REQUIRED)" : ""}`;
  }

  return prompt;
}

export async function extractEntityData(
  options: DefaultLlmPageOptions,
  catalogueType: CatalogueType
): Promise<
  | CourseStructuredData[]
  | LearningProgramStructuredData[]
  | CompetencyStructuredData[]
> {
  const entityDef = getCatalogueTypeDefinition(catalogueType);
  const basePrompt = getBasePrompt(catalogueType);

  const additionalContext = options.additionalContext
    ? `
ADDITIONAL CONTEXT:

${options.additionalContext.message}

${(options.additionalContext.context ?? []).join("\n")}
`
    : "";

  const prompt = `
Your goal is to extract ${entityDef.name} data from this page.

${basePrompt}

${additionalContext}

PAGE URL:

${options.url}

SIMPLIFIED PAGE CONTENT:

${options.content}
`;

  const completionContent: ChatCompletionContentPart[] = [
    {
      type: "text",
      text: prompt,
    },
  ];

  if (options?.screenshot) {
    completionContent.push({
      type: "image_url",
      image_url: { url: `data:image/webp;base64,${options.screenshot}` },
    });
  }

  const messages: ChatCompletionMessageParam[] = [
    {
      role: "user",
      content: completionContent,
    },
  ];

  const entityProperties: Record<string, any> = {};
  const requiredProperties: string[] = [];

  for (const [key, prop] of Object.entries(entityDef.properties)) {
    if (
      key === `${entityDef.name}_credits_type` &&
      catalogueType === CatalogueType.COURSES
    ) {
      entityProperties[key] = {
        type: "string",
        enum: validCreditUnitTypes,
      };
    } else {
      entityProperties[key] = {
        type: "string",
      };
    }

    if (prop.required) {
      requiredProperties.push(key);
    }
  }

  const result = await simpleToolCompletion({
    messages,
    toolName: `${entityDef.name}_data`,
    parameters: {
      [`${entityDef.pluralName}`]: {
        type: "array",
        items: {
          type: "object",
          properties: entityProperties,
          required: requiredProperties,
        },
      },
    },
    requiredParameters: [`${entityDef.pluralName}`],
    logApiCall: options?.logApiCalls
      ? {
          extractionId: options.logApiCalls.extractionId,
          callSite: `extract${entityDef.name.charAt(0).toUpperCase() + entityDef.name.slice(1)}DataItem`,
        }
      : undefined,
  });

  if (!result || !result.toolCallArgs) {
    return [];
  }

  const entities = assertArray<Record<string, any>>(
    result.toolCallArgs,
    `${entityDef.pluralName}`
  );

  return entities
    .filter((entity) => requiredProperties.every((prop) => entity[prop]))
    .map((entity) => processEntity(entity, catalogueType));
}
