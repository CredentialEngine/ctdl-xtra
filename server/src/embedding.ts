import { getOpenAi } from "./openai";

/**
 * Compute the embedding vector for a given text using OpenAI's embeddings API.
 * Defaults to the `text-embedding-3-small` model.
 *
 * @param text Text to embed
 * @param model OpenAI embeddings model name (default: "text-embedding-3-small")
 * @returns The embedding vector as an array of numbers
 */
export async function computeEmbedding(
  text: string,
  model: string = "text-embedding-3-small"
): Promise<{ embedding: number[], usedTokens: number }> {
  const openai = await getOpenAi();
  const response = await openai.embeddings.create({
    model,
    input: text,
  });

  const embedding = response.data[0]?.embedding;
  if (!embedding || !Array.isArray(embedding)) {
    throw new Error("Failed to retrieve embedding from OpenAI response");
  }
  return { embedding: embedding as number[], usedTokens: response.usage?.total_tokens };
} 