import {
  ChatCompletionContentPart,
  ChatCompletionMessageParam,
} from "openai/resources/chat/completions";
import { DefaultLlmPageOptions, MD_START, MD_END } from ".";
import {
  CatalogueType,
  CompetencyStructuredData,
  CourseStructuredData,
  LearningProgramStructuredData,
  ProviderModel,
} from "../../../../common/types";
import { assertArray, simpleToolCompletion, structuredCompletion } from "../../openai";
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
      !entityDef?.properties?.[key]?.required &&
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
  const promptOfRequiredFields = Object.entries(entityDef.properties)
    .map(([key, prop]) => `${key}: ${prop.description}${prop.required ? " (REQUIRED)" : ""}`)
    .join('\n');

  let prompt = entityDef.desiredOutput || '';
  if (entityDef.properties) {
    prompt += `\nWe are looking for the following fields:\n${promptOfRequiredFields}\n`;
  }

  return prompt;
}

type ExtractEntityDataReturnType = Promise<{
  /** LLM textual prompt used for the extraction */
  prompt: string, 

  /** Extracted structured data items (entities) */
  data: Array<
    | Record<string, any>
    | CourseStructuredData
    | LearningProgramStructuredData
    | CompetencyStructuredData>,
}>;

export async function extractEntityData(
  options: DefaultLlmPageOptions,
  catalogueType: CatalogueType,
  entity?: Record<string, any>
): ExtractEntityDataReturnType 
{
  const entityDef = getCatalogueTypeDefinition(catalogueType);
  const basePrompt = getBasePrompt(catalogueType);

  const additionalContext = options.additionalContext
    ? `
ADDITIONAL CONTEXT:

${options.additionalContext.message}

${(options.additionalContext.context ?? []).join("\n")}
`
    : "";

  const entityPrompt = entity
    ? `Your goal is to extract ${entityDef.name} data from this page for one specific ${entityDef.name}.

In a previous step, we asked you to extract the data, but we noticed there was an issue
with the ${entityDef.name} data.

Note you must extract data for the ${entityDef.name} EXACTLY as it is in the page, without adding or
removing anything. NEVER paraphrase or change the content unless requested.

Your previous extraction (INCORRECT) was:

${JSON.stringify(entity)}

Pay attention to the page content and extract it correctly this time.`
    : `Your goal is to extract ${entityDef.name} data from this page.
       Extract the data EXACTLY as it shows up in the page.
       NEVER paraphrase, rewrite or change content unless requested.`;

  const prompt = `
${entityPrompt}

${basePrompt}

${additionalContext}

PAGE URL:

${options.url}

SIMPLIFIED PAGE CONTENT:

${MD_START}
${options.content}
${MD_END}
`;

  const completionContent: ChatCompletionContentPart[] = [
    {
      type: "text",
      text: prompt,
    },
  ];

  if (!entityDef?.skipScreenshot && options?.screenshot) {
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
      catalogueType === CatalogueType.COURSES &&
      key.includes("credits_type")
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

  if (entityDef.schema) {
    const results = await structuredCompletion({
      messages,
      schema: entityDef.schema,
      model: entityDef.model || ProviderModel.Gpt4o,
    });

    if (!results.result) {
      return { prompt, data: [] };
    }

    const data = Array.isArray(results.result?.items)
      ? results.result.items.map((entity) => processEntity(entity, catalogueType))
      : [processEntity(results.result, catalogueType)];

    return { prompt, data };
  } else {
    const completionParameters = {
      messages,
      toolName: "result",
      model: entityDef.model || ProviderModel.Gpt4o,
      parameters: {
        items: {
          type: "array",
          items: {
            type: "object",
            properties: entityProperties,
            required: requiredProperties,
          },
        },
      },
      requiredParameters: ["items"],
      logApiCall: options?.logApiCalls
        ? {
            extractionId: options.logApiCalls.extractionId,
            callSite: "extractEntityData",
          }
        : undefined,
    };
  
    // @ts-ignore
    const result = await simpleToolCompletion(completionParameters);

    if (!result || !result.toolCallArgs) {
      return { prompt, data: [] };
    }

    const entities = assertArray<Record<string, any>>(
      result.toolCallArgs,
      "items"
    );

    const data = entities
      .filter((entity) => requiredProperties.every((prop) => entity[prop]))
      .map((entity) => processEntity(entity, catalogueType));

    return { prompt, data };
  }
}
