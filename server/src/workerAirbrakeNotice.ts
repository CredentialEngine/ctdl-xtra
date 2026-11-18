export type WorkerCatchContext = {
  extractionId?: number;
  crawlPageId?: number;
  datasetId?: number;
  url?: string;
  responseStatus?: number;
  jobName?: string;
  /** Raw proxy endpoint when the failing fetch used a proxy. */
  proxyUrl?: string;
  /** Present when the failing fetch was a direct (non-proxy) browser request. */
  directConnection?: boolean;
};

export function redactProxyUrlForAirbrake(proxyUrl: string): string {
  try {
    const url = new URL(proxyUrl);
    if (url.password) {
      url.password = "redacted";
    }
    return url.toString();
  } catch {
    return "(invalid-url)";
  }
}

export type WorkerAirbrakeCatchInput = {
  error: unknown;
} & WorkerCatchContext;

const workerCatchContextKey = Symbol("workerAirbrakeCatchContext");

export function attachWorkerCatchContext(
  error: unknown,
  context: WorkerCatchContext
): void {
  if (typeof error !== "object" || error === null) {
    return;
  }
  const record = error as Record<typeof workerCatchContextKey, WorkerCatchContext>;
  record[workerCatchContextKey] = {
    ...record[workerCatchContextKey],
    ...context,
  };
}

export function getWorkerCatchContext(error: unknown): WorkerCatchContext {
  if (typeof error !== "object" || error === null) {
    return {};
  }
  return (
    (error as Record<typeof workerCatchContextKey, WorkerCatchContext>)[
      workerCatchContextKey
    ] ?? {}
  );
}

export function extractionFieldsFromJobData(
  data: unknown
): WorkerCatchContext {
  if (!data || typeof data !== "object") {
    return {};
  }
  const record = data as Record<string, unknown>;
  const fields: WorkerCatchContext = {};

  if (typeof record.extractionId === "number") {
    fields.extractionId = record.extractionId;
  }
  if (typeof record.crawlPageId === "number") {
    fields.crawlPageId = record.crawlPageId;
  }
  if (typeof record.datasetId === "number") {
    fields.datasetId = record.datasetId;
  }

  return fields;
}

function airbrakeParams(context: WorkerCatchContext): Record<string, number | string> {
  const params: Record<string, number | string> = {};
  if (context.extractionId != null) {
    params.extractionId = context.extractionId;
  }
  if (context.crawlPageId != null) {
    params.crawlPageId = context.crawlPageId;
  }
  if (context.datasetId != null) {
    params.datasetId = context.datasetId;
  }
  if (context.url != null) {
    params.url = context.url;
  }
  if (context.responseStatus != null) {
    params.responseStatus = context.responseStatus;
  }
  if (context.directConnection) {
    params.proxyUsed = "direct";
  } else if (context.proxyUrl) {
    params.proxyUsed = redactProxyUrlForAirbrake(context.proxyUrl);
  }
  return params;
}

export function buildWorkerAirbrakeNotice(input: WorkerAirbrakeCatchInput) {
  const { error, jobName, ...rest } = input;
  const context: WorkerCatchContext = { ...rest, jobName };

  const notice: {
    error: unknown;
    context: Record<string, unknown>;
    params?: Record<string, unknown>;
  } = {
    error,
    context: {
      component: "worker",
    },
  };

  if (jobName) {
    notice.context.jobName = jobName;
  }

  const params = airbrakeParams(context);
  if (Object.keys(params).length > 0) {
    notice.params = params;
  }

  return notice;
}

export function workerAirbrakeInputForJobFailure(
  error: unknown,
  jobData: unknown,
  jobName?: string
): WorkerAirbrakeCatchInput {
  return {
    error,
    ...extractionFieldsFromJobData(jobData),
    ...getWorkerCatchContext(error),
    ...(jobName ? { jobName } : {}),
  };
}