import {
  ChatCompletionContentPart,
  ChatCompletionMessageParam,
} from "openai/resources/chat/completions";
import { DefaultLlmPageOptions } from ".";
import {
  CatalogueType,
  PageType,
  PaginationConfiguration,
  RecipeConfiguration,
  UrlPatternType,
} from "../../../../common/types";
import {
  BadToolCallResponseError,
  UnknownPaginationTypeError,
  assertBool,
  assertNumber,
  assertString,
  assertStringEnum,
  simpleToolCompletion,
} from "../../openai";
import { getCatalogueTypeDefinition } from "../catalogueTypes";
function getUrlPath(urlString: string): string {
  try {
    const url = new URL(urlString);
    return url.pathname;
  } catch {
    return urlString.startsWith("/") ? urlString : `/${urlString}`;
  }
}

export async function detectPagination(
  defaultOptions: DefaultLlmPageOptions & { catalogueType: CatalogueType },
  pageType: PageType,
  // @ts-ignore
  currentConfiguration?: RecipeConfiguration
): Promise<PaginationConfiguration | undefined> {
  const entity = getCatalogueTypeDefinition(defaultOptions.catalogueType);

  const prompt = `
Your goal is to determine whether the given web page is paginated, and how that pagination works.

If it does have pagination, figure out the pattern
(for example, a parameter for the page number or for the items offset).
Also if it does have pagination, determine the total number of pages.

<parameters>
is_paginated: true or false

IMPORTANT: be strict! If you don't spot something that is CLEARLY a pagination link for the page content,
assume this content isn't paginated and set is_paginated to false.

url_pattern_type: ONLY FILL THIS IN IF THE WEBSITE IS PAGINATED

- page_num: page number parameter
- offset: offset parameter
- other: other type of pattern

url_pattern: ONLY FILL THIS IN IF THE WEBSITE IS PAGINATED

the URL for pages, with the parameter replaced by {page_num} or {offset} (plus {limit} if relevant).
Example:
https://www.example.com/${entity.pluralName.toLowerCase()}.php?page={page_num}

total_pages: ONLY FILL THIS IN IF THE WEBSITE IS PAGINATED

other_explanation: ONLY FILL THIS IN IF THE WEBSITE IS PAGINATED AND THE PAGINATION TYPE IS OTHER

the reason why the pagination type is other and how you determined that.
</parameters>

<context>
The page is a ${entity.name} ${pageType} page.
</context>

<url>
${defaultOptions.url}
</url>

<website_content>
${defaultOptions.content}
</website_content>
`;

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
  const response = await simpleToolCompletion({
    messages,
    toolName: "submit_detected_pagination",
    parameters: {
      is_paginated: {
        type: "boolean",
      },
      url_pattern_type: {
        type: "string",
        enum: ["page_num", "offset", "other"],
      },
      url_pattern: {
        type: "string",
      },
      total_pages: {
        type: "number",
      },
      other_explanation: {
        type: "string",
      },
    },
    logApiCall: defaultOptions?.logApiCalls
      ? {
          extractionId: defaultOptions.logApiCalls.extractionId,
          callSite: "detectPagination",
        }
      : undefined,
  });
  if (!response?.toolCallArgs) {
    return undefined;
  }
  const toolCall = response.toolCallArgs;
  const hasPagination = assertBool(toolCall, "is_paginated");
  if (!hasPagination) {
    return undefined;
  }

  const urlPatternType = assertStringEnum(toolCall, "url_pattern_type", [
    "page_num",
    "offset",
    "other",
  ]);
  if (urlPatternType == "other") {
    // TODO: record this
    console.log(toolCall);
    throw new UnknownPaginationTypeError("The pagination type is unknown.");
  }
  const urlPattern = assertString(toolCall, "url_pattern");
  if (!urlPattern.startsWith("http")) {
    throw new BadToolCallResponseError(`Expected a URL pattern: ${urlPattern}`);
  }
  if (urlPatternType == "page_num" && !urlPattern.includes("{page_num}")) {
    throw new BadToolCallResponseError(`Couldn't find page_num: ${urlPattern}`);
  }
  if (urlPatternType == "offset" && !urlPattern.includes("{offset}")) {
    throw new BadToolCallResponseError(`Couldn't find offset: ${urlPattern}`);
  }

  const detectedPath = getUrlPath(urlPattern);
  if (!defaultOptions.content.includes(detectedPath)) {
    throw new BadToolCallResponseError(
      `Detected path ${detectedPath} not found in HTML`
    );
  }

  const totalPages = assertNumber(toolCall, "total_pages");
  return {
    urlPatternType: urlPatternType as UrlPatternType,
    urlPattern,
    totalPages,
  };
}
