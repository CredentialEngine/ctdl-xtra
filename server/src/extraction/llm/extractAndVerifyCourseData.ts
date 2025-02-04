import { CourseStructuredData, TextInclusion } from "@common/types";
import { DefaultLlmPageOptions } from ".";
import { SimplifiedMarkdown } from "../../types";
import { shouldChunk, splitChunks } from "../splitChunks";
import { extractCourseData } from "./extractCourseData";
import { focusedExtractCourseData } from "./focusedExtractCourseData";

export function preprocessText(text: string): string {
  return text
    .toLowerCase()
    .replace(/(?<!\!)\[([^\]]+)\]\([^)]*\)/g, "$1") // remove MD links
    .replace(/[^a-z0-9]/g, "");
}

async function reportTextInclusion(
  course: CourseStructuredData,
  content: string
): Promise<TextInclusion> {
  const result: TextInclusion = {} as TextInclusion;

  for (const [key, value] of Object.entries(course)) {
    if (value !== undefined && value !== null) {
      const preprocessedValue = preprocessText(String(value));
      result[key as keyof TextInclusion] = {
        full: content.includes(preprocessedValue),
      };
    }
  }

  return result;
}

const passesVerification = (textInclusion: TextInclusion) => {
  return (
    textInclusion.course_id?.full &&
    textInclusion.course_description?.full &&
    (textInclusion.course_prerequisites
      ? textInclusion.course_prerequisites.full
      : true)
  );
};

async function verifyAndRetryExtraction(
  course: CourseStructuredData,
  options: DefaultLlmPageOptions,
  preprocessedContent: string
): Promise<{ course: CourseStructuredData; textInclusion: TextInclusion }> {
  let textInclusion = await reportTextInclusion(course, preprocessedContent);
  let retryCount = 0;
  const MAX_RETRIES = 3;

  // Retry focused extraction if the text inclusion is not complete for ID, description and prereqs
  while (retryCount < MAX_RETRIES && !passesVerification(textInclusion)) {
    const focusedCourseData = await focusedExtractCourseData(
      options,
      course,
      textInclusion
    );
    if (focusedCourseData) {
      course = focusedCourseData;
      textInclusion = await reportTextInclusion(course, preprocessedContent);
    }
    retryCount++;
  }

  return { course, textInclusion };
}

async function maybeChunkContent(
  options: DefaultLlmPageOptions
): Promise<DefaultLlmPageOptions[]> {
  const willChunk = await shouldChunk(options);
  if (willChunk) {
    const chunks = await splitChunks(options);
    return chunks.map((chunk) => ({
      ...options,
      content: chunk as SimplifiedMarkdown,
    }));
  }
  return [options];
}

export async function extractAndVerifyCourseData(
  options: DefaultLlmPageOptions
): Promise<{ course: CourseStructuredData; textInclusion: TextInclusion }[]> {
  const chunks = await maybeChunkContent(options);

  const results = [];
  for (const chunkOptions of chunks) {
    const coursesData = await extractCourseData(chunkOptions);
    if (!coursesData) {
      console.log("Couldn't find course data");
      continue;
    }

    const preprocessedContent = preprocessText(chunkOptions.content);

    for (const course of coursesData) {
      const verifiedExtraction = await verifyAndRetryExtraction(
        course,
        chunkOptions,
        preprocessedContent
      );
      results.push(verifiedExtraction);
    }
  }

  return results;
}
