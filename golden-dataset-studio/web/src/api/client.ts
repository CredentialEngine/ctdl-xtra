// Thin fetch wrappers for the Studio API. Every tab uses these; they keep URLs in one place.
import type {
  ExtractOutputs, MatchRow, ScoreBasis, ScoreDoc, ScoreValues, CatalogsSummary, WrongGroups, WrongKey,
  CatalogCard, CatalogDetail, CrawledCatalog, FirstRulesPrompt, CompareRecords, CompareResponse, Discussion, CourseDetail, CourseHit, GoldenFileText, GoldenLineage, GoldenResponse,
  AnnotateResponse, ApprovePreview, ResetPreview,
  Finding, KeySource, NewEvent, Overlay, PropertyReview, PropertyStatus, PropertyStatusName, ScoreHistory, ThreadComment, ThreadTarget,
  PromptResponse, RuleDetail, RulesResponse, RowsResponse, UnclassifiedPage,
} from "./types";
import { withClass } from "../shell/klass";
import type { ClassSlug } from "../shell/router";
import { signedOut } from "../shell/session";

export class ApiError extends Error {
  constructor(public status: number, message: string) { super(message); }
}

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(withClass(path), init);
  if (!response.ok) throw await apiError(response);
  return response.json() as Promise<T>;
}

export const api = {
  catalogs: () => call<CatalogCard[]>("/api/catalogs"),
  catalogsSummary: (basis: ScoreBasis, cls?: ClassSlug) =>
    call<CatalogsSummary>(`/api/catalogs-summary?basis=${basis}${classQuery(cls, "&")}`),
  // findings, property status and discussion (learning-programs Phase 6), per class and property
  propertyReview: (cls: ClassSlug, col: string) => call<PropertyReview>(`${propertyPath(cls, col)}/review`),
  setPropertyStatus: (cls: ClassSlug, col: string, status: PropertyStatusName, author: string) =>
    call<PropertyStatus>(`${propertyPath(cls, col)}/status`, jsonInit("POST", { status, author })),
  saveFinding: (cls: ClassSlug, col: string, body: Partial<Finding> & { author: string }, id?: string) =>
    call<Finding>(id ? `${propertyPath(cls, col)}/findings/${encodeURIComponent(id)}` : `${propertyPath(cls, col)}/findings`, jsonInit(id ? "PUT" : "POST", body)),
  propertyThread: (cls: ClassSlug, col: string, key: string) => call<ThreadComment[]>(`${propertyPath(cls, col)}/threads?key=${encodeURIComponent(key)}`),
  addPropertyComment: (cls: ClassSlug, col: string, body: { author: string; note: string; target: ThreadTarget }) =>
    call<ThreadComment>(`${propertyPath(cls, col)}/threads`, jsonInit("POST", body)),
  propertyStatuses: (cls: ClassSlug) =>
    call<Record<string, { status: PropertyStatusName; by: string; at: string }>>(`/api/property-status${classQuery(cls, "?")}`),
  /** the home page's score views: a class's properties and each catalog's last scores per property */
  scoreHistory: (cls: ClassSlug) => call<ScoreHistory>(`/api/score-history${classQuery(cls, "?")}`),
  crawls: () => call<{ crawls_root: string; items: CrawledCatalog[] }>("/api/crawls"),
  addCatalog: (catalog: string, body: { crawl?: string; by?: string }) =>
    call<unknown>(`/api/crawls/${encodeURIComponent(catalog)}/add`, jsonInit("POST", body)),
  dismissAdd: (catalog: string) => call<unknown>(`/api/crawls/${encodeURIComponent(catalog)}/add`, { method: "DELETE" }),
  catalog: (catalog: string) => call<CatalogDetail>(catalogPath(catalog)),
  rules: (catalog: string, ext?: string | null) => call<RulesResponse>(`${catalogPath(catalog)}/rules${queryString({ ext })}`),
  rule: (catalog: string, ruleId: string, ext?: string | null) =>
    call<RuleDetail>(`${catalogPath(catalog)}/rules/${encodeURIComponent(ruleId)}${queryString({ ext })}`),
  rows: (catalog: string, ruleId: string, opts: { offset?: number; limit?: number; q?: string } = {}) =>
    call<RowsResponse>(`${catalogPath(catalog)}/rules/${encodeURIComponent(ruleId)}/rows${queryString(opts)}`),
  pageMeta: (catalog: string, stem: string) =>
    call<{ stem: string; url: string; title: string }>(`${catalogPath(catalog)}/pages/${encodeURIComponent(stem)}/meta`),
  overlay: (catalog: string, stem: string, rule: string, ext?: string | null) =>
    call<Overlay>(`${catalogPath(catalog)}/pages/${encodeURIComponent(stem)}/overlay${queryString({ rule, ext })}`),
  unclassifiedPages: (catalog: string, ext?: string | null) =>
    call<UnclassifiedPage[]>(`${catalogPath(catalog)}/unclassified-pages${queryString({ ext })}`),
  courses: (catalog: string, query?: string) => call<CourseHit[]>(`${catalogPath(catalog)}/courses${queryString({ q: query })}`),
  course: (catalog: string, recordKey: string) =>
    call<CourseDetail>(`${catalogPath(catalog)}/courses/${encodeURIComponent(recordKey)}`),
  annotate: (catalog: string, event: NewEvent) =>
    call<AnnotateResponse>(`${catalogPath(catalog)}/annotations`, jsonInit("POST", event)),
  compare: (catalog: string, opts: { a?: number; b?: number; rule?: string } = {}) =>
    call<CompareResponse>(`${catalogPath(catalog)}/compare${queryString(opts)}`),
  discussion: (catalog: string) => call<Discussion>(`${catalogPath(catalog)}/discussion`),
  compareRecords: (catalog: string, o: { a: number; b: number; rule?: string; offset?: number; limit?: number; f?: string[];
                                        order?: string; cross?: string[]; seed?: number }) =>
    call<CompareRecords>(`${catalogPath(catalog)}/compare/records${repeatedQueryString(o)}`),
  firstRulesPrompt: (catalog: string) => call<FirstRulesPrompt>(`${catalogPath(catalog)}/prompt/first-rules`),
  prompt: (catalog: string, opts: { rule?: string; needs_work?: boolean } = {}) =>
    call<PromptResponse>(`${catalogPath(catalog)}/prompt${queryString(opts)}`),
  golden: (catalog: string) => call<GoldenResponse>(`${catalogPath(catalog)}/golden`),
  resetPreview: (catalog: string, rule: string) =>
    call<ResetPreview>(`${catalogPath(catalog)}/rules/${encodeURIComponent(rule)}/reset-preview`),
  approvePreview: (catalog: string, rule: string) =>
    call<ApprovePreview>(`${catalogPath(catalog)}/golden/approve/${encodeURIComponent(rule)}`),
  goldenStems: (catalog: string, version: string, tree: string) =>
    call<string[]>(`${versionPath(catalog, version)}/stems${queryString({ tree })}`),
  goldenPageJson: (catalog: string, version: string, stem: string, tree: string) =>
    call<GoldenFileText>(`${versionPath(catalog, version)}/files/page/${encodeURIComponent(stem)}.json${queryString({ tree })}`),
  goldenPageHtml: (catalog: string, version: string, stem: string) =>
    call<GoldenFileText>(`${versionPath(catalog, version)}/files/page/${encodeURIComponent(stem)}.html`),
  goldenTable: (catalog: string, version: string, table: "lineage" | "golden", opts: { q?: string; offset?: number; limit?: number } = {}) =>
    call<GoldenLineage>(`${versionPath(catalog, version)}/files/${table}.parquet${queryString(opts)}`),
  goldenPublicationJson: (catalog: string, version: string) =>
    call<GoldenFileText>(`${versionPath(catalog, version)}/files/publication.json`),
  extractOutputs: (catalog: string) => call<ExtractOutputs>(`${catalogPath(catalog)}/extract-outputs`),
  scoreDoc: (catalog: string, id: string) => call<ScoreDoc>(`${catalogPath(catalog)}/scores/${encodeURIComponent(id)}`),
  scoreValues: (catalog: string, id: string, o: { basis: string; column?: string | null; subject?: string | null;
                                                  outcome?: string | null; group?: string | null; offset?: number }) =>
    call<ScoreValues>(`${catalogPath(catalog)}/scores/${encodeURIComponent(id)}/values${queryString(o)}`),
  /** "Where it's wrong" (sme-fixes spec §8.4) */
  scoreWrong: (catalog: string, id: string, o: { basis: string; column?: string | null; key?: WrongKey | null }) =>
    call<WrongGroups>(`${catalogPath(catalog)}/scores/${encodeURIComponent(id)}/wrong${queryString(o)}`),
  keySource: (catalog: string, occ: string) => call<KeySource>(`${catalogPath(catalog)}/key-source${queryString({ occ })}`),
  match: (catalog: string, rule: string, occ: string, ext?: string | null) =>
    call<MatchRow>(`${catalogPath(catalog)}/match${queryString({ rule, occ, ext })}`),
  startScore: (catalog: string, body: { golden: string; output: string; by: string }) =>
    call<ScoreDoc>(`${catalogPath(catalog)}/scores`, jsonInit("POST", body)),
};

async function apiError(response: Response): Promise<ApiError> {
  if (response.status === 401) signedOut();
  return new ApiError(response.status, await errorDetail(response));
}

async function errorDetail(response: Response): Promise<string> {
  let detail = response.statusText;
  try { detail = (await response.json()).detail ?? detail; } catch { /* not JSON */ }
  return String(detail);
}

type QueryValue = string | number | boolean | null | undefined;

function queryString(params: Record<string, QueryValue>): string {
  const search = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) if (v !== null && v !== undefined && v !== false) search.set(k, String(v));
  const text = search.toString();
  return text ? `?${text}` : "";
}

function repeatedQueryString(params: Record<string, QueryValue | string[]>): string {
  const search = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (Array.isArray(v)) v.forEach((x) => search.append(k, x));
    else if (v !== undefined && v !== null && v !== "") search.set(k, String(v));
  }
  return `?${search}`;
}

const catalogPath = (catalog: string) => `/api/catalogs/${encodeURIComponent(catalog)}`;
const versionPath = (catalog: string, version: string) => `${catalogPath(catalog)}/golden/${encodeURIComponent(version)}`;
const propertyPath = (cls: ClassSlug, col: string) => `/api/properties/${cls}/${encodeURIComponent(col)}`;
const classQuery = (cls: ClassSlug | undefined, first: "?" | "&") => (cls && cls !== "course" ? `${first}class=${cls}` : "");
const jsonInit = (method: string, body: unknown): RequestInit =>
  ({ method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
