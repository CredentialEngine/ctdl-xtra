// The shared value diff (Evals spec §6.4, §6.5): a word diff of two values, cut into the two sides of a GitHub-style
// split view. Longest common subsequence over words (and the spaces between them); a value is at most a few hundred
// words, so the table stays small.
import type { DiffPart } from "../api/types";
import { compactDiff, type ShownPart } from "../compare/diff";

export type { ShownPart };
const MAX_TOKENS = 1500;

/** `a` → `b`: `del` is only in `a`, `add` only in `b`. */
export function wordDiff(a: string, b: string): DiffPart[] {
  const x = a.split(/(\s+)/).filter(Boolean), y = b.split(/(\s+)/).filter(Boolean);
  if (x.length > MAX_TOKENS || y.length > MAX_TOKENS) return [{ op: "del", text: a }, { op: "add", text: b }];
  const n = x.length, m = y.length;
  const L = Array.from({ length: n + 1 }, () => new Uint16Array(m + 1));
  for (let i = n - 1; i >= 0; i--)
    for (let j = m - 1; j >= 0; j--)
      L[i][j] = x[i] === y[j] ? L[i + 1][j + 1] + 1 : Math.max(L[i + 1][j], L[i][j + 1]);
  const out: DiffPart[] = [];
  const push = (op: DiffPart["op"], text: string) => {
    const last = out[out.length - 1];
    if (last && last.op === op) last.text += text; else out.push({ op, text });
  };
  let i = 0, j = 0;
  while (i < n && j < m) {
    if (x[i] === y[j]) { push("same", x[i]); i++; j++; }
    else if (L[i + 1][j] >= L[i][j + 1]) push("del", x[i++]);
    else push("add", y[j++]);
  }
  while (i < n) push("del", x[i++]);
  while (j < m) push("add", y[j++]);
  return out;
}

/** The two sides of a split view: the left keeps `same` and `del`, the right `same` and `add`. `compact` shortens long
 * unchanged stretches (Compare's rows stay a few lines). Whitespace-only changes stay unmarked. */
export function sides(a: string | null, b: string | null, compact = false): { left: ShownPart[]; right: ShownPart[] } {
  const parts = wordDiff(a ?? "", b ?? "");
  const shown: ShownPart[] = compact ? compactDiff(parts, 160, 60) : parts;
  const keep = (drop: DiffPart["op"]) => shown.filter((p) => p.op !== drop)
    .map((p) => (p.op !== "same" && p.op !== "gap" && !p.text.trim() ? { op: "same" as const, text: p.text } : p));
  return { left: keep("add"), right: keep("del") };
}

/** True when the two values differ only in spacing (the scorer and review.norm ignore it). */
export const sameText = (a: string | null, b: string | null) =>
  (a ?? "").replace(/\s+/g, " ").trim() === (b ?? "").replace(/\s+/g, " ").trim();

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
/** "28 Oct" in the browser's time zone. */
export function fmtDay(iso: string | null | undefined): string {
  if (!iso) return "";
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? "" : `${d.getDate()} ${MONTHS[d.getMonth()]}`;
}
/** "28 Oct, 3:40 PM" in the browser's time zone. */
export function fmtDayTime(iso: string | null | undefined): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  const h = d.getHours() % 12 || 12;
  return `${fmtDay(iso)}, ${h}:${String(d.getMinutes()).padStart(2, "0")} ${d.getHours() < 12 ? "AM" : "PM"}`;
}
