import { Job, Queue } from "bullmq";
import { AppError, AppErrors } from "../appErrors";
import { Queues } from "../workers";
import { parseWatchKey } from "./parseWatchKey";

export type ResolvedWatchKey = {
  queue: Queue;
  queueName: string;
  jobId: string;
  job: Job;
};

function findQueue(queueName: string): Queue | undefined {
  return Object.values(Queues).find((queue) => queue.name === queueName);
}

export async function resolveWatchKey(
  watchKey: string
): Promise<ResolvedWatchKey> {
  const { queueName, jobId } = parseWatchKey(watchKey);
  const queue = findQueue(queueName);
  if (!queue) {
    throw new AppError("Unknown job queue in watch key", AppErrors.NOT_FOUND);
  }
  const job = await queue.getJob(jobId);
  if (!job) {
    throw new AppError("Job not found", AppErrors.NOT_FOUND);
  }
  return { queue, queueName, jobId, job };
}
