import { resolveWatchKey } from "./resolveWatchKey";

export type JobWatchLogs = {
  logs: string[];
  logCount: number;
};

/**
 * Incremental read of Bull's ephemeral `{jobKey}:logs` list. Durable log
 * retention is intentionally omitted — use an off-the-shelf logging stack
 * rather than persisting transcripts here.
 */

export async function getJobWatchLogs(
  watchKey: string,
  startLineIndex = 0
): Promise<JobWatchLogs> {
  const { queue, jobId } = await resolveWatchKey(watchKey);
  const { logs, count } = await queue.getJobLogs(jobId, startLineIndex, -1);
  return { logs, logCount: count };
}
