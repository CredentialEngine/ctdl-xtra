import { AppError, AppErrors } from "../appErrors";
import { Queues } from "../workers";

export type ParsedWatchKey = {
  queueName: string;
  jobId: string;
};

export function toWatchKey(queueName: string, jobId: string): string {
  return `${queueName}.${jobId}`;
}

export function toWatchRef(queue: { name: string }, jobId: string) {
  return {
    queueName: queue.name,
    jobId,
    watchKey: toWatchKey(queue.name, jobId),
  };
}

function queueNames(): string[] {
  return Object.values(Queues)
    .map((queue) => queue.name)
    .sort((a, b) => b.length - a.length);
}

/**
 * Split `{queueName}.{jobId}` using a longest-prefix match against existing
 * `Queues` names. `jobId` may itself contain dots.
 */
export function parseWatchKey(watchKey: string): ParsedWatchKey {
  const trimmed = watchKey.trim();
  const names = queueNames();
  if (
    names.some(
      (queueName) => trimmed === queueName || trimmed === `${queueName}.`
    )
  ) {
    throw new AppError("Watch key is missing a job id", AppErrors.NOT_FOUND);
  }
  for (const queueName of names) {
    const prefix = `${queueName}.`;
    if (!trimmed.startsWith(prefix)) {
      continue;
    }
    const jobId = trimmed.slice(prefix.length);
    if (!jobId) {
      throw new AppError("Watch key is missing a job id", AppErrors.NOT_FOUND);
    }
    return { queueName, jobId };
  }
  throw new AppError("Unknown job queue in watch key", AppErrors.NOT_FOUND);
}
