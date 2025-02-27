import { CatalogueType } from "@common/types";
import {
  ChatCompletionContentPart,
  ChatCompletionMessageParam,
} from "openai/resources/chat/completions";
import { DefaultLlmPageOptions } from ".";
import { simpleToolCompletion } from "../../openai";
import { getCatalogueTypeDefinition } from "../catalogueTypes";
import {
  getBasePrompt,
  processEntity,
  validCreditUnitTypes,
} from "./extractEntityData";

export async function focusedExtractEntityData(
  options: DefaultLlmPageOptions,
  entity: Record<string, any>,
  catalogueType: CatalogueType
) {
  const entityDef = getCatalogueTypeDefinition(catalogueType);
  const basePrompt = getBasePrompt(catalogueType);

  const prompt = `
Your goal is to extract ${entityDef.name} data from this page for one specific ${entityDef.name}.

In a previous step, we asked you to extract the data, but we noticed there was an issue
with the ${entityDef.name} data.

Note you must extract data for the ${entityDef.name} EXACTLY as it is in the page, without adding or
removing anything.

Your previous extraction (INCORRECT) was:

${JSON.stringify(entity)}

${basePrompt}

Pay attention to the page content and extract it correctly this time.

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
      [`${entityDef.name}`]: {
        type: "object",
        properties: entityProperties,
        required: requiredProperties,
      },
    },
    requiredParameters: [`${entityDef.name}`],
    logApiCall: options?.logApiCalls
      ? {
          extractionId: options.logApiCalls.extractionId,
          callSite: `extract${entityDef.name.charAt(0).toUpperCase() + entityDef.name.slice(1)}DataItem`,
        }
      : undefined,
  });

  const extractedEntity = result?.toolCallArgs?.[entityDef.name] as Record<
    string,
    any
  >;
  if (!extractedEntity) {
    return null;
  }
  return processEntity(extractedEntity, catalogueType);
}
