import {
  ChatCompletionContentPart,
  ChatCompletionMessageParam,
} from "openai/resources/chat/completions";
import { DefaultLlmPageOptions, MD_START, MD_END } from ".";
import { ProviderModel } from "../../../../common/types";
import { structuredCompletion } from "../../openai";
import { CatalogueTypeDefinition } from "../catalogueTypes";

/**
 * Determines if an entity is present on a page based on the entity's presencePrompt.
 * This function is used to check if a page contains the expected entity before attempting extraction.
 * 
 * @param options - The page options containing URL, content, and screenshot
 * @param entityDef - The entity definition containing the presencePrompt
 * @returns A promise that resolves to an object containing the prompt used and whether the entity is present
 */
export async function determinePresenceOfEntity(
  options: DefaultLlmPageOptions,
  entityDef: CatalogueTypeDefinition
): Promise<{ prompt: string, present: boolean }> {
  if (!entityDef.presencePrompt) {
    return { prompt: "", present: true }; // If no presencePrompt is defined, assume entity is present
  }

  const prompt = `
${entityDef.presencePrompt}

PAGE:

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

  if (options.screenshot && !entityDef.skipScreenshot) {
    completionContent.push({
      type: "image_url",
      image_url: {
        url: `data:image/webp;base64,${options.screenshot}`,
      },
    });
  }

  const messages: ChatCompletionMessageParam[] = [
    {
      role: "user",
      content: completionContent,
    },
  ];

  const model = entityDef.model || ProviderModel.Gpt5;

  type PresenceCompletion = { present: boolean; explanation: string };

  const requestOptions: Parameters<
    typeof structuredCompletion<PresenceCompletion>
  >[0] = {
    messages,
    model,
    schema: {
      type: "object",
      additionalProperties: false,
      properties: {
        present: {
          type: "boolean",
          description: "Whether the entity is present on the page"
        },
        explanation: {
          type: "string",
          description: "Explanation of why the entity is or is not present"
        }
      },
      required: ["present", "explanation"],
    },
    logApiCall: options?.logApiCalls
      ? {
          extractionId: options.logApiCalls.extractionId,
          callSite: "determinePresenceOfEntity",
        }
      : undefined,
  };

  if (model !== ProviderModel.Gpt5) {
    requestOptions.top_p = 0.3;
  }

  const result = await structuredCompletion<PresenceCompletion>(requestOptions);

  if (!result || !result.result || typeof result.result.present !== 'boolean') {
    return { prompt, present: false };
  }

  return { 
    prompt, 
    present: result.result.present 
  };
} 