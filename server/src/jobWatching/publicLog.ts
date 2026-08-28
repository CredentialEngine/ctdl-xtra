/**
 * ⚠️ WARNING — `publicLog` output is user-visible. Anything passed here is
 * stored in Bull job logs and returned to authenticated users via
 * `jobWatching.logs`. Never log secrets, tokens, raw HTML with PII, internal
 * URLs/credentials, etc. Use private `logger` calls for operator-only detail.
 */

export type PublicLoggableJob = {
  id?: string;
  log: (row: string) => Promise<number> | void;
};

export type PublicLogLogger = {
  info: (obj: object, msg?: string) => void;
};

export async function publicLog(
  job: PublicLoggableJob,
  logger: PublicLogLogger,
  message: string
): Promise<void> {
  await job.log(message);
  logger.info({ jobId: job.id }, message);
}
