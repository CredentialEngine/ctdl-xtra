import { expect, describe, it } from "vitest";

describe("embeddings", () => {
  it("test cosine similarity between two texts", async () => {
    const textA = "By utilizing biology, chemistry and engineering principles, learn to create extremely small electronic and mechanical devices.";
    const textB = "Using biology, chemistry and engineering ideas, learn to create extremely small electronic and mechanical devices.";

    await expect(textA).toBeSimilarEmbedding(textB, 0.85);
  });

  // Testing expect.toBeSimilarEmbedding does not currently work because
  // Vitest does not await on the matcher result. Once Vitest supports async matchers,
  // we can remove the .skip and test this.
  it.skip('test consine similarity between two objects', async () => {
    const objA = {
      title: "By utilizing biology, chemistry and engineering principles, learn to create extremely small electronic and mechanical devices.",
      description: "Using biology, chemistry and engineering ideas, learn to create extremely small electronic and mechanical devices.",
    };

    await expect(objA).toEqual({
      title: await expect.toBeSimilarEmbedding("Using biology, chemistry and engineering ideas, learn to create extremely small electronic and mechanical devices.", 0.85),
      description: await expect.toBeSimilarEmbedding("Using biology, chemistry and engineering ideas, learn to create extremely small electronic and mechanical devices.", 0.85),
    })
  });
});
