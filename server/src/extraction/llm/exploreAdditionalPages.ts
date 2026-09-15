import { URL } from "url";

import {
  dedupUrls,
  DefaultLlmPageOptions,
  filterUrlsByOrigin,
  MD_END,
  MD_START,
  userPageMessage,
} from ".";
import { CatalogueType, ProviderModel } from "../../../../common/types";
import { structuredCompletion } from "../../llm/LLMProviderApi";
import getLogger from "../../logging";
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

  const messages = [userPageMessage(prompt)];

  const model =
    options.modelOverride ?? entityDef.model ?? ProviderModel.Gpt5;

  const result = await structuredCompletion({
    messages,
    model,
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
          datasetId: options.logApiCalls.datasetId,
          crawlPageId: options.logApiCalls.crawlPageId,
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
