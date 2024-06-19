import { ChatCompletionMessageParam } from "openai/resources/chat/completions";
import {
  PAGE_DATA_TYPE,
  PaginationConfiguration,
  UrlPatternType,
} from "../data/schema";
import {
  BadToolCallResponseError,
  assertBool,
  assertNumber,
  assertString,
  assertStringEnum,
  simpleToolCompletion,
} from "../openai";
import { simplifyHtml, toMarkdown } from "./browser";

const pageTypeDescriptions = {
  [PAGE_DATA_TYPE.COURSE_LINKS_PAGE]:
    "It has links to ALL the courses for an institution. Pagination is for pages of links to courses.",
  [PAGE_DATA_TYPE.CATEGORY_PAGE]:
    "It has links to program or degree pages that presumably have links/descriptions for the courses. " +
    "Those links are presumably extensive for ALL the programs/degrees in the institution." +
    "Pagination is for pages of program/degree links.",
  [PAGE_DATA_TYPE.COURSE_DETAIL_PAGE]:
    "It has names/descriptions for ALL the courses for an instution. " +
    "Pagination is for pages of course descriptions.",
};

export async function detectPagination(
  url: string,
  html: string,
  screenshot: string,
  rootPageType: PAGE_DATA_TYPE
): Promise<PaginationConfiguration | null> {
  const content = await toMarkdown(await simplifyHtml(html));
  const prompt = `
Your goal is to determine whether the given website has pagination, and how that pagination works.

You can say the website has pagination if there are links in it to pages like page 1, page 2, page 3 etc.
If the listings aren't paginated, you should say has_pagination is false.
However if it does have pagination, figure out the pattern (for example, a parameter for the page number or for the items offset).
Also, if it does have pagination, determine the total number of pages for the content.

url_pattern_type: ONLY FILL THIS IN IF THE WEBSITE HAS PAGINATION
- page_num: page number parameter
- offset: offset parameter
- other: other type of pattern
- unknown: can't determine pattern

url_pattern: ONLY FILL THIS IN IF THE WEBSITE HAS PAGINATION

the URL for pages, with the parameter replaced by {page_num} or {offset} (plus {limit} if relevant).
Example:
https://www.example.com/courses.php?page={page_num}

total_pages: ONLY FILL THIS IN IF THE WEBSITE HAS PAGINATION


For context, the page is a course catalogue index.
${pageTypeDescriptions[rootPageType]}

WEBSITE CONTENT:

${content}
`;

  const messages: ChatCompletionMessageParam[] = [
    {
      role: "user",
      content: [
        {
          type: "text",
          text: prompt,
        },
        {
          type: "image_url",
          image_url: { url: `data:image/webp;base64,${screenshot}` },
        },
      ],
    },
  ];
  const toolCall = await simpleToolCompletion(
    messages,
    "submit_detected_pagination",
    {
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
    }
  );
  if (!toolCall) {
    return null;
  }
  const hasPagination = assertBool(toolCall, "has_pagination");
  if (!hasPagination) {
    return null;
  }

  const urlPatternType = assertStringEnum(toolCall, "url_pattern_type", [
    "page_num",
    "offset",
    "other",
    "unknown",
  ]) as UrlPatternType;
  const urlPattern = assertString(toolCall, "url_pattern");
  if (!urlPattern.startsWith("http")) {
    throw new BadToolCallResponseError(`Expected a URL pattern: ${urlPattern}`);
  }
  if (urlPattern == "page_num" && !urlPattern.includes("{page_num}")) {
    throw new BadToolCallResponseError(`Couldn't find page_num: ${urlPattern}`);
  }
  if (urlPattern == "offset" && !urlPattern.includes("{offset}")) {
    throw new BadToolCallResponseError(`Couldn't find offset: ${urlPattern}`);
  }
  const totalPages = assertNumber(toolCall, "total_pages");
  return {
    urlPatternType,
    urlPattern,
    totalPages,
  };
}
