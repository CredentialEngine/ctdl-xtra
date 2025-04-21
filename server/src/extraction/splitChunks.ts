import { isWithinTokenLimit } from "gpt-tokenizer";
import { DefaultLlmPageOptions } from "./llm";
import detectChunkSplitRegexp from "./llm/detectChunkSplitRegexp";
import { detectMultipleCourses } from "./llm/detectMultipleCourses";
import { preprocessText } from "./llm/extractAndVerifyEntityData";

/**
 * The maximum number of LLM tokens that can be used to split the chunks.
 * This is a compromise between the number of tokens and the number of chunks
 * and therefore the number of calls to the LLM. If the number of tokens is too low,
 * the number of requests will increase. If the number of tokens is too high, we might
 * encounter rate limiting from the LLM provider or exceed the context window of the LLM.
 */
const MAX_TOKEN_LIMIT = 3000;

export async function splitChunks(options: DefaultLlmPageOptions) {
  let regexp, expectedCourseCount, chunks, firstCourseTitle;
  let attempts = 0;
  const maxAttempts = 10;

  while (attempts < maxAttempts) {
    try {
      ({ regexp, expectedCourseCount, firstCourseTitle } =
        await detectChunkSplitRegexp(options));
      chunks = options.content.split(regexp);
      if (!chunks || chunks?.length < expectedCourseCount) {
        throw new Error(`Could not find chunks with the regexp: ${regexp}`);
      }
      const chunkCount = chunks.length;

      chunks = chunks
        .filter((chunk) => chunk.trim() !== "")
        .reduce((chunkResult: string[], chunk: string) => {
          let accumulatedChunk = chunkResult.pop() || "";
          let combinedChunk = `${accumulatedChunk}${chunk}`;
          if (isWithinTokenLimit(combinedChunk, MAX_TOKEN_LIMIT)) {
            chunkResult.push(combinedChunk);
          } else {
            chunkResult.push(accumulatedChunk);
            chunkResult.push(chunk);
          }
          return chunkResult;
        }, []);

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
      const discrepancy = Math.abs(chunkCount - expectedCourseCount);
      const allowedDiscrepancy =
        expectedCourseCount > 5 ? Math.floor(expectedCourseCount * 0.3) : 0;
      if (discrepancy > allowedDiscrepancy) {
        throw new Error(
          `Could not find expected number of chunks: ${chunkCount} !== ${expectedCourseCount}`
        );
      }
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

  throw new Error(
    `Failed to split chunks for ${options.url} maximum of ${maxAttempts} attempts were made.`
  );
}

export async function shouldChunk(options: DefaultLlmPageOptions) {
  const isLarge = !isWithinTokenLimit(options.content, MAX_TOKEN_LIMIT);
  if (!isLarge) {
    return false;
  }
  const hasMultipleCourses = await detectMultipleCourses(options);
  return hasMultipleCourses;
}
