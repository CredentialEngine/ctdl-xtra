import { PageType } from "@common/types";
import {
  ChatCompletionContentPart,
  ChatCompletionMessageParam,
} from "openai/resources/chat/completions";
import { DefaultLlmPageOptions } from ".";
import { assertStringEnum, simpleToolCompletion } from "../../openai";

export async function detectPageType(defaultOptions: DefaultLlmPageOptions) {
  const prompt = `
  You are an agent in a system that autonomously scrapes course data from the internet.

  For this task, you're being given the content of a web page that we believe is relevant
  for finding course data.

  Your goal is to identify the primary type of content that features in the page.
  There are descriptions for the content types we're looking for below.

  In order to successfully identify it, follow these instructions:

  1. Walk through the content in the page, step by step, trying to identify the main content section.
  2. In order to do that, note that things like navigation menus, headers, footers, sidebars and
     such might also show up in the page. You can use those pieces as hints and context data,
     but you're looking for the main content section.
  3. When evaluating the main content section, go through it carefully and consider:
     - Is the content in the main section mostly links to individual courses such as ACCT 101 (course links page)?
     - Is the content in the main section mostly links to category pages such as "Accounting" (category links page)?
     - Is the content in the main section mostly details such as full descriptions and credit information for courses (course detail page)?
     - Is the content something else that doesn't match the descriptions above?
     Sometimes the page may look like a mix of content. In that case:
     - Prioritize content in the main section. If the content in the main section is a course detail,
       even if it's just a single one, consider it a course detail page.
  4. Take into account both the URLs and the text content of the links when you find some that
     may help you make a decision.
  5. Look at the screenshot, if one is provided, to get a better understanding of the page.

  PAGE TYPES
  ==========

  page_type course_links:

  It has links to the courses of an institution.
  Typically, the course's code and title
  show up in the link (example: ACCT 101).
  Presumably, detailed information about the courses will be present in the destination links.

  Example:

  ...
  # Main Content

  [ACCT 101 - Financial Accounting](preview_course_nopop.php?catoid=7&coid=23568)
  [ACCT 102 - Managerial Accounting](preview_course_nopop.php?catoid=7&coid=23569)
  [ACCT 106 - Payroll Accounting](preview_course_nopop.php?catoid=7&coid=23570)
  [ACCT 118 - Financial Concepts for Accounting](preview_course_nopop.php?catoid=7&coid=23571)
  [ACCT 122 - Accounting Systems Applications](preview_course_nopop.php?catoid=7&coid=23572)
  ...

  > page_type: course_links
  > Reason: The content is mostly links to specific courses like ACCT 101, ACCT 102, etc.

  page_type course_details:

  It has details for the courses of an institution directly in the page.
  Unlike A, pretty much all information about the courses is already in the page.
  In other words, it doesn't have links to detail pages; it IS a detail page.
  Information may include: identifier, description, credits, prerequisites...

  Example:

  ...
  # Main Content

  ACCT 2101 Principles of Accounting I (3-0-3)
  A study of the underlying theory and application of financial accounting concepts. Introduction to accounting as a decision-making tool. Financial accounting principles, methods and procedures, including assets, liabilities, equities, and financial statements are examined. Analyzing and interpreting of financial statements as tools in the organization's information system are also examined.
  ACCT 2102 Principles of Accounting II (3-0-3)
  A study of the underlying theory and application of managerial accounting concepts. The course is a continuation of ACCT 2101, focusing on accounting as a decision-making tool. Management accounting principles, methods and procedures, are examined.
  Prerequisite(s): ACCT 2101 with a minimum grade of C
  ...

  > page_type: course_details
  > Reason: The content is full details for courses.

  page_type category_links:

  It has links to programs, careers, degrees, or course category pages.
  In other words, the page links to "categories" or "groups" of courses.
  We'll find more detailed course information if we navigate to those category pages.

  Example:

  ...
  # Main Content

  *   [Academic Skills Courses (ASC)](/catalog/course-descriptions/asc/)
  *   [Accounting (ACCT)](/catalog/course-descriptions/acct/)
  *   [Agricultural Economics (AGEC)](/catalog/course-descriptions/agec/)
  *   [Agricultural Systems Management (ASM)](/catalog/course-descriptions/asm/)
  *   [Agriculture (AGRI)](/catalog/course-descriptions/agri/)
  *   [Allied Health (AH)](/catalog/course-descriptions/ah/)
  *   [Animal and Range Science (ANSC)](/catalog/course-descriptions/ansc/)
  *   [Anthropology (ANTH)](/catalog/course-descriptions/anth/)
  *   [Architectural Drafting & Estimating Technology (ARCT)](/catalog/course-descriptions/arct/)
  *   [Art (ART)](/catalog/course-descriptions/art/)
  *   [Artificial Intelligence (AI)](/catalog/course-descriptions/ai/)
  *   [Automation Management (AM)](/catalog/course-descriptions/am/)
  *   [Automotive Collision Technology (ABOD)](/catalog/course-descriptions/abod/)
  *   [Automotive Technology (AUTO)](/catalog/course-descriptions/auto/)
  ...

  > page_type: category_links
  > Reason: The content is mostly links to generic subjects like "Accounting" and "Art" and not to individual courses.

  page_type other:

  Other. It doesn't match the descriptions above.

  IMPORTANT
  =========
  - only submit ONE tool call. There is ONE primary content type in the page.
  - the examples are not exhaustive or meant to represent the whole universe of content out there.
    They're just examples that give you an idea of what the content looks like.

  URL: ${defaultOptions.url}

  PAGE CONTENT
  ============
  ${defaultOptions.content}
`;

  const pageTypes = [
    "course_links",
    "course_details",
    "category_links",
    "other",
  ];

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
    toolName: "page_type",
    parameters: {
      page_type: {
        type: "string",
        enum: pageTypes,
      },
    },
    logApiCall: defaultOptions?.logApiCalls
      ? {
          extractionId: defaultOptions.logApiCalls.extractionId,
          callSite: "detectPageType",
        }
      : undefined,
  });

  if (!result?.toolCallArgs?.page_type) {
    return null;
  }

  const pageType = assertStringEnum(
    result.toolCallArgs,
    "page_type",
    pageTypes
  );
  if (pageType === "unknown") {
    return null;
  }

  switch (pageType) {
    case "course_links":
      return PageType.COURSE_LINKS_PAGE;
    case "course_details":
      return PageType.COURSE_DETAIL_PAGE;
    case "category_links":
      return PageType.CATEGORY_LINKS_PAGE;
    default:
      return null;
  }
}
