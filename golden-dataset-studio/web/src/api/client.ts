// Thin fetch wrappers for the Studio API. Every tab uses these; they keep URLs in one place.
import type {
  ExtractOutputs, MatchRow, ScoreBasis, ScoreDoc, ScoreValues, CatalogsSummary,
  CatalogCard, CatalogDetail, CrawledCatalog, FirstRulesPrompt, CompareRecords, CompareResponse, Discussion, CourseDetail, CourseHit, GoldenFileText, GoldenLineage, GoldenResponse,
  AnnotateResponse, ApprovePreview,
  NewEvent, Overlay,
  PromptResponse, RuleDetail, RulesResponse, RowsResponse, UnclassifiedPage,
} from "./types";
import { signedOut } from "../shell/session";

export class ApiError extends Error {
  constructor(public status: number, message: string) { super(message); }
}

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  const r = await fetch(path, init);
  if (!r.ok) {
    if (r.status === 401) signedOut();
    let detail = r.statusText;
    try { detail = (await r.json()).detail ?? detail; } catch { /* not JSON */ }
    throw new ApiError(r.status, String(detail));
  }
  return r.json() as Promise<T>;
}

const q = (params: Record<string, string | number | boolean | null | undefined>) => {
  const s = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) if (v !== null && v !== undefined && v !== false) s.set(k, String(v));
  const t = s.toString();
  return t ? `?${t}` : "";
};
const c = (catalog: string) => `/api/catalogs/${encodeURIComponent(catalog)}`;
const v = (catalog: string, version: string) => `${c(catalog)}/golden/${encodeURIComponent(version)}`;

export const api = {
  catalogs: () => call<CatalogCard[]>("/api/catalogs"),
  catalogsSummary: (basis: ScoreBasis) => call<CatalogsSummary>(`/api/catalogs-summary?basis=${basis}`),
  crawls: () => call<{ crawls_root: string; items: CrawledCatalog[] }>("/api/crawls"),
  addCatalog: (catalog: string, body: { crawl?: string; by?: string }) =>
    call<unknown>(`/api/crawls/${encodeURIComponent(catalog)}/add`, {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
    }),
  dismissAdd: (catalog: string) => call<unknown>(`/api/crawls/${encodeURIComponent(catalog)}/add`, { method: "DELETE" }),
  catalog: (catalog: string) => call<CatalogDetail>(c(catalog)),
  rules: (catalog: string, ext?: string | null) => call<RulesResponse>(`${c(catalog)}/rules${q({ ext })}`),
  rule: (catalog: string, ruleId: string, ext?: string | null) =>
    call<RuleDetail>(`${c(catalog)}/rules/${encodeURIComponent(ruleId)}${q({ ext })}`),
  rows: (catalog: string, ruleId: string, opts: { offset?: number; limit?: number; q?: string } = {}) =>
    call<RowsResponse>(`${c(catalog)}/rules/${encodeURIComponent(ruleId)}/rows${q(opts)}`),
  pageMeta: (catalog: string, stem: string) =>
    call<{ stem: string; url: string; title: string }>(`${c(catalog)}/pages/${encodeURIComponent(stem)}/meta`),
  overlay: (catalog: string, stem: string, rule: string, ext?: string | null) =>
    call<Overlay>(`${c(catalog)}/pages/${encodeURIComponent(stem)}/overlay${q({ rule, ext })}`),
  unclassifiedPages: (catalog: string, ext?: string | null) =>
    call<UnclassifiedPage[]>(`${c(catalog)}/unclassified-pages${q({ ext })}`),
  courses: (catalog: string, query?: string) => call<CourseHit[]>(`${c(catalog)}/courses${q({ q: query })}`),
  course: (catalog: string, courseKey: string) =>
    call<CourseDetail>(`${c(catalog)}/courses/${encodeURIComponent(courseKey)}`),
  annotate: (catalog: string, event: NewEvent) =>
    call<AnnotateResponse>(`${c(catalog)}/annotations`, {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(event),
    }),
  compare: (catalog: string, opts: { a?: number; b?: number; rule?: string } = {}) =>
    call<CompareResponse>(`${c(catalog)}/compare${q(opts)}`),
  discussion: (catalog: string) => call<Discussion>(`${c(catalog)}/discussion`),
  compareRecords: (catalog: string, o: { a: number; b: number; rule?: string; offset?: number; limit?: number; f?: string[];
                                        order?: string; cross?: string[]; seed?: number }) => {
    const s = new URLSearchParams();
    for (const [k, v] of Object.entries(o)) {
      if (Array.isArray(v)) v.forEach((x) => s.append(k, x));
      else if (v !== undefined && v !== null && v !== "") s.set(k, String(v));
    }
    return call<CompareRecords>(`${c(catalog)}/compare/records?${s}`);
  },
  firstRulesPrompt: (catalog: string) => call<FirstRulesPrompt>(`${c(catalog)}/prompt/first-rules`),
  prompt: (catalog: string, opts: { rule?: string; needs_work?: boolean } = {}) =>
    call<PromptResponse>(`${c(catalog)}/prompt${q(opts)}`),
  golden: (catalog: string) => call<GoldenResponse>(`${c(catalog)}/golden`),
  approvePreview: (catalog: string, rule: string) =>
    call<ApprovePreview>(`${c(catalog)}/golden/approve/${encodeURIComponent(rule)}`),
  goldenStems: (catalog: string, version: string, tree: string) =>
    call<string[]>(`${v(catalog, version)}/stems${q({ tree })}`),
  goldenPageJson: (catalog: string, version: string, stem: string, tree: string) =>
    call<GoldenFileText>(`${v(catalog, version)}/files/page/${encodeURIComponent(stem)}.json${q({ tree })}`),
  goldenPageHtml: (catalog: string, version: string, stem: string) =>
    call<GoldenFileText>(`${v(catalog, version)}/files/page/${encodeURIComponent(stem)}.html`),
  goldenTable: (catalog: string, version: string, table: "lineage" | "golden", opts: { q?: string; offset?: number; limit?: number } = {}) =>
    call<GoldenLineage>(`${v(catalog, version)}/files/${table}.parquet${q(opts)}`),
  goldenPublicationJson: (catalog: string, version: string) =>
    call<GoldenFileText>(`${v(catalog, version)}/files/publication.json`),
  extractOutputs: (catalog: string) => call<ExtractOutputs>(`${c(catalog)}/extract-outputs`),
  scoreDoc: (catalog: string, id: string) => call<ScoreDoc>(`${c(catalog)}/scores/${encodeURIComponent(id)}`),
  scoreValues: (catalog: string, id: string, o: { basis: string; column?: string | null; subject?: string | null;
                                                  outcome?: string | null; group?: string | null; offset?: number }) =>
    call<ScoreValues>(`${c(catalog)}/scores/${encodeURIComponent(id)}/values${q(o)}`),
  match: (catalog: string, rule: string, occ: string, ext?: string | null) =>
    call<MatchRow>(`${c(catalog)}/match${q({ rule, occ, ext })}`),
  startScore: (catalog: string, body: { golden: string; output: string; by: string }) =>
    call<ScoreDoc>(`${c(catalog)}/scores`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }),
};
