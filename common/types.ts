export enum CatalogueType {
  COURSES = "COURSES",
  LEARNING_PROGRAMS = "LEARNING_PROGRAMS",
  COMPETENCIES = "COMPETENCIES",
  CREDENTIALS = "CREDENTIALS",
}

export enum PageType {
  DETAIL = "DETAIL",
  CATEGORY_LINKS = "CATEGORY_LINKS",
  DETAIL_LINKS = "DETAIL_LINKS",
  API_REQUEST = "API_REQUEST",
  EXPLORATORY = "EXPLORATORY",
}

export enum ApiProvider {
  Coursedog = "Coursedog",
}

export enum UrlPatternType {
  page_num = "page_num",
  offset = "offset",
}

export interface PaginationConfiguration {
  urlPatternType: UrlPatternType;
  urlPattern: string;
  totalPages: number;
}

export interface RecipeConfiguration<
  ConfigType extends ApiProvider = ApiProvider,
> {
  pageType: PageType;
  linkRegexp?: string;
  pagination?: PaginationConfiguration;
  links?: RecipeConfiguration;
  apiProvider?: ApiProvider;
  apiConfig?: ApiConfig[ConfigType];
}

export type ApiConfig = {
  [ApiProvider.Coursedog]: {
    schoolId: string;
    catalogIds: string[];
  };
};

export enum LogLevel {
  INFO = "INFO",
  ERROR = "ERROR",
}

export enum Provider {
  OpenAI = "openai",
}

export enum ProviderModel {
  Gpt4o = "gpt-4o",
  O3Mini = "o3-mini",
  Gpt41 = "gpt-4.1",
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
  FETCH_VIA_API = "FETCH_VIA_API",
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

export interface LearningProgramStructuredData {
  learning_program_id: string;
  learning_program_name: string;
  learning_program_description: string;
}

export interface CompetencyStructuredData {
  text: string;
  competency_framework: string;
  language?: string;
}

export type TextInclusion<T> = {
  [K in keyof T]: { full: boolean; sentences?: boolean };
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

export interface ProxySettings {
  url: string;
}

export interface CredentialStructuredData {
  credential_name: string;
  credential_description: string;
  credential_type?: string;
}
