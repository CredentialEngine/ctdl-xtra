// Findings (learning-programs Phase 6): how a Where-it's-wrong group is named as a link and a thread, and which
// finding covers it. The keys match the server's (`findings.link_key`, `findings.thread_key`).
import type { FindingLink, FindingX, PropertyReview, WrongGroup } from "../api/types";

export const linkOf = (catalog: string, g: Pick<WrongGroup, "outcome" | "field" | "by" | "key">, groupBy: string): FindingLink =>
  ({ catalog, outcome: g.outcome, field: g.field ?? null, by: g.by, key: g.key, group_by: groupBy });

const same = (a: Omit<FindingLink, "group_by">, b: Omit<FindingLink, "group_by">) =>
  a.catalog === b.catalog && a.outcome === b.outcome && (a.field ?? null) === (b.field ?? null) && a.by === b.by && a.key === b.key;

/** The finding that covers this group, if any. */
export function findingOf(review: PropertyReview | null, link: FindingLink): FindingX | null {
  return review?.findings.find((f) => f.links.some((l) => same(l, link))) ?? null;
}

export const groupThread = (l: Omit<FindingLink, "group_by">) =>
  `group:${l.catalog}|${l.outcome}|${l.field ?? ""}|${l.by}|${l.key}`;
export const findingThread = (id: string) => `finding:${id}`;

/** A column as its CTDL term, as the score views show it: "ceterms:description", "creditValue → minValue". */
export function termOfColumn(col: string): string {
  if (col.includes(">")) return col.replace(/>/g, " → ");
  return /\s/.test(col) ? col : `ceterms:${col}`;
}

export const WHOSE = ["silver", "extractor", "baseline", "normalization"] as const;
export const COUNTED = ["partial", "wrong", "missing"] as const;

/** A finding's counts: live from its linked groups, else the running notes'. Each is [golden, silver] or null. */
export function countsOf(f: FindingX): Record<(typeof COUNTED)[number], [number, number] | null> {
  const src = f.live?.counts ?? f.counts ?? {};
  return { partial: src.partial ?? null, wrong: src.wrong ?? null, missing: src.missing ?? null };
}

/** The catalogs a finding covers, as words: the notes' "WVU 286, Marshall 31", else its linked catalogs. */
export function catalogsOf(f: FindingX, name: (short: string) => string): string {
  if (f.live) return [...new Set(f.live.rows.map((r) => name(r.catalog)))].join(", ");
  return f.catalogs ?? "";
}
