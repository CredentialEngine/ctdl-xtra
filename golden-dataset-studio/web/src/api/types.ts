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
  rules_total: number; rules_approved: number; status: "ready" | "not imported" | "adding" | "failed";
  // while a catalog is being added from the picker: what it's doing ("copying", "indexing", "assets") or why it failed
  adding?: { step: string; done: number; total: number; error: string | null };
}

/** Generate rules: the prompt that has Claude Code write a new catalog's first ruleset from a template catalog. */
export interface FirstRulesPrompt {
  text: string; chars: number; tokens: number; template: string; template_name: string; root: string; studio_root?: string; warning?: string | null;
}

export type CrawlStatus = "complete" | "limit_reached" | "incomplete";
export interface CrawlRun { crawl: string; seed_url: string | null; finished_at: string | null; pages: number; status: CrawlStatus }
/** A catalog xtra-cli has crawled (Add a catalog): its latest crawl, and every crawl newest first. */
export interface CrawledCatalog extends CrawlRun {
  catalog: string; name: string; crawls: CrawlRun[]; added: boolean; adding: boolean;
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
  rule_comments?: number;             // comments on the whole rule (sidebar)
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
  group: string | null;              // its group in the spread sample (strata.py), e.g. "51–67 words (percentile 21–41)"
}

/** How the rows without signals are spread (strata.py): what they are grouped by, and each group's size. */
export interface Spread { by: string; groups: { label: string; rows: number }[] }

export interface RowsResponse {
  rule_id: string; extraction: string; total: number; offset: number; rows: Row[];
  missing: EventBrief[];             // open "missing" verdicts of a locator / page rule
  spread: Spread;
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
  target: { kind: "match" | "occurrence" | "page" | "rule" | "ruleset"; rule_id: string | null;
            occurrence_key?: string | null; page_stem?: string | null };
  verdict?: Verdict; expected?: Expected | null; note?: string | null; supersedes?: string | null;
  topic?: Topic;                      // comments on a whole rule or on the ruleset
}

/** What a comment on a whole rule or on the ruleset is about (log.py TOPICS). */
export type Topic = "new-rule" | "approach" | "question-rule" | "other";
/** A comment on a whole rule or on the ruleset (routes_review.py `/discussion`). */
export interface TalkItem {
  annotation_id: string; author: string; at: string; note: string | null; topic: Topic | null;
  rule_id: string | null; rule_version_seen: number | null; ruleset_version_seen: number | null;
}
export interface Discussion { ruleset: TalkItem[]; rules: Record<string, TalkItem[]> }

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
export type PromptTarget = "local" | "azure";
export interface PromptResponse {
  scope: { rule: string | null; needs_work: boolean };
  text: string; chars: number; tokens: number; page_refs: number; rules: string[]; annotations: number;
  target: PromptTarget;
  root: string;                       // the root the prompt points Claude at
  studio_root?: string;               // the root this Studio serves
  warning?: string | null;            // e.g. the branch Claude installs the CLI from has unpushed commits
}

// --- Golden (routes_golden.py; W7) -------------------------------------------------------------------
/** A property the field rules fill, and whether it can be published (its rule approved). */
export interface PublishProperty {
  property: string; ctdl_property: string | null; rule_id: string; version: number; status: RuleStatus;
  approved_by: string | null;
  published: { publication: string; published_at: string | null; published_by: string | null; extraction: string | null;
               rule_version: number | null } | null;
}
export interface GoldenResponse {
  ready: boolean;                     // some property can be published
  all_rules_approved: boolean;
  chosen: string[];                   // the properties the counts and previews are for
  approvals?: { human: number; rule: number };   // the chosen properties' values, by who approved them
  properties: PublishProperty[];
  extraction: string; ruleset_version: number;
  rules: { rule_id: string; title: string; subtitle: string; kind: RuleKind; version: number;
           status: RuleStatus; approved_by: string | null }[];
  target: string;                     // where the per-page files go: <golden root>/<catalog>/<crawl>/
  pages: number; courses: number; records: number; fields: number; skipped_no_course_key: number;
  collisions: { course_key: string; golden_record_ids: string[]; names: string[] }[];
  page_stems: { stem: string; records: number }[];   // the pages that get a <stem>.json, with their course entries
  publications: { publication: string; extraction: string; ruleset_version: number; published_at: string | null;
                  published_by: string | null; pages: number; courses: number; records: number;
                  lineage_rows: number; to: string; all_rules_approved: boolean | null; properties?: string[] | null }[];
}

export interface GoldenFileText { text: string; stem?: string; records?: number; bytes?: number; truncated?: boolean;
                                  truncated_page_stems?: boolean }
export interface GoldenLineage { columns: string[]; total: number; matched: number; offset: number; rows: unknown[][] }

// --- Sample drawer (facets.py): strata histograms and sample orders; /rows and /compare/records return them ---
export type SampleOrder = "review" | "auto" | "shuffle";
export interface StratumHist {
  id: string; label: string; help: string;
  uniform: boolean;                   // every row in one bucket: set aside
  spread: number;                     // how evenly the rows split over the buckets, 0–1
  buckets: { id: string; count: number; on: boolean }[];   // count: rows in the list (this stratum's own filter left out)
}
export interface SampleInfo {
  order: SampleOrder; seed: number; total: number; listed: number;
  histograms: StratumHist[];
  cross: string[];                    // Autostratify: the strata crossed
  cells: { buckets: Record<string, string>; rows: number }[];   // their combinations, rarest first
  cell_count?: number;
  tag_dims: string[];
  elsewhere?: number;                 // Rules tab: unreviewed rows whose record was reviewed in another rule
  prior?: boolean;                    // …and they come first
}
export interface StrataTag { dim: string; label: string; bucket: string }
/** {dimension: [bucket, …]}: buckets of one dimension are ORed, dimensions ANDed. */
export type FacetFilter = Record<string, string[]>;
export const filterParams = (f: FacetFilter): string[] =>
  Object.entries(f).flatMap(([d, bs]) => bs.map((b) => `${d}:${b}`));

/** `/compare/records`: every changed record without a verdict, a page at a time (routes_compare.py). */
export interface CompareRecords {
  total: number;                      // records in the list (after the strata filters)
  all: number;                        // records before filtering
  offset: number; limit: number;
  records: (BriefRow & { rule_id: string; tags: StrataTag[] })[];
  sample: SampleInfo;
}

// --- Evals (docs/qrspi/evals): extractions, baselines and scores, in `xtra score`'s words ------------------
export type ScoreOutcome = "missing" | "wrong" | "partial" | "match";
export type BaselineId = "full" | "hand" | "verified";
export interface Extraction {
  id: string; kind: "extract" | "import"; title: string; detail: string; scope: string; records: number | null;
  commit?: string; ref?: string; created_at: string; commands: string[];
}
export interface ScoreSummary {
  eval: string; kind: "hand" | "full"; baseline: BaselineId; version: string; extraction: string;
  match_rate: number | null; fields: number | null; created_at: string; approved: boolean;
}
export interface EvalJob {
  id: string; kind: string; label: string; status: "running" | "done" | "failed" | "cancelled"; error: string | null;
  result: { run?: string; eval?: string } | null; started: number; finished: number | null; log: string[];
}
export interface ExtractOptions {
  source?: string; error?: string; discovery_run_id?: string; sample_pages?: number; course_pages?: number;
  latest?: { records: number; pages_considered: number; discovery_run_id: string; scope: "sample" | "all" };
}
export interface EvalsIndex {
  extractions: Extraction[]; versions: { id: string; label: string; approved: boolean }[]; scores: ScoreSummary[];
  extract_options: ExtractOptions; default_ref: string; allow_runs: boolean; jobs: EvalJob[];
}
export interface BaselineInfo {
  baseline: BaselineId; version: string; approved: boolean; from: string | null; records: number; pages: number;
  fields: number; properties: { property: string; fields: number; ctdl_property: string | null }[];
  not_scored: { property: string; fields: number; why: string }[]; left_out: { stem: string; why: string }[];
}
export interface OutcomeCounts { fields: number; missing: number; wrong: number; partial: number; match: number }
export interface ScoreRow {
  key: string; page_stem: string; entity: number; golden_record_id: string | null; courses_on_page: number;
  property: string; ctdl_property: string; golden_value: string | null; xtra_value: string | null; _o: ScoreOutcome;
  similarity: number | null; approval: string | null; approved_by: string | null; template_id: string | null;
  source_url: string | null; golden_css_path: string | null; golden_char_start: number | null; golden_char_end: number | null;
}
export interface ScoreView {
  eval: { id: string; xtra_run: string; golden: { golden: string; approved: boolean }; commands: string[];
          summary: Record<string, { left_out: { stem: string; why: string }[] }> };
  kind: "hand" | "full"; baseline: BaselineId;
  total: OutcomeCounts & { records: number; match_rate: number | null };
  properties: (OutcomeCounts & { property: string })[];
  outcomes: OutcomeCounts;
  groups: (OutcomeCounts & { value: string })[];
  group_choices: { id: string; label: string }[];
  rows: { total: number; offset: number; page: number; items: ScoreRow[] };
}
