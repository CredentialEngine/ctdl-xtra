// Loading previews: quiet gray shapes where data is on its way, so a page that is waiting says so without drawing the
// eye (a slow, low-contrast shimmer; still for people who ask for reduced motion). Shaped like what will replace them,
// so nothing jumps when the data lands. Used where a class or catalog switch reloads a list, a record or a table.
import type { CSSProperties } from "react";

/** One bar. */
export function Skel({ w = "100%", h = 12, r = 4, style }: { w?: number | string; h?: number; r?: number; style?: CSSProperties }) {
  return <span className="skel" aria-hidden style={{ width: w, height: h, borderRadius: r, ...style }} />;
}

/** A sidebar list (rules, records): rows of a title and a shorter line under it. */
export function SkelList({ rows = 9, label, heads = true }: { rows?: number; label: string; heads?: boolean }) {
  const widths = [72, 58, 80, 64, 50, 76, 62, 68, 54, 70];
  return (
    <div className="skel-list" role="status" aria-label={label} data-testid="loading">
      {Array.from({ length: rows }, (_, i) => (
        <div key={i} className="skel-item">
          {heads && i % 4 === 0 && <Skel w="34%" h={10} style={{ marginBottom: 12 }} />}
          <Skel w={`${widths[i % widths.length]}%`} h={13} />
          <Skel w={`${widths[(i + 3) % widths.length] - 22}%`} h={10} style={{ marginTop: 7 }} />
        </div>
      ))}
    </div>
  );
}

/** Cards (a rule's rows, a record's properties): a bordered box with a few lines. */
export function SkelCards({ n = 4, label }: { n?: number; label: string }) {
  return (
    <div className="skel-cards" role="status" aria-label={label} data-testid="loading">
      {Array.from({ length: n }, (_, i) => (
        <div key={i} className="skel-card">
          <Skel w="22%" h={11} />
          <Skel w="88%" h={14} style={{ marginTop: 14 }} />
          <Skel w={`${60 + (i * 13) % 30}%`} h={14} style={{ marginTop: 9 }} />
        </div>
      ))}
    </div>
  );
}

/** A heading block (a rule's name, its term and input). */
export function SkelHead() {
  return (
    <div className="skel-head" aria-hidden>
      <Skel w="30%" h={18} /><Skel w="18%" h={12} style={{ marginTop: 10 }} /><Skel w="24%" h={12} style={{ marginTop: 8 }} />
    </div>
  );
}

/** A table body: `rows` lines of `cols` short bars. */
export function SkelTable({ rows = 6, cols = 8, label }: { rows?: number; cols?: number; label: string }) {
  return (
    <div className="skel-table" role="status" aria-label={label} data-testid="loading">
      {Array.from({ length: rows }, (_, i) => (
        <div key={i} className="skel-tr">
          <Skel w={150} h={14} />
          {Array.from({ length: cols }, (_, j) => <Skel key={j} w={34} h={12} />)}
        </div>
      ))}
    </div>
  );
}
