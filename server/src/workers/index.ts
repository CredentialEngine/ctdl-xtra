import * as Airbrake from "@airbrake/node";
import {
  BulkJobOptions,
  DefaultJobOptions,
  JobsOptions,
  Queue,
  RepeatOptions,
  SandboxedJob,
  Worker,
} from "bullmq";
import { default as IORedis } from "ioredis";
import { closeCluster } from "../extraction/browser";
import getLogger from "../logging";

const logger = getLogger("workers");
const REDIS_URL = process.env.REDIS_URL || "redis://localhost:6379";
export const REPEAT_UPDATE_COMPLETION_EVERY_MS = 2 * 60 * 1000;

export function getRedisConnection() {
  const connection = new IORedis(REDIS_URL, { maxRetriesPerRequest: null });
  connection.setMaxListeners(30);
  return connection;
}

export interface BaseProgress {
  status?: "info" | "success" | "failure";
  message: string;
}

export interface JobWithProgress<T, K extends BaseProgress>
  extends SandboxedJob<T> {
  updateProgress(value: object | number): Promise<void>;
  updateProgress(value: K): Promise<void>;
}

export type Processor<T, K extends BaseProgress, L = any> = (
  job: JobWithProgress<T, K>
) => Promise<L>;

export const createProcessor = <T, K extends BaseProgress>(
  fn: Processor<T, K>
) => {
  process.on("SIGTERM", async () => {
    logger.info(`Shutting down ${fn.name}`);
    closeCluster();
  });

  let airbrake: Airbrake.Notifier | null = null;
  if (process.env.AIRBRAKE_PROJECT_ID && process.env.AIRBRAKE_PROJECT_KEY) {
    airbrake = new Airbrake.Notifier({
      projectId: parseInt(process.env.AIRBRAKE_PROJECT_ID),
      projectKey: process.env.AIRBRAKE_PROJECT_KEY,
    });
  }

  return async (job: JobWithProgress<T, K>) => {
    try {
      await fn(job);
    } catch (error) {
      if (airbrake) {
        await airbrake.notify(error);
      }
      throw error;
    }
  };
};

export async function submitJob<T, K extends T>(
  queue: Queue<T>,
  data: K,
  jobId: string,
  priority?: number
) {
  const name = `${queue.name}.default`;
  return queue.add(name, data, { jobId, priority: priority || 100 });
}

export async function submitJobWithOpts<T, K extends T>(
  queue: Queue<T>,
  data: K,
  opts: JobsOptions
) {
  const name = `${queue.name}.default`;
  return queue.add(name, data, opts);
}

export async function submitRepeatableJob<T, K extends T>(
  queue: Queue<T>,
  data: K,
  jobId: string,
  repeat: RepeatOptions
) {
  const name = `${queue.name}.default`;
  return queue.add(name, data, { jobId, repeat });
}

export interface SubmitJobsItem<K> {
  data: K;
  options: BulkJobOptions & { jobId: string };
}

export interface DelayOptions {
  delayInterval: number;
  startWithDelay: number;
}

export async function submitJobs<T, K extends T>(
  queue: Queue<T>,
  jobs: SubmitJobsItem<K>[],
  delayOptions?: DelayOptions
) {
  const name = `${queue.name}.default`;

  const bulkJobs = [];
  let delay = delayOptions?.startWithDelay || undefined;
  logger.info(
    `[Batch starting with ${jobs[0].options.jobId}] Delay interval ${delayOptions?.delayInterval}`
  );
  for (const job of jobs) {
    bulkJobs.push({
      name,
      data: job.data,
      opts: {
        ...job.options,
        delay,
      },
    });
    if (delay && delayOptions?.delayInterval) {
      delay += delayOptions.delayInterval + 1000;
    }
  }

  return queue.addBulk(bulkJobs);
}

export function startProcessor<T>(
  queue: Queue<T>,
  processor: string,
  localConcurrency: number = 1
) {
  const worker = new Worker(queue.name, processor, {
    connection: getRedisConnection(),
    useWorkerThreads: false,
    concurrency: localConcurrency,
  });
  return worker;
}

export interface DetectConfigurationJob {
  recipeId: number;
}

export interface FetchPageJob {
  crawlPageId: number;
  extractionId: number;
}

export interface ExtractDataJob {
  crawlPageId: number;
  extractionId: number;
}

export interface UpdateExtractionCompletionJob {
  extractionId: number;
}

export interface DetectConfigurationProgress extends BaseProgress {}
export interface FetchPageProgress extends BaseProgress {}
export interface ExtractDataProgress extends BaseProgress {}
export interface UpdateExtractionCompletionProgress extends BaseProgress {}

const connection = getRedisConnection();

const defaultJobOptions: DefaultJobOptions = {
  attempts: 3,
  backoff: {
    type: "exponential",
    delay: 1000,
  },
  removeOnComplete: true,
  removeOnFail: {
    age: 1000 * 60 * 60 * 24 * 5, // 5 days
  },
};

export async function detectExtractionJobs(extractionId: number) {
  const queues = [
    Queues.FetchPage,
    Queues.ExtractData,
    Queues.ExtractDataWithAPI,
  ];
  for (const queue of queues) {
    let start = 0,
      end = 100;
    while (true) {
      const jobs = await queue.getJobs(
        ["active", "waiting", "delayed", "prioritized", "repeat", "wait"],
        start,
        end
      );
      if (jobs.length === 0) {
        break;
      }
      for (const job of jobs) {
        if (job.data.extractionId === extractionId) {
          return true;
        }
      }
      start = end;
    }
  }
  return false;
}

export const Queues = {
  DetectConfiguration: new Queue<DetectConfigurationJob>(
    "recipes.detectConfiguration",
    {
      connection,
      defaultJobOptions,
    }
  ),
  FetchPage: new Queue<FetchPageJob>("extractions.fetchPage", {
    connection,
    defaultJobOptions,
  }),
  ExtractData: new Queue<ExtractDataJob>("extractions.extractData", {
    connection,
    defaultJobOptions,
  }),
  ExtractDataWithAPI: new Queue<ExtractDataJob>(
    "extractions.extractDataWithApi",
    {
      connection,
      defaultJobOptions,
    }
  ),
  UpdateExtractionCompletion: new Queue<UpdateExtractionCompletionJob>(
    "extractions.updateExtractionCompletion",
    {
      connection,
      defaultJobOptions,
    }
  ),
};
