/**
 * Standalone script to submit BullMQ jobs to a custom Redis instance.
 * Useful for unsticking extractions in production.
 *
 * Usage:
 *   REDIS_URL="redis://your-production-redis:6379" node submitBullMqJob.js <command> [options]
 *
 * Commands:
 *   update-completion <extractionId>  - Submit a repeatable job to update extraction completion
 *   fetch-page <crawlPageId> <extractionId> <datasetId> - Submit a fetch page job
 *   extract-data <crawlPageId> <extractionId> <datasetId> - Submit an extract data job
 *   list-jobs <queueName> - List jobs in a queue (waiting, active, delayed)
 *   remove-repeatable <queueName> <jobId> - Remove a repeatable job
 *
 * Examples:
 *   REDIS_URL="redis://prod:6379" node submitBullMqJob.js update-completion 123
 *   REDIS_URL="redis://prod:6379" node submitBullMqJob.js list-jobs extractions.updateExtractionCompletion
 *   REDIS_URL="redis://prod:6379" node submitBullMqJob.js remove-repeatable extractions.updateExtractionCompletion updateExtractionCompletion.123
 */

const { Queue } = require("bullmq");
const IORedis = require("ioredis").default;

const REDIS_URL = process.env.REDIS_URL || "redis://localhost:6379";
const REPEAT_UPDATE_COMPLETION_EVERY_MS = 2 * 60 * 1000; // 2 minutes

// Queue names matching server/src/workers/index.ts
const QUEUE_NAMES = {
  DetectConfiguration: "recipes.detectConfiguration",
  FetchPage: "extractions.fetchPage",
  ExtractData: "extractions.extractData",
  ExtractDataWithAPI: "extractions.extractDataWithApi",
  UpdateExtractionCompletion: "extractions.updateExtractionCompletion",
};

const defaultJobOptions = {
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

function getConnection() {
  console.log(`Connecting to Redis: ${REDIS_URL}`);
  const connection = new IORedis(REDIS_URL, { maxRetriesPerRequest: null });
  connection.setMaxListeners(30);
  return connection;
}

function createQueue(queueName, connection) {
  return new Queue(queueName, {
    connection,
    defaultJobOptions,
  });
}

async function submitRepeatableJob(queue, data, jobId, repeat) {
  const name = `${queue.name}.default`;
  console.log(`Submitting repeatable job: ${name} with jobId: ${jobId}`);
  console.log(`Data:`, JSON.stringify(data, null, 2));
  console.log(`Repeat options:`, JSON.stringify(repeat, null, 2));
  return queue.add(name, data, { jobId, repeat });
}

async function submitJob(queue, data, jobId, priority = 100) {
  const name = `${queue.name}.default`;
  console.log(`Submitting job: ${name} with jobId: ${jobId}`);
  console.log(`Data:`, JSON.stringify(data, null, 2));
  return queue.add(name, data, { jobId, priority });
}

async function listJobs(queue) {
  const states = ["active", "waiting", "delayed", "prioritized", "repeat"];
  console.log(`\nListing jobs in queue: ${queue.name}`);

  for (const state of states) {
    const jobs = await queue.getJobs([state], 0, 50);
    if (jobs.length > 0) {
      console.log(`\n--- ${state.toUpperCase()} (${jobs.length}) ---`);
      for (const job of jobs) {
        console.log(`  ID: ${job.id}`);
        console.log(`  Name: ${job.name}`);
        console.log(`  Data: ${JSON.stringify(job.data)}`);
        if (job.opts?.repeat) {
          console.log(`  Repeat: ${JSON.stringify(job.opts.repeat)}`);
        }
        console.log("");
      }
    }
  }

  // List repeatable jobs specifically
  const repeatableJobs = await queue.getRepeatableJobs();
  if (repeatableJobs.length > 0) {
    console.log(`\n--- REPEATABLE JOBS (${repeatableJobs.length}) ---`);
    for (const job of repeatableJobs) {
      console.log(`  Key: ${job.key}`);
      console.log(`  Name: ${job.name}`);
      console.log(`  ID: ${job.id}`);
      console.log(`  Every: ${job.every}ms`);
      console.log(`  Next: ${new Date(job.next).toISOString()}`);
      console.log("");
    }
  }
}

async function removeRepeatableJob(queue, jobId) {
  const repeatableJobs = await queue.getRepeatableJobs();
  const job = repeatableJobs.find((j) => j.id === jobId || j.key.includes(jobId));

  if (job) {
    console.log(`Removing repeatable job: ${job.key}`);
    await queue.removeRepeatableByKey(job.key);
    console.log("Removed successfully");
  } else {
    console.log(`No repeatable job found matching: ${jobId}`);
    console.log("Available repeatable jobs:");
    for (const j of repeatableJobs) {
      console.log(`  - ${j.key} (id: ${j.id})`);
    }
  }
}

async function main() {
  const args = process.argv.slice(2);
  const command = args[0];

  if (!command) {
    console.log("Usage: node submitBullMqJob.js <command> [options]");
    console.log("\nCommands:");
    console.log("  update-completion <extractionId>  - Submit repeatable job for extraction completion");
    console.log("  fetch-page <crawlPageId> <extractionId> <datasetId> - Submit fetch page job");
    console.log("  extract-data <crawlPageId> <extractionId> <datasetId> - Submit extract data job");
    console.log("  list-jobs <queueName> - List jobs in a queue");
    console.log("  remove-repeatable <queueName> <jobId> - Remove a repeatable job");
    console.log("\nQueue names:");
    Object.entries(QUEUE_NAMES).forEach(([key, value]) => {
      console.log(`  ${key}: ${value}`);
    });
    console.log("\nSet REDIS_URL env var to connect to a different Redis instance.");
    process.exit(1);
  }

  const connection = getConnection();

  try {
    switch (command) {
      case "update-completion": {
        const extractionId = parseInt(args[1], 10);
        if (isNaN(extractionId)) {
          console.error("Error: extractionId must be a number");
          process.exit(1);
        }

        const queue = createQueue(QUEUE_NAMES.UpdateExtractionCompletion, connection);
        const jobId = `updateExtractionCompletion.${extractionId}`;
        const job = await submitRepeatableJob(
          queue,
          { extractionId },
          jobId,
          { every: REPEAT_UPDATE_COMPLETION_EVERY_MS }
        );
        console.log(`\nJob submitted successfully!`);
        console.log(`Job ID: ${job.id}`);
        break;
      }

      case "fetch-page": {
        const crawlPageId = parseInt(args[1], 10);
        const extractionId = parseInt(args[2], 10);
        const datasetId = parseInt(args[3], 10);

        if (isNaN(crawlPageId) || isNaN(extractionId) || isNaN(datasetId)) {
          console.error("Error: crawlPageId, extractionId, and datasetId must be numbers");
          process.exit(1);
        }

        const queue = createQueue(QUEUE_NAMES.FetchPage, connection);
        const jobId = `fetchPage.${crawlPageId}`;
        const job = await submitJob(queue, { crawlPageId, extractionId, datasetId }, jobId);
        console.log(`\nJob submitted successfully!`);
        console.log(`Job ID: ${job.id}`);
        break;
      }

      case "extract-data": {
        const crawlPageId = parseInt(args[1], 10);
        const extractionId = parseInt(args[2], 10);
        const datasetId = parseInt(args[3], 10);

        if (isNaN(crawlPageId) || isNaN(extractionId) || isNaN(datasetId)) {
          console.error("Error: crawlPageId, extractionId, and datasetId must be numbers");
          process.exit(1);
        }

        const queue = createQueue(QUEUE_NAMES.ExtractData, connection);
        const jobId = `extractData.${crawlPageId}`;
        const job = await submitJob(queue, { crawlPageId, extractionId, datasetId }, jobId);
        console.log(`\nJob submitted successfully!`);
        console.log(`Job ID: ${job.id}`);
        break;
      }

      case "list-jobs": {
        const queueName = args[1];
        if (!queueName) {
          console.error("Error: queueName is required");
          console.log("Available queues:", Object.values(QUEUE_NAMES).join(", "));
          process.exit(1);
        }

        const queue = createQueue(queueName, connection);
        await listJobs(queue);
        break;
      }

      case "remove-repeatable": {
        const queueName = args[1];
        const jobId = args[2];

        if (!queueName || !jobId) {
          console.error("Error: queueName and jobId are required");
          process.exit(1);
        }

        const queue = createQueue(queueName, connection);
        await removeRepeatableJob(queue, jobId);
        break;
      }

      default:
        console.error(`Unknown command: ${command}`);
        process.exit(1);
    }
  } finally {
    await connection.quit();
    console.log("\nConnection closed.");
  }
}

main().catch((err) => {
  console.error("Error:", err);
  process.exit(1);
});
