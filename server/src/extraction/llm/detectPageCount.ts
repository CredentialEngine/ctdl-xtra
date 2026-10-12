import { DefaultLlmPageOptions, userPageMessage } from ".";
import { assertBool, assertNumber } from "../../llm/assert";
import { simpleToolCompletion } from "../../llm/LLMProviderApi";

export async function detectPageCount(
  defaultOptions: DefaultLlmPageOptions,
  urlPattern: string,
  urlPatternType: string
) {
  const prompt = `
You are being given information about a web page that has paginated links in its content.
Your goal is to determine total number of pages, IF that information can be inferred from the page.
If you disagree the content has pagination, or if you can't determine the page count, use the
tool accordingly.

DETECTED PAGINATION PATTERN: ${urlPattern}

DETECTED PATTERN TYPE: ${urlPatternType}

WEBSITE CONTENT:

${defaultOptions.content}
`;

  const messages = [userPageMessage(prompt, defaultOptions.screenshot)];
  const result = await simpleToolCompletion({
    messages,
    toolName: "submit_detected_page_count",
    parameters: {
      detected_pagination: {
        type: "boolean",
      },
      detected_page_count: {
        type: "boolean",
      },
      total_pages: {
        type: "number",
      },
    },
    logApiCall: defaultOptions?.logApiCalls
      ? {
          callSite: "detectPageCount",
          extractionId: defaultOptions.logApiCalls.extractionId,
        }
      : undefined,
  });

  if (!result.toolCallArgs) {
    return undefined;
  }
  const toolCall = result.toolCallArgs;
  if (!toolCall) {
    return undefined;
  }
  const hasPagination = assertBool(toolCall, "detected_pagination");
  const hasPageCount = assertBool(toolCall, "detected_page_count");

  if (!hasPagination || !hasPageCount) {
    return undefined;
  }

  const totalPages = assertNumber(toolCall, "total_pages");
  return {
    totalPages,
  };
}
