export type ProgressJob = {
  progress: unknown;
  updateProgress: (value: object) => Promise<void>;
};

/**
 * Merge a small replaceable snapshot onto `job.progress`. Do not store log
 * text here — use `publicLog` for append-only user-visible output.
 */
export async function mergeJobProgress(
  job: ProgressJob,
  patch: Record<string, unknown>
): Promise<void> {
  const current =
    job.progress &&
    typeof job.progress === "object" &&
    !Array.isArray(job.progress)
      ? (job.progress as Record<string, unknown>)
      : {};
  await job.updateProgress({ ...current, ...patch });
}
