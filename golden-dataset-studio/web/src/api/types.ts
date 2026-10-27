// The JSON the Studio server returns (src/golden_datasets/server/routes_*.py). This file is the contract between
// the server and the tabs; change both sides together.

export type RuleKind = "page" | "locator" | "field";
export type RuleStatus = "approved" | "needs work" | "in review";
export type Verdict = "correct" | "wrong" | "missing" | "question";
/** A row's verdict carried forward to the current rule version (review.py `_carry`). */
export type RowStateName = Verdict | "fixed" | "still-wrong" | "changed-since-correct";

export interface CatalogCard {
  catalog: string; short: string; name: string; institution: string; platform: string; logo: string | null;
  pages: number | null; crawl: string | null; ruleset_version: number | null;
  rules_total: number; rules_approved: number; status: "ready" | "not imported";
}

export interface RulesetInfo {
  version: number; note: string | null; published_at: string | null; published_by: string | null;
  changed_rules: string[]; extraction: string | null;
}

export interface CatalogDetail {
  catalog: string; short: string; name: string; institution: string; logo: string | null;
  crawl: string; crawl_started: string; pages: number; extraction: string; ruleset_version: number;
  extractions: { extraction: string; ruleset_version: number; parent_extraction: string | null }[];
  rulesets: RulesetInfo[]; authors: string[]; pane_css: string; root: string;
}

export interface RuleSummary {
  rule_id: string; kind: RuleKind; version: number; title: string; subtitle: string;
  ctdl_property: string | null; property_label: string | null; locator: string | null;
  status: RuleStatus; reviewed: number; total: number; open_wrong: number; open_missing: number;
  questions: number; approved_by: string | null; approved_at: string | null; comments: number;
}

export interface RuleGroup { kind: RuleKind; label: string; rules: RuleSummary[]; approved: number }
export interface RulesResponse { extraction: string; ruleset_version: number; groups: RuleGroup[] }

export interface RuleDetail extends RuleSummary {
  definition: Record<string, unknown>; what: string; how: string; why: string;
  examples: { input: string; output: string }[]; depends_on: string[]; content_hash: string;
  published_by: string | null; published_at: string | null; parent_version: number | null; versions: number[];
  fill: { rows: number; found: number }; signal_counts: Record<string, number>;
  settings: { content_root: string };
}

/** `expected` of a verdict: the text Jared selected on the page (spec §9 highlight-to-annotate). */
export interface Expected {
  text: string; css_path: string | null; char_start: number | null; char_end: number | null;
  quote?: { prefix: string; exact: string; suffix: string } | null; located_by?: string; author?: string;
}

export interface EventBrief {
  annotation_id: string; type: "verdict" | "comment" | "approve" | "reopen"; verdict: Verdict | null;
  author: string; at: string; note: string | null; expected: Expected | null;
  rule_version_seen: number | null; value_seen: string | null; page_stem?: string | null;
}

export interface Row {
  key: string;                       // occurrence_key (field rules, locators) or page_stem (page rules)
  occurrence_key: string | null; course_key: string | null; page_stem: string; url: string; page_title: string | null;
  value: string | null; status: "found" | "empty" | "no_match";
  css_path: string | null;           // document-root path of the value's element (null for constants)
  char_start: number | null; char_end: number | null;   // DOM textContent offsets in that element
  occurrence_css_path: string | null; context: string | null;   // "GEOG 222 - Cartography …" (or the page URL)
  state: RowStateName | null; verdict: EventBrief | null; reattached: boolean; comments: EventBrief[];
  signal_count: number;              // never shown as tags (spec §8); available for debugging only
}

export interface RowsResponse {
  rule_id: string; extraction: string; total: number; offset: number; rows: Row[];
  missing: EventBrief[];             // open "missing" verdicts of a locator / page rule
  elapsed_ms: number;
}

export interface Overlay {
  blocks: { occurrence_key: string; css_path: string; n: number; course_key: string | null }[];
  marks: { css_path: string; char_start: number; char_end: number; detail: string }[];
}

export interface UnclassifiedPage { page_stem: string; url: string; title: string | null; detail: string }

export interface CourseHit { course_key: string; occurrences: number; line: string | null }
export interface CourseField {
  rule_id: string; property_label: string | null; ctdl_property: string | null; value: string | null;
  status: string; css_path: string | null; char_start: number | null; char_end: number | null;
  state: RowStateName | null; verdict: EventBrief | null; comments: EventBrief[];
}
export interface CourseDetail {
  course_key: string; extraction: string;
  occurrences: { occurrence_key: string; page_stem: string; url: string; page_title: string | null;
                 locator_rule_id: string; css_path: string; fields: CourseField[] }[];
}

/** What the client posts to /annotations. The server fills id, time, catalog, crawl, versions and value_seen. */
export interface NewEvent {
  type: "verdict" | "comment" | "approve" | "reopen";
  author: string;
  target: { kind: "match" | "occurrence" | "page" | "rule"; rule_id: string | null;
            occurrence_key?: string | null; page_stem?: string | null };
  verdict?: Verdict; expected?: Expected | null; note?: string | null; supersedes?: string | null;
}

// --- Compare (routes_compare.py, scorecard.py) -------------------------------------------------------
export interface DiffPart { op: "same" | "del" | "add"; text: string }
export interface BriefRow {
  key: string; course_key: string | null; page_stem: string; a_value: string | null; b_value: string | null;
  diff: DiffPart[]; css_path: string | null; char_start: number | null; char_end: number | null;
}
export interface AnnotatedRow extends BriefRow {
  verdict: "correct" | "wrong"; author: string; note: string | null; expected: string | null;
  outcome: "fixed" | "still wrong" | "newly wrong" | "unchanged"; annotation_id: string;
}
export interface SignalDelta { signal: string; a: number; b: number; lost: BriefRow[]; gained: BriefRow[] }
export interface RuleCard {
  rule_id: string; kind: RuleKind; ctdl_property: string | null; property_label: string | null;
  title: string; subtitle: string; a_version: number | null; b_version: number | null; why: string;
  annotated: { rows: number; fixed: number; still_wrong: number; newly_wrong: number; unchanged: number };
  annotated_rows: AnnotatedRow[];
  values: { changed: number; total: number; new: number; vanished: number };
  signals: SignalDelta[]; sample: BriefRow[]; new_rows: BriefRow[]; vanished_rows: BriefRow[]; verdict: string;
}
export interface CompareResponse {
  a: number; b: number; a_extraction: string; b_extraction: string;
  versions: { version: number; extraction: string; note: string | null }[];
  changed_rules: { rule_id: string; title: string; subtitle: string; kind: RuleKind; ctdl_property: string | null;
                   a_version: number | null; b_version: number | null; records_changed: number }[];
  records_changed: number;
  totals: { fixed: number; still_wrong: number; newly_wrong: number; unchanged: number };
  rules: RuleCard[]; elapsed_ms: number;
}

// --- Prompt (routes_prompt.py; W6) -------------------------------------------------------------------
export interface PromptResponse {
  scope: { rule: string | null; needs_work: boolean };
  text: string; chars: number; tokens: number; page_refs: number; rules: string[]; annotations: number;
}

// --- Golden (routes_golden.py; W7) -------------------------------------------------------------------
export interface GoldenResponse {
  ready: boolean; extraction: string; ruleset_version: number;
  rules: { rule_id: string; title: string; subtitle: string; kind: RuleKind; version: number;
           status: RuleStatus; approved_by: string | null }[];
  target: string;                     // where the per-page files go: <golden root>/<catalog>/<crawl>/
  pages: number; courses: number; records: number; fields: number; skipped_no_course_key: number;
  collisions: { course_key: string; golden_ids: string[]; names: string[] }[];
  page_stems: { stem: string; records: number }[];   // the pages that get a <stem>.json, with their course entries
  publications: { publication: string; extraction: string; ruleset_version: number; published_at: string | null;
                  published_by: string | null; pages: number; courses: number; records: number;
                  lineage_rows: number; to: string; all_rules_approved: boolean | null }[];
}

export interface GoldenFileText { text: string; stem?: string; records?: number; bytes?: number; truncated?: boolean;
                                  truncated_page_stems?: boolean }
export interface GoldenLineage { columns: string[]; total: number; matched: number; offset: number; rows: unknown[][] }
