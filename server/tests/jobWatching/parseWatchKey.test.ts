import { describe, expect, test } from "vitest";
import { AppError, AppErrors } from "../../src/appErrors";
import { parseWatchKey, toWatchKey } from "../../src/jobWatching";
import { Queues } from "../../src/workers";

describe("parseWatchKey", () => {
  test("splits an agentic recipe watch key whose jobId contains dots", () => {
    const jobId = "agenticRecipeConfig.42";
    const watchKey = toWatchKey(Queues.AgenticRecipeConfig.name, jobId);
    expect(watchKey).toBe(
      "recipes.agenticRecipeConfig.agenticRecipeConfig.42"
    );
    expect(parseWatchKey(watchKey)).toEqual({
      queueName: Queues.AgenticRecipeConfig.name,
      jobId,
    });
  });

  test("splits a detect-configuration watch key", () => {
    const jobId = "detectConfiguration.7";
    expect(
      parseWatchKey(toWatchKey(Queues.DetectConfiguration.name, jobId))
    ).toEqual({
      queueName: Queues.DetectConfiguration.name,
      jobId,
    });
  });

  test("does not match a shorter queue name prefix of another queue", () => {
    const jobId = "page-1";
    const watchKey = toWatchKey(Queues.ExtractDataWithAPI.name, jobId);
    expect(parseWatchKey(watchKey)).toEqual({
      queueName: Queues.ExtractDataWithAPI.name,
      jobId,
    });
  });

  test("uses the longest matching queue name", () => {
    const names = Object.values(Queues).map((queue) => queue.name);
    const longest = [...names].sort((a, b) => b.length - a.length)[0];
    const jobId = "job.with.dots";
    expect(parseWatchKey(`${longest}.${jobId}`)).toEqual({
      queueName: longest,
      jobId,
    });
  });

  test("rejects an unknown queue name", () => {
    try {
      parseWatchKey("not.a.queue.job-1");
      throw new Error("expected parseWatchKey to throw");
    } catch (error) {
      expect(error).toBeInstanceOf(AppError);
      expect((error as AppError).code).toBe(AppErrors.NOT_FOUND);
    }
  });

  test("rejects a queue name with an empty job id", () => {
    try {
      parseWatchKey(`${Queues.AgenticRecipeConfig.name}.`);
      throw new Error("expected parseWatchKey to throw");
    } catch (error) {
      expect(error).toBeInstanceOf(AppError);
      expect((error as AppError).code).toBe(AppErrors.NOT_FOUND);
    }
  });

  test("rejects a longer queue name that would otherwise match a shorter prefix", () => {
    try {
      parseWatchKey(Queues.ExtractDataWithAPI.name);
      throw new Error("expected parseWatchKey to throw");
    } catch (error) {
      expect(error).toBeInstanceOf(AppError);
      expect((error as AppError).code).toBe(AppErrors.NOT_FOUND);
    }
  });
});
