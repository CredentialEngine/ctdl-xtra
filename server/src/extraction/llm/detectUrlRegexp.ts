import { ChatCompletionContentPart } from "openai/resources/chat/completions";
import { DefaultLlmPageOptions } from ".";
import { CatalogueType, PageType } from "../../../../common/types";
import getLogger from "../../logging";
import { assertArray, assertString, simpleToolCompletion } from "../../openai";
import { SimplifiedMarkdown } from "../../types";
import { resolveAbsoluteUrl } from "../../utils";
import { getCatalogueTypeDefinition } from "../catalogueTypes";

const logger = getLogger("extraction.llm.detectUrlRegexp");

export function createUrlExtractor(regexp: RegExp) {
  return async (baseUrl: string, content: SimplifiedMarkdown) => {
    // First, extract all markdown links [text](url) and their URLs
    const markdownLinkRegex = /\[([^\]]*)\]\(([^)]+)\)/g;
    const markdownLinkUrls: string[] = [];
    
    // Reset regex lastIndex to ensure we start from the beginning
    markdownLinkRegex.lastIndex = 0;
    let match;
    while ((match = markdownLinkRegex.exec(content)) !== null) {
      const fullUrl = match[2]; // The URL part of [text](url)
      markdownLinkUrls.push(fullUrl);
    }
    
    // Now find all regex matches
    regexp.lastIndex = 0;
    const urls = content.match(regexp) || [];
    const matchedUrls = urls.map((foundUrl) => {
      // If the matched URL is already absolute (starts with http:// or https://),
      // use it as-is to preserve subdomains and full URLs
      if (foundUrl.startsWith('http://') || foundUrl.startsWith('https://')) {
        return foundUrl;
      }

      const markdownUrl = markdownLinkUrls.find((url) => url.includes(foundUrl));
      if (markdownUrl) {
        return markdownUrl;
      }

      return resolveAbsoluteUrl(baseUrl, foundUrl);
    });

    const uniqueUrls = new Set(matchedUrls);
    return Array.from(uniqueUrls);
  };
}

export interface AdditionalPage {
  content: SimplifiedMarkdown;
  url: string;
  screenshot: string;
}

export default async function detectUrlRegexp(
  defaultOptions: DefaultLlmPageOptions & { catalogueType: CatalogueType },
  dataType: PageType,
  additionalPages?: AdditionalPage[]
) {
  if (dataType == PageType.DETAIL) {
    throw new Error("Invalid page data type.");
  }

  const entity = getCatalogueTypeDefinition(defaultOptions.catalogueType);

  const descriptions = {
    [PageType.CATEGORY_LINKS]: `
    ${entity.name.toUpperCase()} CATEGORY LINKS
    ${entity.categoryDescription}

    In other words, the page links to "categories" or "groups" of ${entity.pluralName},
    and we'll find more detailed ${entity.name} information if we navigate to those category pages.

    <example_content>
    ...
    Possibly links to other things (that are not categories)... (we don't want these)
    ...
    # Main Content

    *   [Accounting (ACCT)](link to category page)
    *   [Agricultural Economics (AGEC)](link to category page)
    *   [Agricultural Systems Management (ASM)](link to category page)
    *   [Agriculture (AGRI)](link to category page)
    *   [Allied Health (AH)](link to category page)
    *   [Animal and Range Science (ANSC)](link to category page)
    *   [Anthropology (ANTH)](link to category page)
    *   [Architectural Drafting & Estimating Technology (ARCT)](link to category page)
    *   [Art (ART)](link to category page)
    *   [Artificial Intelligence (AI)](link to category page)
    *   [Automation Management (AM)](link to category page)
    *   [Automotive Collision Technology (ABOD)](link to category page)
    *   [Automotive Technology (AUTO)](link to category page)
    ...
    Possibly links to other things (that are not categories)... (we don't want these)
    ...
    </example_content>
    `,

    [PageType.DETAIL_LINKS]: `
    ${entity.name.toUpperCase()} DETAIL LINKS
    ${entity.linkDescription}

    Typically those links include the ${entity.name} identifier and/or description.
    Presumably, more information about the ${entity.name} will be in the destination link.

    <example_content>
    ...
    Possibly links to other things (that are not ${entity.pluralName})... (we don't want these)
    ...
    ...
    # Main Content

    [${entity.exampleIdentifier} - ${entity.exampleName}](link to detail page)
    [ACCT 102 - Managerial Accounting](link to detail page)
    [ACCT 106 - Payroll Accounting](link to detail page)
    [ACCT 118 - Financial Concepts for Accounting](link to detail page)
    [ACCT 122 - Accounting Systems Applications](link to detail page)
    ...
    Possibly links to other things (that are not ${entity.pluralName})... (we don't want these)
    ...
    </example_content>

    VERY IMPORTANT NOTE:

    You must find a pattern that is generic to ${entity.name} detail links.
    Let's say for example that the page has 30 links and they're all like this:

    /${entity.name}-1?cat=ACCOUNTING&other=123
    /${entity.name}-2?cat=ACCOUNTING&other=123
    ...
    /${entity.name}-30?cat=ACCOUNTING&other=123

    Your regexp shouldn't look for /${entity.name}-[number]?cat=ACCOUNTING&other=123,
    but for /${entity.name}-[number]?[any characters],
    because in other pages there might be links like /${entity.name}-1?cat=MATH&other=321

    It's also NOT necessary to do something like /${entity.name}-[number]?cat=[letters]&other=[numbers] in
    the case above, because there might be multipe query string parameters in varying order which
    would break the regexp in edge cases.

    For example /${entity.name}-1?other=123&cat=ACCOUNTING is also a valid ${entity.name} link, and your regexp
    shouldn't break for that.

    The goal is to identify a pattern that is common to ${entity.name} detail links, but it doesn't need to
    be extremely strict, it shouldn't break if the query string params are in a different order for example.

    Be smart about this.

    TO SUM IT UP:

    GOOD
    /${entity.name}-[number]?[any characters]

    BAD
    /${entity.name}-[number]?cat=ACCOUNTING&other=123

    On the other hand, you should avoid regexps that will link to a wide variety of pages outside
    of ${entity.pluralName} detail pages.
    `,
    [PageType.API_REQUEST]: "",
    [PageType.EXPLORATORY]: "",
  };

  const prompt = `
    ${
      additionalPages
        ? `
      The following webpages all have lists of links to detail pages of a certain type.
      `
        : `The following webpage has a list of links to detail pages of a certain type.`
    }

    Your goal is to create a single JS regexp that will find all the URLs of those links.

    Go through the content carefully and think about a regexp that finds all the links
    with the type above.

    We are going to use it like this:

    > const detailUrls = content.match(new RegExp(regexp, "g"));

    DESCRIPTION OF THE LINKS
    ========================

    ${descriptions[dataType]}

    GUIDELINES FOR REGEXP CREATION
    ==============================

    Content:
    [Course Page A](course_page.php?id=1)
    [Course Page B](course_page.php?id=2)
    [Course Page C](course_page.php?id=3)
    Regexp: course_page\.php\?id=\d+

    Content:
    [Course Page A](/course_page.php?id=1)
    [Course Page B](/course_page.php?id=2)
    [Course Page C](/course_page.php?id=3)
    Regexp: \/course_page\.php\?id=\d+

    Content:
    [Course Page A](https://www.blablabla.com/course_page.php?id=1)
    [Course Page B](https://www.blablabla.com/course_page.php?id=2)
    [Course Page C](https://www.blablabla.com/course_page.php?id=3)
    Regexp: https:\/\/www.blablabla.com/course_page\.php\?id=\d+

    Content:
    [Course Page A](www.blablabla.com/course_page.php?id=1)
    [Course Page B](www.blablabla.com/course_page.php?id=2)
    [Course Page C](www.blablabla.com/course_page.php?id=3)
    Regexp: www\.blablabla\.com\/course_page\.php\?id=\d+

    IMPORTANT
    =========
    - only extract links for the type we mentioned above.
    - do not attempt to transform links in any way.
    - do not add any extra characters to the links.
    - we will run the regexp as you give it, on the content we gave you.
    - only submit one tool call with one regexp and total_links.
      There must be one regexp for all the links.
    - example_matches: some example matches that we should find when running your regexp. Max 5 examples.
    - it's obvious, but the URLs detected by your regexp should be in the page content!
    - if we give you multiple pages, make sure the single regexp works for all of them.

    The examples are EXAMPLES. Don't just blindly submit those as an answer. Create a regexp for the specific
    page content we give you.

    <page_content>
    ${defaultOptions.content}
    </page_content>

        ${
          additionalPages
            ? `
    ${additionalPages
      .map(
        (p) => `
    <page_content>
    ${p.content}
    </page_content>
    `
      )
      .join("\n")}
    `
            : null
        }
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

  const result = await simpleToolCompletion({
    messages: [
      {
        role: "user",
        content: completionContent,
      },
    ],
    toolName: "detail_link_regexp",
    parameters: {
      regexp: {
        type: "string",
      },
      example_matches: {
        type: "array",
        items: {
          type: "string",
        },
      },
    },
    logApiCall: defaultOptions?.logApiCalls
      ? {
          extractionId: defaultOptions.logApiCalls.extractionId,
          callSite: "detectUrlRegexp",
        }
      : undefined,
  });

  if (!result?.toolCallArgs) {
    throw new Error("Couldn't detect regexp");
  }

  const completion = result.toolCallArgs;
  let regexpStr = assertString(completion, "regexp");
  const exampleMatches = assertArray<string>(completion, "example_matches");
  logger.info(`Raw regexp is ${regexpStr}`);
  logger.info(`Example matches is ${exampleMatches}`);
  const regexp = new RegExp(regexpStr, "g");

  const mainContentUrls = [...(defaultOptions.content.match(regexp) || [])];
  const additionalContentUrls =
    additionalPages?.flatMap((p) => p.content.match(regexp) || []) || [];

  const allContentUrls = Array.from(
    new Set([...mainContentUrls, ...additionalContentUrls])
  );

  const notFoundExamples = exampleMatches.filter(
    (u) => !allContentUrls.includes(u)
  );

  if (notFoundExamples.length > 0) {
    logger.error("Examples not found:", notFoundExamples);
    throw new Error("Could not find every example");
  }

  return regexp;
}
