import { Queue, Worker } from "bullmq";
import "dotenv/config";
import path from "path";
import { Queues, startProcessor } from "./workers";

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
    console.log(`Shutting down worker ${worker.name}`);
    await worker.close();
  }
  process.exit(0);
}

function processorPath(name: string) {
  return path.join(__dirname, "workers", `${name}.${workerExtension}`);
}

const processors: [Queue, string, number][] = [
  [Queues.DetectConfiguration, processorPath("detectConfiguration"), 2],
  [Queues.FetchPage, processorPath("fetchPage"), 3],
  [Queues.ExtractData, processorPath("extractData"), 10],
  [Queues.ExtractDataWithAPI, processorPath("extractDataWithApi"), 10],
  [
    Queues.UpdateExtractionCompletion,
    processorPath("updateExtractionCompletion"),
    10,
  ],
];

for (const [queue, processor, localConcurrency] of processors) {
  const worker = startProcessor(queue, processor, localConcurrency);
  worker.on("error", (err) => console.log(err));
  worker.on("failed", (_job, err) => console.log(err));
  worker.on("progress", (_job, progress) => console.log(progress));
  workers.push(worker);
}

process.on("SIGINT", handleShutdown);
process.on("SIGTERM", handleShutdown);
