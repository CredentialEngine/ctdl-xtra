// Thin fetch wrappers for the Studio API. Every tab uses these; they keep URLs in one place.
import type {
  EvalJob, EvalsIndex, EvalView,
  CatalogCard, CatalogDetail, CompareRecords, CompareResponse, Discussion, CourseDetail, CourseHit, GoldenFileText, GoldenLineage, GoldenResponse,
  NewEvent, Overlay,
  PromptResponse, PromptTarget, RuleDetail, RuleSummary, RulesResponse, RowsResponse, UnclassifiedPage,
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
  prompt: (catalog: string, opts: { rule?: string; needs_work?: boolean; target?: PromptTarget } = {}) =>
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
  evals: (catalog: string) => call<EvalsIndex>(`${c(catalog)}/evals`),
  evalView: (catalog: string, id: string, o: { golden: string; f: string[]; dim: string; offset?: number; limit?: number }) => {
    const s = new URLSearchParams({ golden: o.golden, dim: o.dim, offset: String(o.offset ?? 0), limit: String(o.limit ?? 50) });
    o.f.forEach((x) => s.append("f", x));
    return call<EvalView>(`${c(catalog)}/evals/${encodeURIComponent(id)}?${s}`);
  },
  startXtraRun: (catalog: string, body: { ref?: string; sample?: boolean; import?: boolean; then_eval?: string | null; by: string }) =>
    call<EvalJob>(`${c(catalog)}/xtra-runs`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }),
  startEval: (catalog: string, body: { xtra_run: string; golden: string; by: string }) =>
    call<EvalJob>(`${c(catalog)}/evals`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }),
  job: (id: string) => call<EvalJob>(`/api/jobs/${encodeURIComponent(id)}`),
  cancelJob: (id: string) => call<EvalJob>(`/api/jobs/${encodeURIComponent(id)}/cancel`, { method: "POST" }),
};
