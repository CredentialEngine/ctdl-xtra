import { ChatCompletionContentPart } from "openai/resources/chat/completions";
import { DefaultLlmPageOptions } from ".";
import { ProviderModel } from "../../../../common/types";
import { assertNumber, assertString, simpleToolCompletion } from "../../openai";

export default async function detectChunkSplitRegexp(
  defaultOptions: DefaultLlmPageOptions
) {
  const additionalContext = defaultOptions.additionalContext
    ? `
    ADDITIONAL CONTEXT
    ==================

    This is another attempt at this task. The last attempt failed for the following reason:

    ${defaultOptions.additionalContext}

    (the values above were provided by you in the previous attempt)
    `
    : "";
  const prompt = `
    This document has a list of courses. For each course, it may have a description and details.

    One of your goals is to find a regexp that splits the document per course. So a course list with 5 courses
    should be split into 5 chunks.

    We are going to use the regexp like this:

    > const chunks = content.split(new RegExp(regexp, "g"))

    The other goal is to find how many courses are in the document.
    Sometimes the document will have the number of courses in the title.
    Sometimes in the end.
    Sometimes it might not have the number of courses at all or can be inferred from the content.

    If the document lists the number of courses, use that number, do not attempt to count the courses yourself.

    Explain your reasoning for the expected course count in expected_course_count_explanation.

    SANITY CHECK
    ============

    Additionally, we are going to do a sanity check on the regexp by using the first_course_title
    value: the title of the first course you expect to find in the document. We expect to find this
    course title in the first chunk.

    IMPORTANT
    ========

    The regexp should begin with (?=

    EXAMPLES
    ========

    If the document is:

    ... misc text ...

    Course 1

    Course 1 description

    Course 1 details

    Course 2

    Course 2 description

    Course 2 details

    Course 3

    Course 3 description

    Course 3 details

    ... misc text ...

    The regexp should split the string into 3 chunks, separated by the course title.

    The documents sometimes have unrelated text before or after the courses. That's OK, no need
    to account for that. Focus on splitting the courses.

    ${additionalContext}

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
    model: ProviderModel.Gpt41,
    toolName: "regexp",
    parameters: {
      regexp: {
        type: "string",
      },
      expected_course_count: {
        type: "number",
      },
      expected_course_count_explanation: {
        type: "string",
      },
      first_course_title: {
        type: "string",
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
  const expectedCourseCount = assertNumber(completion, "expected_course_count");
  console.log(`Raw regexp is ${regexpStr}`);
  console.log(`Expected chunks is ${expectedCourseCount}`);
  const regexp = new RegExp(regexpStr, "g");
  const firstCourseTitle = assertString(completion, "first_course_title");
  console.log(`Explanation is ${completion.expected_course_count_explanation}`);
  return { regexp, expectedCourseCount, firstCourseTitle };
}
