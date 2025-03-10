import { CatalogueType, PageType, RecipeConfiguration } from "@common/types";
import { ChatCompletionContentPart } from "openai/resources/chat/completions";
import { DefaultLlmPageOptions } from ".";
import { assertArray, assertString, simpleToolCompletion } from "../../openai";
import { SimplifiedMarkdown } from "../../types";
import { resolveAbsoluteUrl } from "../../utils";
import { getCatalogueTypeDefinition } from "../catalogueTypes";

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

export interface AdditionalPage {
  content: SimplifiedMarkdown;
  url: string;
  screenshot: string;
}

export default async function detectUrlRegexp(
  defaultOptions: DefaultLlmPageOptions & { catalogueType: CatalogueType },
  dataType: PageType,
  currentConfiguration?: RecipeConfiguration,
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

    EXAMPLE ON HOW TO IDENTIFY THE CATEGORIES:

    ...
    Possibly links to other things (that are not categories)... (we don't want these)
    ...
    # Main Content

    *   [Accounting (ACCT)](/catalog/${entity.name}/acct/)
    *   [Agricultural Economics (AGEC)](/catalog/${entity.name}/agec/)
    *   [Agricultural Systems Management (ASM)](/catalog/${entity.name}/asm/)
    *   [Agriculture (AGRI)](/catalog/${entity.name}/agri/)
    *   [Allied Health (AH)](/catalog/${entity.name}/ah/)
    *   [Animal and Range Science (ANSC)](/catalog/${entity.name}/ansc/)
    *   [Anthropology (ANTH)](/catalog/${entity.name}/anth/)
    *   [Architectural Drafting & Estimating Technology (ARCT)](/catalog/${entity.name}/arct/)
    *   [Art (ART)](/catalog/${entity.name}/art/)
    *   [Artificial Intelligence (AI)](/catalog/${entity.name}/ai/)
    *   [Automation Management (AM)](/catalog/${entity.name}/am/)
    *   [Automotive Collision Technology (ABOD)](/catalog/${entity.name}/abod/)
    *   [Automotive Technology (AUTO)](/catalog/${entity.name}/auto/)
    ...
    Possibly links to other things (that are not categories)... (we don't want these)
    ...

    > page_type: category_links
    > Reason: The content is mostly links to generic subjects like "Accounting" and "Art"
      and not to individual ${entity.pluralName}.

    `,

    [PageType.DETAIL_LINKS]: `
    ${entity.name.toUpperCase()} DETAIL LINKS
    ${entity.linkDescription}

    Typically those links include the ${entity.name} identifier and/or description.
    Presumably, more information about the ${entity.name} will be in the destination link.

    EXAMPLE ON HOW TO IDENTIFY THE ${entity.name.toUpperCase()} LINKS:
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
  console.log(`Raw regexp is ${regexpStr}`);
  console.log(`Example matches is ${exampleMatches}`);
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
    console.error("Examples not found:", notFoundExamples);
    throw new Error("Could not find every example");
  }

  return regexp;
}
