import { describe, expect, test } from "vitest";
import { jobStartedAtIso } from "../../src/jobWatching";

describe("jobStartedAtIso", () => {
  test("returns null while the job has not been processed", () => {
    expect(jobStartedAtIso(undefined)).toBeNull();
    expect(jobStartedAtIso(null)).toBeNull();
  });

  test("returns the process-start time, not enqueue time", () => {
    const processedOn = Date.UTC(2026, 7, 27, 12, 0, 0);
    expect(jobStartedAtIso(processedOn)).toBe("2026-08-27T12:00:00.000Z");
  });
});
