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
  /** A value in several pieces on the page: each piece, in page order (`text` is them joined by line breaks). */
  segments?: { text: string; css_path: string; char_start: number; char_end: number;
               quote?: { prefix: string; exact: string; suffix: string } }[];
}

/** What a note or a verdict made on a diff was compared with (Evals spec §4.2): xtra's extract output in a score,
 * or another ruleset version's value (Compare). `value`: the other side's value as it was shown. */
export type ComparedWith =
  | { kind: "extract"; score: string; value: string | null }
  | { kind: "ruleset"; ruleset: number; value: string | null };

export interface EventBrief {
  annotation_id: string; type: "verdict" | "comment" | "approve" | "reopen"; verdict: Verdict | null;
  author: string; at: string; note: string | null; expected: Expected | null;
  rule_version_seen: number | null; value_seen: string | null; page_stem?: string | null; author_role?: string | null;
  compared_with?: ComparedWith | null;
}

/** Evals §4.3: an expert confirmed the value (`human`: their verdict), or only an engineer did, waiting for an expert
 * (`checked`: the latest engineer's ✓, also the check an expert confirmed). */
export interface ReviewMarks {
  human_reviewed?: boolean; engineer_checked?: boolean; human?: EventBrief | null; checked?: EventBrief | null;
}

export interface Row extends ReviewMarks {
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
export interface CourseField extends ReviewMarks {
  /** who marked or commented on it: their verdict (correct · wrong) and note, and when (the "Annotated by" filter) */
  annotators?: Record<string, { kinds: string[]; at: string; role?: "sme" | "engineer" }>;
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
  compared_with?: ComparedWith;       // a note or a verdict made on a diff (Evals, Compare)
  extraction?: string;                // the extraction the target is in (default: the latest)
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

// --- Golden datasets (routes_golden.py; Evals spec §6.6) ------------------------------------------------
/** A golden dataset version's latest xtra score against the latest extract output. */
export interface GoldenScore {
  id: string; status: "done" | "running"; basis?: "human" | "rule"; rate?: number | null; values?: number; match?: number;
  output?: string; finished_at?: string | null;
}
export type GoldenTree = "rule-matched" | "human-reviewed";
/** One golden dataset version (ruleset-vN): its columns (CTDL terms without ceterms:), values and where it's written. */
export interface GoldenVersion {
  id: string; ruleset_version: number; latest: boolean; columns: string[]; values: number; human: number;
  published_at: string | null; created_at: string | null; published_by: string | null; extraction: string | null;
  score: GoldenScore | null;
  where: { root: string; version: string; trees: Record<GoldenTree, { prefix: string; pages: number | null }>;
           latest: string | null; studio: string };
}
export interface GoldenResponse {
  catalog: string; crawl: string; versions: GoldenVersion[]; latest_output: string | null; running: string | null;
}
/** What approving a rule publishes (the approve confirmation). `publishes` false: approved without writing files. */
export interface ApprovePreview {
  publishes: boolean; rule_id: string; property?: string; column?: string | null; golden?: string;
  ruleset_version?: number; creates?: boolean; now?: string[]; after?: string[]; where?: string;
  values?: number; human?: number; rule?: number;
}
/** The approve's answer: what it published (a column's rule) and the score it started. */
export interface AnnotateResponse {
  event: unknown; rule: RuleSummary | null; elapsed_ms: number;
  published?: { written?: boolean; publication?: string; created?: boolean; column?: string | null; columns?: string[];
                files?: number; property?: string; error?: string } | null;
  score?: { id: string; status: string; golden: string } | null;
}

export interface GoldenFileText { text: string; stem?: string; path?: string; records?: number; bytes?: number; truncated?: boolean;
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

// --- Evals (docs/qrspi/evals): extract outputs and scores against a golden dataset ----------------------------
export type ScoreOutcome = "missing" | "wrong" | "partial" | "match";
export type ScoreBasis = "human" | "rule";        // the human-reviewed values only; every rule-matched value
export interface OutcomeCounts { values: number; missing: number; wrong: number; partial: number; match: number }

/** The home page's catalogs table (Evals spec §6.1, §6.2): per catalog with rules, each column's status and the exact
 * matches of xtra's latest extract output against the latest golden dataset, on one basis (null: not scored yet). */
export type ColumnStatus = "published" | "in review" | "needs work";
export interface CatalogSummary {
  columns: Record<string, { status: ColumnStatus; ruleset: number | null }>;
  score: { id: string; golden: string; output: string; output_at: string | null; values: number;
    outcomes: Record<ScoreOutcome, number>; by_column: Record<string, OutcomeCounts>; implied: string[] } | null;
  error?: string;
}
export interface CatalogsSummary { basis: ScoreBasis; columns: string[]; not_in_studio: string[]; catalogs: Record<string, CatalogSummary> }
export interface ExtractOutput {
  id: string; path: string; report_etag: string; last_modified: string; run_id: string | null;
  discovery_run_id: string | null; only_golden_sample: boolean | null; records: number; records_written: number | null;
  records_mismatch: boolean; copy?: string; seen_at?: string;
}
export interface ScoreBrief {
  id: string; status: ScoreStatus; golden: string; output: string; created_at: string; error: string | null;
  human_rate: number | null; rule_rate: number | null; human_values: number | null; rule_values: number | null;
  human_outcomes: Record<ScoreOutcome, number> | null; rule_outcomes: Record<ScoreOutcome, number> | null;
  golden_kind: "version" | "human-reviewed" | "draft"; golden_as_of: string | null; finished_at: string | null;
  slot_names: boolean | null;
}
/** A golden dataset Evals can score against with Rule-matched: a published version, or a draft (an extraction). */
export interface GoldenChoice {
  id: string; kind: "version" | "draft"; ruleset_version: number; published_at: string | null; latest: boolean;
}
export type ScoreStatus = "running" | "done" | "failed" | "interrupted";
export interface ExtractOutputs {
  outputs: (ExtractOutput & { scores: ScoreBrief[] })[]; latest_golden: string | null; goldens: GoldenChoice[];
  error: string | null; running: string | null;
}
export interface ScoreResult {
  values: number; exact_match_rate: number | null; outcomes: Record<ScoreOutcome, number>;
  by_column: Record<string, OutcomeCounts>; implied: Record<string, number>; pages_scored: number;
  pages_skipped: number; pages_out_of_scope: number; malformed: number; left_out: { stem: string; why: string }[];
}
export interface ScoreDoc {
  id: string; status: ScoreStatus; created_at: string; finished_at: string | null; by: string; reason: string;
  error: string | null;
  golden: { id: string; kind: "version" | "human-reviewed" | "draft"; from: string; as_of: string; sha256: string;
            values?: Record<ScoreBasis, number> };
  output: ExtractOutput; slot_names: boolean | null; scorer: { xtra_cli_commit: string | null }; commands: string[];
  columns: string[]; results: Partial<Record<ScoreBasis, ScoreResult | null>>;
}
export interface ScoreRow {
  key: string; basis: ScoreBasis; column: string; ctdl_property: string; property: string | null;
  golden_record_id: string | null; page_stem: string; entity: number; outcome: ScoreOutcome; similarity: number | null;
  golden_value: string | null; extracted_value: string | null; source_url: string | null;
  golden_css_path: string | null; golden_char_start: number | null; golden_char_end: number | null;
  approval: string | null; approved_by: string | null; approved_at: string | null; subject: string | null;
  /** its Studio match, through the golden dataset's lineage: where a note or a verdict on it goes */
  rule_id: string | null; occurrence_key: string | null; value_index: number | null;
}
export interface ScoreValues {
  basis: ScoreBasis; result: ScoreResult | null; total: OutcomeCounts; columns: (OutcomeCounts & { column: string })[];
  outcomes: OutcomeCounts; groups: (OutcomeCounts & { name: string })[] | null;
  rows: { total: number; offset: number; page: number; items: ScoreRow[] };
}
/** `/match`: one field rule's row on one occurrence, with its verdict and comments (what a diff's actions act on). */
export interface MatchRow extends ReviewMarks {
  rule_id: string; kind: RuleKind; ctdl_property: string | null; property_label: string | null; extraction: string;
  key: string; occurrence_key: string; course_key: string | null; page_stem: string; value: string | null; status: string;
  css_path: string | null; char_start: number | null; char_end: number | null;
  state: RowStateName | null; verdict: EventBrief | null; comments: EventBrief[];
}
