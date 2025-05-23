import { Queue, Worker } from "bullmq";
import "dotenv/config";
import path from "path";
import getLogger from "./logging";
import { Queues, startProcessor } from "./workers";

const logger = getLogger("worker");

// @ts-ignore
const workerExtension = process._preload_modules.some((s) => s.includes("tsx"))
  ? "ts"
  : "js";

const workers: Worker[] = [];

let shuttingDown = false;

async function handleShutdown() {
  if (shuttingDown) {
    return;
  }
  shuttingDown = true;
  for (const worker of workers) {
    logger.info(`Shutting down worker ${worker.name}`);
    await worker.close();
  }
  process.exit(0);
}

function processorPath(name: string) {
  return path.join(__dirname, "workers", `${name}.${workerExtension}`);
}

const processors: [Queue, string, number][] = [
  [Queues.DetectConfiguration, processorPath("detectConfiguration"), 2],
  [Queues.FetchPage, processorPath("fetchPage"), 2],
  [Queues.ExtractData, processorPath("extractData"), 2],
  [Queues.ExtractDataWithAPI, processorPath("extractDataWithApi"), 2],
  [
    Queues.UpdateExtractionCompletion,
    processorPath("updateExtractionCompletion"),
    10,
  ],
];

for (const [queue, processor, localConcurrency] of processors) {
  const worker = startProcessor(queue, processor, localConcurrency);
  worker.on("error", (err) => logger.error(err));
  worker.on("failed", (_job, err) => logger.error(err));
  worker.on("progress", (_job, progress) => logger.info(progress));
  workers.push(worker);
}

process.on("SIGINT", handleShutdown);
process.on("SIGTERM", handleShutdown);
