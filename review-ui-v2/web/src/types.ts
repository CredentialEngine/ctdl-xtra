export type Status = "accepted" | "rejected" | "missing";
export type Author = "Jared" | "Seth";
export type NoteScope = "field" | "rule" | "property" | "general";
export type FlagScope = "page" | "field" | "label";

export interface Location {
  css_path: string;
  char_start: number;
  char_end: number;
}

export interface Field {
  canonical_label: string;
  ctdl_property: string | null;
  value: string | null;
  presence: "present" | "absent";
  rule_id: string | null;
  rule_type: string | null;
  source_url: string;
  field_id: string;
  location: Location | null;
  raw_text: string | null;
}

export interface Conflict {
  canonical_label: string;
  values: { value: string; source_urls: string[] }[];
}

export interface RecordView {
  record_id: string;
  conflicts: Conflict[];
  source_urls: string[];
  fields: Field[];
}

export interface LabelView {
  key: string;
  label: string;
  rule_id: string;
}

export interface PageView {
  stem: string;
  url: string;
  page_type: string;
  labels: LabelView[];
  records: RecordView[];
}

export interface PageSummary {
  stem: string;
  url: string;
  page_type: string;
  reason: string;
  title: string;
  labels: string[];
  record_count: number;
  keys: string[];
}

export interface Decision {
  key: string;
  kind: "field" | "label";
  status: Status;
  canonical_label: string;
  source_url: string;
  record_id?: string;
  rule_id?: string | null;
  value?: string | null;
  expected_value?: string;
  reasons: string[];
  author: string;
  at: string;
  carried_from?: string;
}

export interface Note {
  id: string;
  scope: NoteScope;
  target: string | null;
  text: string;
  author: string;
  at: string;
}

/** A page, label or field the reviewer cannot judge and wants an expert to look at. */
export interface Flag {
  target: string;
  scope: FlagScope;
  stem: string;
  source_url: string;
  canonical_label?: string;
  record_id?: string;
  note: string;
  author: string;
  at: string;
  carried_from?: string;
}

export interface Counts {
  total: number;
  accepted: number;
  rejected: number;
  missing: number;
  pending: number;
  flagged_pages: number;
  flagged_items: number;
}

export interface TemplateProperty {
  name: string;
  term: string | null;
  section: string;
  required: boolean;
  multiple: boolean;
}

export interface Boot {
  run: { key: string; catalog_folder: string };
  extraction: {
    id: string;
    ruleset: { id: string; version: number };
    records: number;
    regression: { accepted_checked: number; regressions: unknown[]; fixed: number; still_wrong: number };
  };
  review: {
    session: { review_id: string; extraction_id: string };
    decisions: Record<string, Decision>;
    notes: Note[];
    flags: Record<string, Flag>;
    counts: Counts;
  };
  reviews: string[];
  pages: PageSummary[];
  properties: TemplateProperty[];
  label_vocabulary: string[];
  reasons: string[];
  note_scopes: NoteScope[];
  golden: string[]; // pages that already have a saved golden dataset
}

export type DecisionEvent = {
  type: "decision";
  kind: "field" | "label";
  key: string;
  status: Status | "pending";
  canonical_label: string;
  source_url: string;
  record_id?: string;
  rule_id?: string | null;
  value?: string | null;
  expected_value?: string;
  reasons?: string[];
};

export type NoteEvent = {
  type: "note";
  id?: string;
  scope: NoteScope;
  target: string | null;
  text: string;
};

export type FlagEvent = {
  type: "flag";
  scope: FlagScope;
  target: string;
  stem: string;
  source_url: string;
  canonical_label?: string;
  record_id?: string;
  flagged: boolean;
  note?: string;
};

export interface CatalogSummary {
  cid: string;
  catalog_folder: string;
  run_key: string;
  run_id: string;
  seed_url: string;
  pages: number;
  ruleset: { id: string; version: number; rules: number } | null;
  ruleset_error: string | null;
  extraction: { id: string; records: number; ruleset_version: number; stale: boolean; legacy: boolean } | null;
  has_sample: boolean;
  ready: boolean;
  hint: string | null;
  review: { review_id: string; counts: Counts } | null;
}

export interface CatalogList {
  catalogs: CatalogSummary[];
  default: string | null;
}

/** Why values were not saved to a golden dataset (counts, only the non-zero ones). */
export interface GoldenLeftOut {
  not_reviewed?: number;
  flagged?: number;
  rejected_without_correction?: number;
  absent?: number;
  no_ctdl_property?: number;
}

export interface GoldenResult {
  key: string;
  location: string;
  values: number;
  records: number;
  datasets: number;
  left_out: GoldenLeftOut;
}
