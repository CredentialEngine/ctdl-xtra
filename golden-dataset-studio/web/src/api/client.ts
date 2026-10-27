// Thin fetch wrappers for the Studio API. Every tab uses these; they keep URLs in one place.
import type {
  CatalogCard, CatalogDetail, CompareResponse, CourseDetail, CourseHit, GoldenResponse, NewEvent, Overlay,
  PromptResponse, RuleDetail, RuleSummary, RulesResponse, RowsResponse, UnclassifiedPage,
} from "./types";

export class ApiError extends Error {
  constructor(public status: number, message: string) { super(message); }
}

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  const r = await fetch(path, init);
  if (!r.ok) {
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
  catalog: (catalog: string) => call<CatalogDetail>(c(catalog)),
  rules: (catalog: string) => call<RulesResponse>(`${c(catalog)}/rules`),
  rule: (catalog: string, ruleId: string) => call<RuleDetail>(`${c(catalog)}/rules/${encodeURIComponent(ruleId)}`),
  rows: (catalog: string, ruleId: string, opts: { offset?: number; limit?: number; q?: string } = {}) =>
    call<RowsResponse>(`${c(catalog)}/rules/${encodeURIComponent(ruleId)}/rows${q(opts)}`),
  overlay: (catalog: string, stem: string, rule: string) =>
    call<Overlay>(`${c(catalog)}/pages/${encodeURIComponent(stem)}/overlay${q({ rule })}`),
  unclassifiedPages: (catalog: string) => call<UnclassifiedPage[]>(`${c(catalog)}/unclassified-pages`),
  courses: (catalog: string, query?: string) => call<CourseHit[]>(`${c(catalog)}/courses${q({ q: query })}`),
  course: (catalog: string, courseKey: string) =>
    call<CourseDetail>(`${c(catalog)}/courses/${encodeURIComponent(courseKey)}`),
  annotate: (catalog: string, event: NewEvent) =>
    call<{ event: unknown; rule: RuleSummary | null; elapsed_ms: number }>(`${c(catalog)}/annotations`, {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(event),
    }),
  compare: (catalog: string, opts: { a?: number; b?: number; rule?: string } = {}) =>
    call<CompareResponse>(`${c(catalog)}/compare${q(opts)}`),
  prompt: (catalog: string, opts: { rule?: string; needs_work?: boolean } = {}) =>
    call<PromptResponse>(`${c(catalog)}/prompt${q(opts)}`),
  golden: (catalog: string) => call<GoldenResponse>(`${c(catalog)}/golden`),
  goldenPublish: (catalog: string, body: { author: string; to?: string }) =>
    call<{ publication: string; path: string; files: number }>(`${c(catalog)}/golden/publish`, {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
    }),
};
