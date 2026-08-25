import { describe, expect, test } from "vitest";
import { mergeJobProgress } from "../../src/jobWatching";

describe("mergeJobProgress", () => {
  test("merges a patch onto an object snapshot", async () => {
    const job = {
      progress: { message: "old", status: "info" } as Record<string, unknown>,
      updateProgress: async (value: object) => {
        job.progress = value as Record<string, unknown>;
      },
    };

    await mergeJobProgress(job, { message: "new", step: 2 });

    expect(job.progress).toEqual({
      message: "new",
      status: "info",
      step: 2,
    });
  });

  test("replaces a numeric progress value", async () => {
    const job = {
      progress: 50 as unknown,
      updateProgress: async (value: object) => {
        job.progress = value;
      },
    };

    await mergeJobProgress(job, { message: "started" });

    expect(job.progress).toEqual({ message: "started" });
  });
});
