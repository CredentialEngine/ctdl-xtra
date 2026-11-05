// The highlight bar (sme-fixes §1): after a text selection on the page, a compact dark bar just above it says what the
// selection means. The actions are props, so each caller decides: a property rule's row has the comment bubble ·
// ✓ In answer · ✕ Not in answer; a list-of-objects rule has its field names (§5.3). Esc or a click elsewhere dismisses
// it. It is centred over the selection and always kept inside the pane, so a selection near an edge still shows it.
import { useLayoutEffect, useRef, useState, type ReactNode } from "react";
import type { CapturedSelection } from "./dom";

export interface BarAction {
  id: string;
  /** What the button shows: a short label ("✓ In answer") or an icon (<Ico name="bubble" />). */
  label: ReactNode;
  /** The informative tooltip (also its accessible name when the label is an icon). */
  title: string;
  /** `in` green, `out` red, `note` the comment bubble (separated from the rest by a thin rule). */
  tone?: "in" | "out" | "note";
  /** The bar stays up after this one (the comment bubble: then ✓ or ✕ for the same text); it shows as pressed. */
  keepOpen?: boolean;
  run(sel: CapturedSelection): void;
}

/** `x`: the middle of the selection, `y`: the bar's top, both in the pane's pixels. */
export interface BarAt { sel: CapturedSelection; x: number; y: number; /** the page's scroll when it was placed */ scrollY?: number }

const EDGE = 4;  // the gap kept between the bar and the pane's sides

/** The bar's left edge: centred on `x`, then moved inside a pane `paneW` wide. */
export function barLeft(x: number, barW: number, paneW: number): number {
  const centred = x - barW / 2;
  if (!paneW) return Math.max(EDGE, centred);
  return Math.max(EDGE, Math.min(centred, paneW - barW - EDGE));
}

export function HighlightBar({ at, actions, onDone }: { at: BarAt; actions: BarAction[]; onDone: () => void }) {
  const ref = useRef<HTMLDivElement>(null);
  const [left, setLeft] = useState(() => Math.max(EDGE, at.x));
  const [pressed, setPressed] = useState<string[]>([]);
  // measured before paint: the bar never shows outside the pane, even for one frame
  useLayoutEffect(() => {
    const el = ref.current;
    const pane = el?.parentElement;
    if (el && pane) setLeft(barLeft(at.x, el.offsetWidth, pane.clientWidth));
  }, [at.x, actions]);
  return (
    <div ref={ref} className="gpp-hbar" role="toolbar" aria-label="What this selection means" data-testid="highlight-bar"
      style={{ left, top: Math.max(EDGE, at.y) }}
      // keep the selection in the page while a button is pressed
      onMouseDown={(e) => e.preventDefault()}>
      {actions.map((a) => (
        <button key={a.id} type="button" className={`gpp-hb${a.tone ? ` hb-${a.tone}` : ""}`} title={a.title}
          aria-label={typeof a.label === "string" ? undefined : a.title} aria-pressed={a.keepOpen ? pressed.includes(a.id) : undefined}
          data-action={a.id} onClick={(e) => {
            e.stopPropagation();
            a.run(at.sel);
            if (a.keepOpen) setPressed((p) => (p.includes(a.id) ? p : [...p, a.id]));
            else onDone();
          }}>{a.label}</button>
      ))}
    </div>
  );
}
