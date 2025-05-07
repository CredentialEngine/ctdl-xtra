import { isWithinTokenLimit } from "gpt-tokenizer";
import { DefaultLlmPageOptions } from "./llm";
import detectChunkSplitRegexp from "./llm/detectChunkSplitRegexp";
import { detectMultipleCourses } from "./llm/detectMultipleCourses";
import { preprocessText } from "./llm/extractAndVerifyEntityData";

export async function splitChunks(options: DefaultLlmPageOptions) {
  let regexp, expectedCourseCount, chunks, firstCourseTitle;
  let attempts = 0;

  while (attempts < 10) {
    try {
      ({ regexp, expectedCourseCount, firstCourseTitle } =
        await detectChunkSplitRegexp(options));
      chunks = options.content.split(regexp);
      if (!chunks) {
        const errorMessage = `Could not find any chunks with the regexp: ${regexp}. Expected ${expectedCourseCount} chunks.`;
        console.error(errorMessage);
        throw new Error(errorMessage);
      }

      chunks = chunks.filter((chunk) => chunk.trim() !== "");

      // There's usually some junk at the beginning of the document, so let's
      // remove the first few chunks until the first title appears
      while (chunks.length > 0) {
        if (
          preprocessText(chunks[0]).includes(preprocessText(firstCourseTitle))
        ) {
          break;
        }
        chunks.shift();
      }

      // LLMs are not good at counting so let's treat the number of courses as a ballpark estimate
      const discrepancy = Math.abs(chunks.length - expectedCourseCount);
      const allowedDiscrepancy =
        expectedCourseCount > 5 ? Math.floor(expectedCourseCount * 0.1) : 0;
      if (discrepancy > allowedDiscrepancy) {
        const errorMessage =
          "Could not find expected number of chunks.\n" +
          `Regexp: ${regexp}.\n` +
          `Found ${chunks.length} chunks, expected ${expectedCourseCount}`;

        console.error(errorMessage);
        throw new Error(errorMessage);
      }
      console.log(`Success - Found ${chunks.length} chunks`);
      return chunks;
    } catch (error) {
      if (error instanceof Error) {
        options.additionalContext = {
          message: error.message,
        };
      }
      attempts++;
    }
  }

  throw new Error("Failed to split chunks");
}

export async function shouldChunk(options: DefaultLlmPageOptions) {
  const isLarge = !isWithinTokenLimit(options.content, 1000);
  if (!isLarge) {
    return false;
  }
  const hasMultipleCourses = await detectMultipleCourses(options);
  return hasMultipleCourses;
}
