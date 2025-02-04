import { PageType } from "@common/types";
import { ChatCompletionContentPart } from "openai/resources/chat/completions";
import { DefaultLlmPageOptions } from ".";
import { assertArray, assertString, simpleToolCompletion } from "../../openai";
import { SimplifiedMarkdown } from "../../types";
import { resolveAbsoluteUrl } from "../../utils";

export function createUrlExtractor(regexp: RegExp) {
  return async (baseUrl: string, content: SimplifiedMarkdown) => {
    const urls = content.match(regexp) || [];
    return [
      ...new Set(
        urls.map((foundUrl) => {
          return resolveAbsoluteUrl(baseUrl, foundUrl);
        })
      ),
    ];
  };
}

export default async function detectUrlRegexp(
  defaultOptions: DefaultLlmPageOptions,
  dataType: PageType
) {
  if (dataType == PageType.COURSE_DETAIL_PAGE) {
    throw new Error("Invalid page data type.");
  }

  const descriptions = {
    [PageType.CATEGORY_LINKS_PAGE]: `
    CATEGORY LINKS

    Programs, careers, degrees, or course category pages.
    In other words, the page links to "categories" or "groups" of courses, and we'll find more detailed course
    information if we navigate to those category pages.

    EXAMPLE ON HOW TO IDENTIFY THE CATEGORIES:

    ...
    Possibly links to other things (that are not categories)... (we don't want these)
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
    Possibly links to other things (that are not categories)... (we don't want these)
    ...

    > page_type: category_links
    > Reason: The content is mostly links to generic subjects like "Accounting" and "Art" and not to individual courses.

    `,

    [PageType.COURSE_LINKS_PAGE]: `
    COURSE LINKS

    Course detail pages in an educational institution.
    Typically those links include the course identifier and/or description.
    Presumably, more information about the course will be in the destination link.

    EXAMPLE ON HOW TO IDENTIFY THE COURSE LINKS:

    ...
    Possibly links to other things (that are not courses)... (we don't want these)
    ...
    ...
    # Main Content

    [ACCT 101 - Financial Accounting](preview_course_nopop.php?catoid=7&coid=23568)
    [ACCT 102 - Managerial Accounting](preview_course_nopop.php?catoid=7&coid=23569)
    [ACCT 106 - Payroll Accounting](preview_course_nopop.php?catoid=7&coid=23570)
    [ACCT 118 - Financial Concepts for Accounting](preview_course_nopop.php?catoid=7&coid=23571)
    [ACCT 122 - Accounting Systems Applications](preview_course_nopop.php?catoid=7&coid=23572)
    ...
    Possibly links to other things (that are not couses)... (we don't want these)
    ...

    VERY IMPORTANT NOTE (PLEASE READ):

    You must find a pattern that is generic to course detail links.
    Let's say for example that the page has 30 links and they're all like this:

    /course-1?cat=ACCOUNTING&other=123
    /course-2?cat=ACCOUNTING&other=123
    ...
    /course-30?cat=ACCOUNTING&other=123

    Your regexp shouldn't look for /course-[number]?cat=ACCOUNTING&other=123,
    but for /course-[number]?[any characters],
    because in other pages there might be links like /course-1?cat=MATH&other=321

    It's also NOT necessary to do something like /course-[number]?cat=[letters]&other=[numbers] in
    the case above, because there might be multipe query string parameters in varying order which
    would break the regexp in edge cases.

    For example /course-1?other=123&cat=ACCOUNTING is also a valid course link, and your regexp
    shouldn't break for that.

    The goal is to identify a pattern that is common to course detail links, but it doesn't need to
    be extremely strict, it shouldn't break if the query string params are in a different order for example.

    Be smart about this.

    TO SUM IT UP:

    GOOD
    /course-[number]?[any characters]

    BAD
    /course-[number]?cat=ACCOUNTING&other=123
    `,
  };

  const prompt = `
    This document has a list of links to detail pages of a certain type:

    ${descriptions[dataType]}

    Your goal is to create a JS regexp for all the URLs of those links.
    Go through the content carefully and think about a regexp that finds all the links
    with the type above.
    We are going to use it like this:

    > const detailUrls = content.match(new RegExp(regexp, "g"));

    Break down your reasoning for creating the regexp.

    IMPORTANT
    =========
    - only extract links for the type we mentioned above.
    - do not attempt to transform links in any way.
    - do not add any extra characters to the links.
    - we will run the regexp as you give it, on the content we gave you.
    - only submit one tool call with one regexp and total_links.
      There must be one regexp for all the links.
    - example_matches: some example matches that we should find when running your regexp. Max 5 examples.

    EXAMPLES
    ========
    Note that these are just examples!
    There will be different patterns and links in different pages.

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

    PAGE CONTENT
    ============

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
  console.log(`Raw regexp is ${regexpStr}`);
  console.log(`Example matches is ${exampleMatches}`);
  const regexp = new RegExp(regexpStr, "g");

  const urls = defaultOptions.content.match(regexp) || [];
  if (!exampleMatches.every((u) => urls.find((u2) => u2 == u))) {
    throw new Error("Could not find every example");
  }
  return regexp;
}
