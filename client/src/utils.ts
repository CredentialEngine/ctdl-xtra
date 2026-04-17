import { createTRPCReact } from "@trpc/react-query";
import type { inferRouterOutputs } from "@trpc/server";

import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

import type { AppRouter } from "../../server/src/appRouter";
export { AppRouter };

export const trpc = createTRPCReact<AppRouter>();
export type ItemType<T> = T extends (infer U)[] ? U : never;
export type RouterOutput = inferRouterOutputs<AppRouter>;
export type Catalogue = Exclude<
  RouterOutput["catalogues"]["detail"],
  undefined
>;
export type Institution = Exclude<
  RouterOutput["institutions"]["detail"],
  undefined
>;
export type Recipe = Exclude<RouterOutput["recipes"]["detail"], undefined>;
export type Extraction = Exclude<
  RouterOutput["extractions"]["detail"],
  undefined
>;
export type CrawlStep = ItemType<Extraction["crawlSteps"]>;
export type CrawlPage = ItemType<
  RouterOutput["extractions"]["stepDetail"]["crawlPages"]["results"]
>;
type DatasetItemsResponse = Exclude<RouterOutput["datasets"]["items"], null>;
export type DatasetItem = ItemType<DatasetItemsResponse["items"]["results"]>;

export {
  EmailNotificationPreference,
  ExtractionStatus,
  PageStatus,
  RecipeDetectionStatus,
  Step,
} from "../../common/types";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function prettyPrintDate(dateStr: string) {
  const date = new Date(dateStr);
  return date.toLocaleString(undefined, {
    month: "2-digit",
    day: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function concisePrintDate(dateStr: string) {
  const date = new Date(dateStr);
  return (
    date.getFullYear() +
    "-" +
    String(date.getMonth() + 1).padStart(2, "0") +
    "-" +
    String(date.getDate()).padStart(2, "0") +
    " " +
    String(date.getHours()).padStart(2, "0") +
    ":" +
    String(date.getMinutes()).padStart(2, "0")
  );
}

export function prettyPrintJson(json: Record<string, any>) {
  return JSON.stringify(json, null, "  ");
}

export async function copyToClipboard(text: string) {
  return navigator.clipboard.writeText(text);
}

export function formatCatalogueType(catalogueType: string): string {
  const typeMap: Record<string, string> = {
    COURSES: "Courses",
    LEARNING_PROGRAMS: "Learning Programs",
    COMPETENCIES: "Competencies",
    CREDENTIALS: "Credentials",
  };
  return typeMap[catalogueType] || catalogueType;
}

/**
 * Resolves a crawl page URL to an absolute URL. Relative URLs (e.g. /courses/math)
 * are resolved against the catalogue base URL so they open on the extracted
 * website rather than the app origin.
 */
export function resolveCrawlPageUrl(url: string, baseUrl: string): string {
  try {
    return new URL(url, baseUrl).href;
  } catch {
    return url;
  }
}

export type IterableElement<TargetIterable> =
  TargetIterable extends Iterable<infer ElementType>
  ? ElementType
  : TargetIterable extends AsyncIterable<infer ElementType>
  ? ElementType
  : never;
