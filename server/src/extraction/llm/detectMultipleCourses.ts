import { DefaultLlmPageOptions, userPageMessage } from ".";
import { assertBool } from "../../llm/assert";
import { simpleToolCompletion } from "../../llm/LLMProviderApi";

export async function detectMultipleCourses(options: DefaultLlmPageOptions) {
  const prompt = `
This is a page that we extracted from a university website.

It is either a course detail page (containing description and details for a single course)
or a course list page (containing a list of courses, possibly with their details and descriptions).

Your goal is to detect which one of the above is right, that is
whether this page contains a single course or multiple courses.

PAGE URL:

${options.url}

SIMPLIFIED PAGE CONTENT:

${options.content}
`;

  const messages = [userPageMessage(prompt, options?.screenshot)];
  const result = await simpleToolCompletion({
    messages,
    toolName: "detect_multiple_courses",
    parameters: {
      multiple_courses: {
        type: "boolean",
      },
    },
    requiredParameters: ["multiple_courses"],
    logApiCall: options?.logApiCalls
      ? {
          extractionId: options.logApiCalls.extractionId,
          callSite: "extractCourseDataItem",
        }
      : undefined,
  });
  if (!result || !result.toolCallArgs) {
    return [];
  }
  const multipleCourses = assertBool(result.toolCallArgs, "multiple_courses");
  return multipleCourses;
}
