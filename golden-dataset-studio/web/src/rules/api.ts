// W4's additions to the review API (routes_review.py). They extend the shared contract in `api/types.ts` /
// `api/client.ts` (owned by the lead); fold these in there when convenient.
import { ApiError } from "../api/client";
import type { CourseHit, EventBrief, Row, RowsResponse, RuleSummary, SampleInfo, StrataTag } from "../api/types";

export interface PageRef { page_stem: string; url: string; title: string | null }

/** A row as `/rows` returns it now: page-level questions (page rules) and the other pages its course is on. */
export interface RowX extends Row { page_questions?: EventBrief[]; other_pages?: PageRef[]; tags?: StrataTag[] }
export interface RowsX extends RowsResponse { rows: RowX[]; focus_index?: number | null; sample?: SampleInfo | null }
export interface RuleSummaryX extends RuleSummary { page_questions?: number }
export interface CourseHitX extends CourseHit { annotated?: boolean }
export interface PageHit extends PageRef { matched: boolean }
/** The "Annotated by" dropdown (Evals spec §6.7): people with their role and the field values they annotated, the
 * values waiting for an expert, and with a filter, each rule's rows that pass it. */
export interface Annotators {
  people: { name: string; role: "sme" | "engineer"; values: number }[];
  waiting: number; rules: Record<string, number> | null;
}

async function get<T>(path: string): Promise<T> {
  const r = await fetch(path);
  if (!r.ok) {
    let detail = r.statusText;
    try { detail = (await r.json()).detail ?? detail; } catch { /* not JSON */ }
    throw new ApiError(r.status, String(detail));
  }
  return r.json() as Promise<T>;
}

const c = (catalog: string) => `/api/catalogs/${encodeURIComponent(catalog)}`;
const qs = (o: Record<string, string | number | boolean | string[] | null | undefined>) => {
  const s = new URLSearchParams();
  for (const [k, v] of Object.entries(o)) {
    if (Array.isArray(v)) v.forEach((x) => s.append(k, x));
    else if (v !== null && v !== undefined && v !== "") s.set(k, String(v));
  }
  const t = s.toString();
  return t ? `?${t}` : "";
};

export const apiX = {
  rows: (catalog: string, ruleId: string, o: { offset?: number; limit?: number; focus?: string | null; f?: string[]; ext?: string | null;
                                              order?: string; cross?: string[]; seed?: number; prior?: boolean;
                                              by?: string | null; verdict?: string | null } = {}) =>
    get<RowsX>(`${c(catalog)}/rules/${encodeURIComponent(ruleId)}/rows${qs(o)}`),
  pageSearch: (catalog: string, q: string, rule: string) => get<PageHit[]>(`${c(catalog)}/page-search${qs({ q, rule })}`),
  courses: (catalog: string, q?: string, by?: string | null) => get<CourseHitX[]>(`${c(catalog)}/courses${qs({ q, limit: 400, by })}`),
  annotators: (catalog: string, o: { by?: string | null; verdict?: string | null; ext?: string | null } = {}) =>
    get<Annotators>(`${c(catalog)}/annotators${qs(o)}`),
};
