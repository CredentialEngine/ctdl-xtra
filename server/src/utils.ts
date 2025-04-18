import { get } from 'fast-levenshtein';

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

/**
 * Checks if two strings are similar enough based on Levenshtein distance percentage
 * @param str1 First string to compare
 * @param str2 Second string to compare
 * @param threshold Maximum allowed difference as a percentage (default: 80%)
 * @returns true if the strings are similar enough, false otherwise
 */
export function isSimilar(str1: string, str2: string, threshold: number = 0.8): boolean {
  const distance = get(str1, str2);
  const maxLength = Math.max(str1.length, str2.length);
  const differencePercentage = distance / maxLength;
  return differencePercentage <= threshold;
}

/**
 * Checks if two objects are similar by doing a deep comparison
 * For string values, uses string similarity
 * For other values, uses strict equality
 * @param obj1 First object to compare
 * @param obj2 Second object to compare
 * @param similarityThreshold Maximum allowed difference as a percentage (default: 0.8)
 * @returns true if the objects are similar enough, false otherwise
 */
export function isObjectSimilar(
  obj1: Record<string, any>,
  obj2: Record<string, any>,
  similarityThreshold: number = 0.8
): boolean {
  // Get all unique keys from both objects
  const keys = new Set([...Object.keys(obj1), ...Object.keys(obj2)]);
  
  for (const key of keys) {
    const val1 = obj1[key];
    const val2 = obj2[key];

    // If one object has the key and the other doesn't, they're not similar
    if ((val1 === undefined) !== (val2 === undefined)) {
      return false;
    }

    // Skip if both values are undefined
    if (val1 === undefined && val2 === undefined) {
      continue;
    }

    // For string values, use string similarity
    if (typeof val1 === 'string' && typeof val2 === 'string') {
      if (!isSimilar(val1, val2, similarityThreshold)) {
        return false;
      }
    }
    // For arrays, compare each element
    else if (Array.isArray(val1) && Array.isArray(val2)) {
      if (val1.length !== val2.length) {
        return false;
      }
      for (let i = 0; i < val1.length; i++) {
        if (typeof val1[i] === 'object' && typeof val2[i] === 'object') {
          if (!isObjectSimilar(val1[i], val2[i], similarityThreshold)) {
            return false;
          }
        } else if (typeof val1[i] === 'string' && typeof val2[i] === 'string') {
          if (!isSimilar(val1[i], val2[i], similarityThreshold)) {
            return false;
          }
        } else if (val1[i] !== val2[i]) {
          return false;
        }
      }
    }
    // For nested objects, do recursive comparison
    else if (typeof val1 === 'object' && typeof val2 === 'object' && val1 !== null && val2 !== null) {
      if (!isObjectSimilar(val1, val2, similarityThreshold)) {
        return false;
      }
    }
    // For all other types, use strict equality
    else if (val1 !== val2) {
      return false;
    }
  }

  return true;
}

/**
 * Deduplicates an array of items based on their similarity
 * @param items Array of items to deduplicate
 * @param similarityThreshold Maximum allowed difference as a percentage (default: 0.8)
 * @returns Deduplicated array of items
 */
export function deduplicateSimilarItems<T extends Record<string, any>>(
  items: T[],
  similarityThreshold: number = 0.8
): T[] {
  const uniqueItems: T[] = [];

  for (const item of items) {
    // Check if this item is similar to any previously seen item
    const isDuplicate = uniqueItems.some(
      (uniqueItem) => isObjectSimilar(item, uniqueItem, similarityThreshold)
    );

    if (!isDuplicate) {
      uniqueItems.push(item);
    }
  }

  return uniqueItems;
}
