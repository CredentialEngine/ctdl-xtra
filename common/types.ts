export enum CatalogueType {
  COURSES = "COURSES",
  LEARNING_PROGRAMS = "LEARNING_PROGRAMS",
}

export enum PageType {
  COURSE_DETAIL_PAGE = "COURSE_DETAIL_PAGE",
  CATEGORY_LINKS_PAGE = "CATEGORY_LINKS_PAGE",
  COURSE_LINKS_PAGE = "COURSE_LINKS_PAGE",
}

export type UrlPatternType = "page_num" | "offset";

export interface PaginationConfiguration {
  urlPatternType: UrlPatternType;
  urlPattern: string;
  totalPages: number;
}

export interface RecipeConfiguration {
  pageType: PageType;
  linkRegexp?: string;
  pagination?: PaginationConfiguration;
  links?: RecipeConfiguration;
}

export enum LogLevel {
  INFO = "INFO",
  ERROR = "ERROR",
}

export enum Provider {
  OpenAI = "openai",
}

export enum ProviderModel {
  Gpt4o = "gpt-4o",
}

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

export interface FetchFailureReason {
  responseStatus?: number;
  reason: string;
}

export interface CourseStructuredData {
  course_id: string;
  course_name: string;
  course_description: string;
  course_credits_min?: number;
  course_credits_max?: number;
  course_credits_type?: string;
  course_ceu_credits?: number;
  course_prerequisites?: string;
}

export type TextInclusion = {
  [K in keyof CourseStructuredData]: { full: boolean };
};

export interface StepCompletionStats {
  downloads: {
    total: number;
    attempted: number;
    succeeded: number;
  };
  extractions: {
    attempted: number;
    succeeded: number;
    courses: number;
  };
}

export interface CostCallSite {
  callSite: string;
  totalInputTokens: number;
  totalOutputTokens: number;
  estimatedCost: number;
}

export interface CostSummary {
  totalInputTokens: number;
  totalOutputTokens: number;
  callSites: CostCallSite[];
  estimatedCost: number;
}

export interface CompletionStats {
  costs?: CostSummary;
  steps: StepCompletionStats[];
  generatedAt: string;
}
