export async function exponentialRetry<T>(
  fn: () => Promise<T>,
  retries: number,
  delay: number = 1000
) {
  let attempt = 0;
  let retryErr: unknown;
  while (attempt <= retries) {
    try {
      return await fn();
    } catch (error) {
      console.log(
        `Exponential retries fn failed with error ${error}. Details:`
      );
      console.error(error);
      console.log("Retrying...");
      retryErr = error;
      if (attempt === retries) throw error;
      await new Promise((resolve) =>
        setTimeout(resolve, delay * Math.pow(2, attempt))
      );
      attempt++;
    }
  }
  console.log("All retries failed");
  throw retryErr;
}

export async function bestOutOf<T>(
  times: number,
  fn: () => Promise<T>,
  compareWithFn: (result: T) => string
) {
  const results = new Map<string, { count: number; result: T }>();
  let bestResult: T | undefined;
  let maxCount = 0;

  for (let i = 0; i < times; i++) {
    const result = await fn();
    const compareResult = compareWithFn(result);
    const resultCount = (results.get(compareResult)?.count || 0) + 1;
    results.set(compareResult, { count: resultCount + 1, result });

    if (resultCount > maxCount) {
      maxCount = resultCount;
      bestResult = result;
    }
  }

  return bestResult as T;
}

export function unique<T>(array: T[]): T[] {
  return Array.from(new Set(array));
}

export function resolveAbsoluteUrl(base: string, relative: string): string {
  const baseUrl = new URL(base);
  const absoluteUrl = new URL(relative, baseUrl);
  return absoluteUrl.href;
}

export function buildFrontendUrl(suffix: string) {
  let baseUrl = process.env.FRONTEND_URL || "";
  if (!baseUrl.endsWith("/")) {
    baseUrl = `${baseUrl}/`;
  }
  if (suffix.startsWith("/")) {
    suffix = suffix.substring(1);
  }
  return `${baseUrl}${suffix}`;
}
