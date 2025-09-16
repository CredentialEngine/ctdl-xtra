import { URL } from "url";

import {
  ChatCompletionContentPart,
  ChatCompletionMessageParam,
} from "openai/resources/chat/completions";
import {
  dedupUrls,
  DefaultLlmPageOptions,
  filterUrlsByOrigin,
  MD_END,
  MD_START,
} from ".";
import { CatalogueType, ProviderModel } from "../../../../common/types";
import getLogger from "../../logging";
import { structuredCompletion } from "../../openai";
import { getCatalogueTypeDefinition } from "../catalogueTypes";

const logger = getLogger("extraction.llm.exploreAdditionalPages");

export async function exploreAdditionalPages(
  options: DefaultLlmPageOptions,
  catalogueType: CatalogueType
): Promise<{ prompt: string; data: string[] }> {
  const entityDef = getCatalogueTypeDefinition(catalogueType);
  if (!entityDef.exploreDuringExtraction) {
    throw new Error(
      `Entity of type ${entityDef.name} is not configured to allow exploration of additional content.`
    );
  }

  const prompt = `
${entityDef.explorationPrompt}

PAGE URL:

${options.url}

PAGE CONTENT:

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

  const messages: ChatCompletionMessageParam[] = [
    {
      role: "user",
      content: completionContent,
    },
  ];

  const result = await structuredCompletion({
    messages,
    model: entityDef.model || ProviderModel.Gpt5,
    schema: {
      type: "object",
      additionalProperties: false,
      properties: {
        items: {
          type: "array",
          items: {
            type: "string",
          },
        },
      },
      required: ["items"],
    },
    logApiCall: options?.logApiCalls
      ? {
          extractionId: options.logApiCalls.extractionId,
          callSite: "exploreAdditionalPages",
        }
      : undefined,
  });

  if (!result || !result.result?.items) {
    return { prompt, data: [] };
  }

  const rawUrls = (result.result?.items as string[]) || [];
  let urls = rawUrls
    .map((rawUrl) => {
      try {
        if (!options.content.includes(rawUrl)) {
          return null;
        }

        return new URL(rawUrl, options.url).href;
      } catch (e) {
        logger.warn(
          `Exception caught while joining ${rawUrl} with ${options.url}`,
          e
        );
        return null;
      }
    })
    .filter(Boolean) as string[];

  if (entityDef.exploreSameOrigin) {
    const hostname = new URL(options.url).hostname;
    urls = filterUrlsByOrigin(urls, hostname);
  }

  return { prompt, data: dedupUrls(urls) };
}
