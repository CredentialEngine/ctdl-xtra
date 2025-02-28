import { CatalogueType } from "@common/types";
import {
  ChatCompletionContentPart,
  ChatCompletionMessageParam,
} from "openai/resources/chat/completions";
import { DefaultLlmPageOptions } from ".";
import { assertStringEnum, simpleToolCompletion } from "../../openai";
import { catalogueTypes } from "../catalogueTypes";

export async function detectCatalogueType(
  defaultOptions: DefaultLlmPageOptions
) {
  const entityDescriptions = Object.entries(catalogueTypes)
    .map(
      ([type, definition]) =>
        `${type}: It has links or details about the ${definition.description}.`
    )
    .join("\n");

  const prompt = `
  You are an agent in a system that autonomously scrapes educational data from the internet.

  For this task, you're being given the content of a web page that we believe is the index for
  a collection of pages (a catalogue), all of which correspond to a specific type of educational data.

  Your goal is to identify the primary type of educational data that features in the page.

  In order to successfully identify it, follow these instructions:

  1. Walk through the content in the page, step by step, trying to identify the main content section.
  2. In order to do that, note that things like navigation menus, headers, footers, sidebars and
     such might also show up in the page. You can use those pieces as hints and context data,
     but you're looking for the main content section.
  3. Take into account both the URLs and the text content of the links when you find some that
     may help you make a decision.
  4. Look at the screenshot, if one is provided, to get a better understanding of the page.

  CATALOGUE TYPES
  ==========

  ${entityDescriptions}

  IMPORTANT
  =========
  - only submit ONE tool call. There is ONE primary content type in the page.

  URL: ${defaultOptions.url}

  PAGE CONTENT
  ============

  ${defaultOptions.content}
`;

  console.log(prompt);

  const completionContent: ChatCompletionContentPart[] = [
    {
      type: "text",
      text: prompt,
    },
  ];

  if (defaultOptions.screenshot) {
    completionContent.push({
      type: "image_url",
      image_url: {
        url: `data:image/webp;base64,${defaultOptions.screenshot}`,
      },
    });
  }

  const messages: ChatCompletionMessageParam[] = [
    {
      role: "user",
      content: completionContent,
    },
  ];

  const result = await simpleToolCompletion({
    messages,
    toolName: "data_type",
    parameters: {
      catalogue_type: {
        type: "string",
        enum: Object.values(CatalogueType),
      },
    },
    logApiCall: defaultOptions?.logApiCalls
      ? {
          extractionId: defaultOptions.logApiCalls.extractionId,
          callSite: "detectCatalogueType",
        }
      : undefined,
  });

  if (!result?.toolCallArgs?.catalogue_type) {
    return null;
  }

  const catalogueType = assertStringEnum(
    result.toolCallArgs,
    "catalogue_type",
    Object.values(CatalogueType)
  );

  return catalogueType;
}
