// The highlight bar (sme-fixes §1): after a text selection on the page, a compact dark bar just above it says what the
// selection means. The actions are props, so each caller decides: a property rule's row has 💬 · ✓ In answer ·
// ✕ Not in answer; a list-of-objects rule has its field names (§5.3). Esc or a click elsewhere dismisses it.
import type { CapturedSelection } from "./dom";

export interface BarAction {
  id: string;
  /** What the button shows: a short label ("✓ In answer") or an icon ("💬"). */
  label: string;
  /** The informative tooltip (also its accessible name when the label is an icon). */
  title: string;
  /** `in` green, `out` red, `note` the comment bubble (separated from the rest by a thin rule). */
  tone?: "in" | "out" | "note";
  run(sel: CapturedSelection): void;
}

export interface BarAt { sel: CapturedSelection; x: number; y: number }

export function HighlightBar({ at, actions, onDone }: { at: BarAt; actions: BarAction[]; onDone: () => void }) {
  return (
    <div className="gpp-hbar" role="toolbar" aria-label="What this selection means" data-testid="highlight-bar"
      style={{ left: Math.max(4, at.x), top: Math.max(4, at.y) }}
      // keep the selection in the page while a button is pressed
      onMouseDown={(e) => e.preventDefault()}>
      {actions.map((a) => (
        <button key={a.id} type="button" className={`gpp-hb${a.tone ? ` ${a.tone}` : ""}`} title={a.title} aria-label={a.tone === "note" ? a.title : undefined}
          data-action={a.id} onClick={(e) => { e.stopPropagation(); a.run(at.sel); onDone(); }}>{a.label}</button>
      ))}
    </div>
  );
}
