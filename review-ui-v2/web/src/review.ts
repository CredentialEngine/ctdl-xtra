// Pure helpers over reviewer decisions; kept free of React so they can be unit-tested.
import type { Decision, Flag, GoldenResult, Note, PageSummary } from "./types";

export type CardState = "pending" | "accepted" | "rejected";

export function cardState(decision: Decision | undefined): CardState {
  if (!decision) return "pending";
  return decision.status === "accepted" ? "accepted" : "rejected";
}

export interface Progress {
  decided: number;
  total: number;
  rejected: number;
}

export function pageProgress(
  page: PageSummary,
  decisions: Record<string, Decision>,
): Progress {
  let decided = 0;
  let rejected = 0;
  for (const key of page.keys) {
    const decision = decisions[key];
    if (!decision) continue;
    decided += 1;
    if (decision.status !== "accepted") rejected += 1;
  }
  return { decided, total: page.keys.length, rejected };
}

/** Apply one saved event to local state, mirroring the server's fold. */
export function foldDecision(
  decisions: Record<string, Decision>,
  event: Record<string, unknown>,
): Record<string, Decision> {
  const next = { ...decisions };
  const key = event.key as string;
  if (event.status === "pending") delete next[key];
  else next[key] = event as unknown as Decision;
  return next;
}

export function foldNote(notes: Note[], event: Record<string, unknown>): Note[] {
  const rest = notes.filter((n) => n.id !== event.id);
  return (event.text as string).trim() ? [...rest, event as unknown as Note] : rest;
}

export function fieldNotes(notes: Note[], key: string): Note[] {
  return notes.filter((n) => n.scope === "field" && n.target === key);
}

export const addedKey = (recordId: string, label: string, url: string) =>
  `${recordId}::${label}::${url}::added::${Date.now().toString(36)}`;

export const manualLabelKey = (url: string, label: string) =>
  `label::${url}::${label}::manual`;

export const pageFlagKey = (stem: string) => `page::${stem}`;

/** Apply one saved flag event to local state, mirroring the server's fold. */
export function foldFlag(
  flags: Record<string, Flag>,
  event: Record<string, unknown>,
): Record<string, Flag> {
  const next = { ...flags };
  const target = event.target as string;
  if (event.flagged) next[target] = event as unknown as Flag;
  else delete next[target];
  return next;
}

export interface PageFlags {
  page: boolean;
  items: number;
  any: boolean;
}

/** Whether a page, or anything on it, is flagged: what the red flag in the list shows. */
export function pageFlags(stem: string, flags: Record<string, Flag>): PageFlags {
  let page = false;
  let items = 0;
  for (const flag of Object.values(flags)) {
    if (flag.stem !== stem) continue;
    if (flag.scope === "page") page = true;
    else items += 1;
  }
  return { page, items, any: page || items > 0 };
}

export function flagTotals(flags: Record<string, Flag>): { pages: number; items: number } {
  const all = Object.values(flags);
  const pages = all.filter((f) => f.scope === "page").length;
  return { pages, items: all.length - pages };
}

const plural = (n: number, word: string) => `${n} ${word}${n === 1 ? "" : "s"}`;

/** What to tell the reviewer after saving: what was saved and what was left out, and why. */
export function goldenMessage(result: GoldenResult): { text: string; incomplete: boolean } {
  const left = result.left_out;
  const reasons: string[] = [];
  if (left.not_reviewed) {
    const flagged = left.flagged ? ` (${left.flagged} flagged for an expert)` : "";
    reasons.push(`${left.not_reviewed} not reviewed yet${flagged}`);
  }
  if (left.rejected_without_correction)
    reasons.push(`${left.rejected_without_correction} rejected without a correction`);
  if (left.absent) reasons.push(`${left.absent} accepted as absent`);
  if (left.no_ctdl_property) reasons.push(`${left.no_ctdl_property} with no CTDL property`);
  const saved = `Saved ${plural(result.values, "value")} in ${plural(result.records, "record")}.`;
  return {
    text: reasons.length ? `${saved} Left out: ${reasons.join(", ")}.` : saved,
    incomplete: Boolean(left.not_reviewed || left.rejected_without_correction),
  };
}
