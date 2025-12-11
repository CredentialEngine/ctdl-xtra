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

export enum ExtractionStatus {
  WAITING = "WAITING",
  IN_PROGRESS = "IN_PROGRESS",
  COMPLETE = "COMPLETE",
  STALE = "STALE",
  CANCELLED = "CANCELLED",
}

export enum PageStatus {
  WAITING = "WAITING",
  IN_PROGRESS = "IN_PROGRESS",
  SUCCESS = "SUCCESS",
  ERROR = "ERROR",
}

export enum RecipeDetectionStatus {
  WAITING = "WAITING",
  IN_PROGRESS = "IN_PROGRESS",
  SUCCESS = "SUCCESS",
  ERROR = "ERROR",
}

export enum Step {
  FETCH_ROOT = "FETCH_ROOT",
  FETCH_PAGINATED = "FETCH_PAGINATED",
  FETCH_LINKS = "FETCH_LINKS",
}

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function prettyPrintDate(dateStr: string) {
  const date = new Date(dateStr);
  return date.toLocaleString("en-US", {
    month: "long",
    day: "numeric",
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

export type IterableElement<TargetIterable> =
  TargetIterable extends Iterable<infer ElementType>
  ? ElementType
  : TargetIterable extends AsyncIterable<infer ElementType>
  ? ElementType
  : never;
