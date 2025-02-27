import {
  CatalogueType,
  PageType,
  PaginationConfiguration,
} from "@common/types";
import {
  ChatCompletionContentPart,
  ChatCompletionMessageParam,
} from "openai/resources/chat/completions";
import { DefaultLlmPageOptions } from ".";
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
  defaultOptions: DefaultLlmPageOptions,
  rootPageType: PageType
): Promise<PaginationConfiguration | undefined> {
  const catalogueType = defaultOptions.catalogueType || CatalogueType.COURSES;
  const entity = getCatalogueTypeDefinition(catalogueType);

  const pageTypeDescriptions = {
    [PageType.DETAIL_LINKS]:
      `It has links to ALL the ${entity.pluralName} for an institution. ` +
      `IF there is pagination, it is for pages of links to ${entity.pluralName}.`,
    [PageType.CATEGORY_LINKS]:
      `It has links to ${entity.categoryDescription.toLowerCase()} ` +
      `Those links are presumably extensive for ALL the categories in the institution. ` +
      `IF there is pagination, it is for pages of category links.`,
    [PageType.DETAIL]:
      `It has names/descriptions for ALL the ${entity.pluralName} for an institution. ` +
      `IF there is pagination, it is for pages of ${entity.name} descriptions.`,
  };

  const prompt = `
Your goal is to determine whether the given website has pagination, and how that pagination works.

You can say the website has pagination if there are links in it to pages like page 1, page 2, page 3 etc.
If the listings aren't paginated, you should say has_pagination is false.

If it does have pagination, figure out the pattern (for example, a parameter for the page number or for the items offset).
If it does have pagination, determine the total number of pages for the content.

IMPORTANT: be strict! If you don't spot a pagination link, assume the page doesn't have pagination and set has_pagination to false.

url_pattern_type: ONLY FILL THIS IN IF THE WEBSITE HAS PAGINATION

- page_num: page number parameter
- offset: offset parameter
- other: other type of pattern
- unknown: can't determine pattern

url_pattern: ONLY FILL THIS IN IF THE WEBSITE HAS PAGINATION

the URL for pages, with the parameter replaced by {page_num} or {offset} (plus {limit} if relevant).
Example:
https://www.example.com/${entity.pluralName.toLowerCase()}.php?page={page_num}

total_pages: ONLY FILL THIS IN IF THE WEBSITE HAS PAGINATION


For context, the page is a ${entity.name} catalogue index:

${pageTypeDescriptions[rootPageType]}

URL FOR THIS PAGE:

${defaultOptions.url}

WEBSITE CONTENT:

${defaultOptions.content}
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
      has_pagination: {
        type: "boolean",
      },
      url_pattern_type: {
        type: "string",
        enum: ["page_num", "offset", "other", "unknown"],
      },
      url_pattern: {
        type: "string",
      },
      total_pages: {
        type: "number",
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
  const hasPagination = assertBool(toolCall, "has_pagination");
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
    urlPatternType,
    urlPattern,
    totalPages,
  };
}
