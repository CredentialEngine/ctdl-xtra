import { resolveWatchKey } from "./resolveWatchKey";

export type JobWatchStatus = {
  watchKey: string;
  queueName: string;
  jobId: string;
  state: string;
  progress: unknown;
  startedAt: string | null;
};

export const TERMINAL_JOB_STATES = new Set(["completed", "failed"]);

export function isTerminalJobState(state: string): boolean {
  return TERMINAL_JOB_STATES.has(state);
}

/** ISO time the worker started the job; null while still waiting. */
export function jobStartedAtIso(
  processedOn: number | null | undefined
): string | null {
  return processedOn ? new Date(processedOn).toISOString() : null;
}

export async function getJobWatchStatus(
  watchKey: string
): Promise<JobWatchStatus> {
  const { queueName, jobId, job } = await resolveWatchKey(watchKey);
  const state = await job.getState();
  return {
    watchKey,
    queueName,
    jobId,
    state,
    progress: job.progress ?? null,
    startedAt: jobStartedAtIso(job.processedOn),
  };
}
