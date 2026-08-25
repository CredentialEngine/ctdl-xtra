import { beforeEach, describe, expect, test, vi } from "vitest";
import { getJobWatchLogs } from "../../src/jobWatching/getJobWatchLogs";
import { resolveWatchKey } from "../../src/jobWatching/resolveWatchKey";

vi.mock("../../src/jobWatching/resolveWatchKey", () => ({
  resolveWatchKey: vi.fn(),
}));

const mockedResolveWatchKey = vi.mocked(resolveWatchKey);
const getJobLogs = vi.fn();
const ALL_LOGS = ["line0", "line1", "line2"];

describe("getJobWatchLogs", () => {
  beforeEach(() => {
    getJobLogs.mockReset();
    mockedResolveWatchKey.mockReset();
    mockedResolveWatchKey.mockResolvedValue({
      queue: { getJobLogs },
      queueName: "recipes.agenticRecipeConfig",
      jobId: "agenticRecipeConfig.42",
      job: {},
    } as unknown as Awaited<ReturnType<typeof resolveWatchKey>>);
    getJobLogs.mockImplementation(async (_jobId: string, start: number) => {
      return {
        logs: start >= ALL_LOGS.length ? [] : ALL_LOGS.slice(start),
        count: ALL_LOGS.length,
      };
    });
  });

  test("returns all lines from the start", async () => {
    await expect(getJobWatchLogs("watch-key", 0)).resolves.toEqual({
      logs: ["line0", "line1", "line2"],
      logCount: 3,
    });
    expect(getJobLogs).toHaveBeenCalledWith(
      "agenticRecipeConfig.42",
      0,
      -1
    );
  });

  test("returns new lines from a cursor", async () => {
    await expect(getJobWatchLogs("watch-key", 2)).resolves.toEqual({
      logs: ["line2"],
      logCount: 3,
    });
  });

  test("returns an empty slice when the cursor is at the end", async () => {
    await expect(getJobWatchLogs("watch-key", 3)).resolves.toEqual({
      logs: [],
      logCount: 3,
    });
  });
});
