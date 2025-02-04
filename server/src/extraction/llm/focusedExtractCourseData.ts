import { TextInclusion } from "@common/types";
import {
  ChatCompletionContentPart,
  ChatCompletionMessageParam,
} from "openai/resources/chat/completions";
import { DefaultLlmPageOptions } from ".";
import { CourseStructuredData } from "../../appRouter";
import { simpleToolCompletion } from "../../openai";
import {
  basePrompt,
  processCourse,
  validCreditUnitTypes,
} from "./extractCourseData";

export async function focusedExtractCourseData(
  options: DefaultLlmPageOptions,
  course: CourseStructuredData,
  textInclusion: TextInclusion
) {
  const prompt = `
Your goal is to extract course data from this page for one specific course.

In a previous step, we asked you to extract the data, but we noticed there was an issue
with the course description.

Note you must extract data for the course EXACTLY as it is in the page, without adding or
removing anything.

Your previous extraction (INCORRECT) was:

${JSON.stringify(course)}

${basePrompt}

Pay attention to the page content and extract it correctly this time.

PAGE URL:

${options.url}

SIMPLIFIED PAGE CONTENT:

${options.content}
`;

  const completionContent: ChatCompletionContentPart[] = [
    {
      type: "text",
      text: prompt,
    },
  ];

  if (options?.screenshot) {
    completionContent.push({
      type: "image_url",
      image_url: { url: `data:image/webp;base64,${options.screenshot}` },
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
    toolName: "course_data",
    parameters: {
      course: {
        type: "object",
        properties: {
          course_id: {
            type: "string",
          },
          course_name: {
            type: "string",
          },
          course_description: {
            type: "string",
          },
          course_credits_min: {
            type: "string",
          },
          course_credits_max: {
            type: "string",
          },
          course_credits_type: {
            type: "string",
            enum: validCreditUnitTypes,
          },
          course_prerequisites: {
            type: "string",
          },
        },
        required: ["course_id", "course_name", "course_description"],
      },
    },
    requiredParameters: ["course"],
    logApiCall: options?.logApiCalls
      ? {
          extractionId: options.logApiCalls.extractionId,
          callSite: "extractCourseDataItem",
        }
      : undefined,
  });
  const extractedCourse = result?.toolCallArgs?.course as CourseStructuredData;
  if (!extractedCourse) {
    return null;
  }
  return processCourse(extractedCourse);
}
