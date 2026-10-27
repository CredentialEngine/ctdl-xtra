// Fields routes_compare.py / scorecard.py return beyond web/src/api/types.ts. Optional, so the tab also works
// against the shared types alone. (To fold into api/types.ts: see the W5 report.)
import type { AnnotatedRow, CompareResponse, RuleCard, SignalDelta } from "../api/types";

export interface SignalDeltaX extends SignalDelta { lost_total?: number; gained_total?: number }
export interface AnnotatedRowX extends AnnotatedRow {
  /** History signal of this row in this comparison (spec §8). */
  history?: "previously-wrong" | "previously-correct" | "changed-since-correct";
}
export interface RuleCardX extends Omit<RuleCard, "signals" | "annotated_rows"> {
  signals: SignalDeltaX[]; annotated_rows: AnnotatedRowX[];
  /** All changed records not in `annotated_rows`; `sample` is a seeded random few of them. */
  sample_total?: number;
}
export interface CompareResponseX extends Omit<CompareResponse, "rules"> { rules: RuleCardX[] }
