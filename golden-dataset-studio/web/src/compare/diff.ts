// Word-diff helpers for Compare (spec §7.4): shorten long unchanged stretches so a row stays two or three lines.
import type { AnnotatedRow, DiffPart } from "../api/types";

/** A diff part ready to render; `gap` marks where unchanged text was cut. */
export interface ShownPart { op: DiffPart["op"] | "gap"; text: string }

const cutStart = (t: string, n: number) => {
  const s = t.slice(0, n);
  const sp = s.lastIndexOf(" ");
  return sp > n / 2 ? s.slice(0, sp) : s;
};
const cutEnd = (t: string, n: number) => {
  const s = t.slice(-n);
  const sp = s.indexOf(" ");
  return sp >= 0 && sp < n / 2 ? s.slice(sp + 1) : s;
};

/**
 * Keep every change; shorten unchanged text longer than `max` characters to `edge` characters of context on the side
 * that touches a change (both sides for a stretch between two changes).
 */
export function compactDiff(parts: DiffPart[], max = 120, edge = 50): ShownPart[] {
  const out: ShownPart[] = [];
  parts.forEach((p, i) => {
    if (p.op !== "same" || p.text.length <= max) { out.push(p); return; }
    const first = i === 0, last = i === parts.length - 1;
    if (first && last) { out.push({ op: "same", text: cutStart(p.text, max) }, { op: "gap", text: " …" }); return; }
    if (!first) out.push({ op: "same", text: cutStart(p.text, edge) });
    out.push({ op: "gap", text: first ? "… " : last ? " …" : " … " });
    if (!last) out.push({ op: "same", text: cutEnd(p.text, edge) });
  });
  return out;
}

/** True when the diff has no change (the value is the same in both versions). */
export const unchanged = (parts: DiffPart[]) => parts.every((p) => p.op === "same");

/** The outcome badge's label and class: a correct row that didn't change is "still correct" (screen 08). */
export function outcomeLabel(r: Pick<AnnotatedRow, "verdict" | "outcome">): { label: string; cls: string } {
  if (r.outcome === "unchanged") return r.verdict === "correct"
    ? { label: "still correct", cls: "still-correct" } : { label: "unchanged", cls: "still-correct" };
  return { label: r.outcome, cls: r.outcome.replace(" ", "-") };
}

/** "+2", "-274", "–" */
export const delta = (a: number, b: number) => (b - a > 0 ? `+${b - a}` : b - a < 0 ? `-${a - b}` : "–");
