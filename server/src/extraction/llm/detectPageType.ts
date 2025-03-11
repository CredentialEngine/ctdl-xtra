import {
  ChatCompletionContentPart,
  ChatCompletionMessageParam,
} from "openai/resources/chat/completions";
import { DefaultLlmPageOptions } from ".";
import {
  CatalogueType,
  PageType,
  RecipeConfiguration,
} from "../../../../common/types";
import {
  assertStringEnum,
  BadToolCallResponseError,
  simpleToolCompletion,
} from "../../openai";
import { getCatalogueTypeDefinition } from "../catalogueTypes";
export async function detectPageType(
  defaultOptions: DefaultLlmPageOptions & { catalogueType: CatalogueType },
  // @ts-ignore
  currentConfiguration?: RecipeConfiguration
) {
  const entity = getCatalogueTypeDefinition(defaultOptions.catalogueType);

  const prompt = `
  You are an agent in a system that autonomously scrapes educational data from the internet.

  For this task, you're being given the content of a web page that we believe is relevant
  for finding ${entity.pluralName} (${entity.description}) entities.

  Your goal is to identify the primary type of content that features in the page.
  There are descriptions for the content types we're looking for below.

  In order to successfully identify it, follow these instructions:

  1. Walk through the content in the page, step by step, trying to identify the main content section.
  2. In order to do that, note that things like navigation menus, headers, footers, sidebars and
     such might also show up in the page. You can use those pieces as hints and context data,
     but you're looking for the main content section.
  3. When evaluating the main content section, go through it carefully and consider:
     - Is the content in the main section mostly links to individual ${entity.pluralName} such as ${entity.exampleIdentifier} (${entity.name} links page)?
     - Is the content in the main section mostly links to category pages (${entity.name} categories page)?
     - Is the content in the main section mostly details such as full descriptions for ${entity.pluralName} (${entity.name} detail page)?
     - Is the content something else that doesn't match the descriptions above?
     Sometimes the page may look like a mix of content. In that case:
     - Prioritize content in the main section. If the content in the main section is a ${entity.name} detail,
       even if it's just a single one, consider it a ${entity.name} detail page.
  4. Take into account both the URLs and the text content of the links when you find some that
     may help you make a decision.
  5. Look at the screenshot, if one is provided, to get a better understanding of the page.

  PAGE TYPES
  ==========

  page_type ${PageType.DETAIL_LINKS}:

  ${entity.linkDescription}
  Typically, the ${entity.name}'s identifier and title
  show up in the link (example: ${entity.exampleIdentifier}).
  Presumably, detailed information about the ${entity.pluralName} will be present in the destination links.

  <example>
  ...
  # Main Content

  [${entity.exampleIdentifier} - ${entity.exampleName}](${entity.name}.php?catoid=7&coid=1)
  [${entity.exampleIdentifier.replace(/\d+$/, (n) => String(Number(n) + 1))} - Another ${entity.name}](${entity.name}.php?catoid=7&coid=2)
  [${entity.exampleIdentifier.replace(/\d+$/, (n) => String(Number(n) + 2))} - Yet Another ${entity.name}](${entity.name}.php?catoid=7&coid=3)
  ...

  > page_type: ${PageType.DETAIL_LINKS}
  > Reason: The content is mostly links to specific ${entity.pluralName} like ${entity.exampleIdentifier}.
  </example>

  page_type ${PageType.DETAIL}:

  ${entity.detailDescription}
  Unlike A, pretty much all information about the ${entity.pluralName} is already in the page.
  In other words, it doesn't have links to detail pages; it IS a detail page.

  For ${entity.name}, we need the following fields:

  ${Object.entries(entity.properties)
    .map(([key, { description }]) => `${key}: ${description}`)
    .join("\n")}

  <example>
  ...
  # Main Content

  ## ${entity.exampleIdentifier}
  ${entity.exampleName}
  ${entity.exampleDescription}
  ...

  > page_type: ${PageType.DETAIL}
  > Reason: The content is full details for ${entity.pluralName}.
  </example>

  page_type ${PageType.CATEGORY_LINKS}:

  ${entity.categoryDescription}
  In other words, the page links to "categories" or "groups" of ${entity.pluralName}.
  We'll find more detailed ${entity.name} information if we navigate to those category pages.

  <example>
  ...
  # Main Content

  *   [Academic Skills ${entity.pluralName}](/catalog/${entity.name}-descriptions/asc/)
  *   [Accounting ${entity.pluralName}](/catalog/${entity.name}-descriptions/acct/)
  *   [Agricultural Economics ${entity.pluralName}](/catalog/${entity.name}-descriptions/agec/)
  ...

  > page_type: ${PageType.CATEGORY_LINKS}
  > Reason: The content is mostly links to generic subjects like "Accounting" and not to individual ${entity.pluralName}.
  </example>

  Blank page_type:

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
        enum: Object.values(PageType),
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

  try {
    const pageType = assertStringEnum(
      result.toolCallArgs,
      "page_type",
      Object.values(PageType)
    );
    return pageType;
  } catch (e) {
    if (e instanceof BadToolCallResponseError) {
      return null;
    }
    throw e;
  }
}
