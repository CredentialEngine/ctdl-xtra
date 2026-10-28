// Thin fetch wrappers for the Studio API. Every tab uses these; they keep URLs in one place.
import type {
  CatalogCard, CatalogDetail, CrawledCatalog, FirstRulesPrompt, CompareRecords, CompareResponse, Discussion, CourseDetail, CourseHit, GoldenFileText, GoldenLineage, GoldenResponse,
  NewEvent, Overlay,
  PromptResponse, RuleDetail, RuleSummary, RulesResponse, RowsResponse, UnclassifiedPage,
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

export const api = {
  catalogs: () => call<CatalogCard[]>("/api/catalogs"),
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
  overlay: (catalog: string, stem: string, rule: string, ext?: string | null) =>
    call<Overlay>(`${c(catalog)}/pages/${encodeURIComponent(stem)}/overlay${q({ rule, ext })}`),
  unclassifiedPages: (catalog: string, ext?: string | null) =>
    call<UnclassifiedPage[]>(`${c(catalog)}/unclassified-pages${q({ ext })}`),
  courses: (catalog: string, query?: string) => call<CourseHit[]>(`${c(catalog)}/courses${q({ q: query })}`),
  course: (catalog: string, courseKey: string) =>
    call<CourseDetail>(`${c(catalog)}/courses/${encodeURIComponent(courseKey)}`),
  annotate: (catalog: string, event: NewEvent) =>
    call<{ event: unknown; rule: RuleSummary | null; elapsed_ms: number }>(`${c(catalog)}/annotations`, {
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
  // `properties`: the properties a publication would publish (comma-separated in the query)
  golden: (catalog: string, properties?: string[]) =>
    call<GoldenResponse>(`${c(catalog)}/golden${q({ properties: properties?.join(",") })}`),
  goldenPageJson: (catalog: string, stem: string, properties?: string[]) =>
    call<GoldenFileText>(`${c(catalog)}/golden/files/page/${encodeURIComponent(stem)}.json${q({ properties: properties?.join(",") })}`),
  goldenPageHtml: (catalog: string, stem: string, properties?: string[]) =>
    call<GoldenFileText>(`${c(catalog)}/golden/files/page/${encodeURIComponent(stem)}.html${q({ properties: properties?.join(",") })}`),
  goldenLineage: (catalog: string, opts: { q?: string; offset?: number; limit?: number; properties?: string } = {}) =>
    call<GoldenLineage>(`${c(catalog)}/golden/files/lineage${q(opts)}`),
  goldenPublicationJson: (catalog: string, author: string, properties?: string[]) =>
    call<GoldenFileText>(`${c(catalog)}/golden/files/publication.json${q({ author, properties: properties?.join(",") })}`),
  goldenPublish: (catalog: string, body: { author: string; properties: string[]; to?: string }) =>
    call<{ publication: string; path: string; files: number }>(`${c(catalog)}/golden/publish`, {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
    }),
};
