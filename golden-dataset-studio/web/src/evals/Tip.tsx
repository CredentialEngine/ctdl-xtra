// Tooltips, the explanations they hold, and the small outcome bars they explain.
import { useEffect, useRef, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";
import type { OutcomeCounts } from "../api/types";
import { fmt } from "../shell/ui";
import { BAR_ORDER, num, OUTCOME_RULE, SIMILARITY, total, type Counts } from "./score";

/** The ⓘ beside "scored against": which values each choice scores. */
export const BASIS_TIP = <span className="evx-tip-basis">
  <b>Rule-matched</b> scores every value in the golden dataset: the values the rules matched and the human-reviewed ones.
  <br /><b>Human-reviewed</b> scores only the values an expert reviewed.</span>;
/** The two numbers per column, under plain names, with their formulas (sme-fixes Q10.9). */
export const FOUND_TIP = <span><b>Found</b> (recall): the golden values xtra got exactly.<br />
  found = match ÷ golden values = match ÷ (match + partial + wrong + missing + unsure)</span>;
export const RIGHT_TIP = <span><b>Right</b> (precision): the candidates that are exactly a golden value.<br />
  right = match ÷ candidates = match ÷ (match + partial + wrong + extra)</span>;
export const COURSES_TIP = <span><b>Courses exact</b>, for a list property (durations): courses whose whole list is exact
  (no wrong, missing or extra item) ÷ courses.</span>;

interface TipProps { tip: ReactNode; width?: number; delay?: number; children: ReactNode }
interface TipPlace { left: number; top: number; maxWidth: number }

/** A dark tooltip under its children while hovered or focused, fixed to the viewport so a scrolling column never
 * clips it; `delay` (ms) holds it back on hover so passing the pointer over doesn't flash it. */
export function Tip({ tip, width = 340, delay = 0, children }: TipProps) {
  const { at, show, hide } = useTipPlace(width, delay);
  return (
    <span className="evx-tipw" onMouseEnter={show} onMouseLeave={hide} onFocus={show} onBlur={hide}>
      {children}
      {at && createPortal(<span ref={(el) => keepInWindow(el)} className="evx-tip" role="tooltip" style={{ ...at, transform: "translateX(-50%)" }}>{tip}</span>,
        document.body)}
    </span>
  );
}

/** Hovering a bar or a legend colour: each outcome, its count and its rule, and how similarity is computed. */
export function OutcomeTip({ counts, title, children }: { counts: Counts | OutcomeCounts | null; title?: string; children: ReactNode }) {
  return (
    <Tip tip={<>
      {title && <span className="hd">{title}</span>}
      <table><tbody>
        {BAR_ORDER.map((o) => (
          <tr key={o}><td><i className={`sw o-${o}`} />{o}</td>{counts && <td className="n">{fmt(num(counts, o))}</td>}<td>{OUTCOME_RULE[o]}</td></tr>
        ))}
      </tbody></table>
      <span className="ft">{SIMILARITY}</span>
    </>}>{children}</Tip>
  );
}

/** One bar: the golden side's outcomes, then the extras striped (candidates with no golden value). */
export function Bar({ c }: { c: OutcomeCounts }) {
  return (
    <span className="evx-bar" role="img" aria-label={BAR_ORDER.map((o) => `${o} ${num(c, o)}`).join(", ")}>
      {BAR_ORDER.filter((o) => num(c, o) > 0).map((o) => <i key={o} className={`o-${o}`} style={{ flexGrow: num(c, o) }} />)}
    </span>
  );
}

export function MiniBar({ c }: { c: Counts | null }) {
  const n = total(c);
  return <i className="evx-mini">{c && n ? BAR_ORDER.map((k) => num(c, k) > 0 && <b key={k} className={`o-${k}`} style={{ height: `${Math.max(1, (num(c, k) / n) * 14)}px` }} />) : null}</i>;
}

function useTipPlace(width: number, delay: number) {
  const [at, setAt] = useState<TipPlace | null>(null);
  const timer = useRef<number | undefined>(undefined);
  useEffect(() => () => window.clearTimeout(timer.current), []);
  const open = (el: HTMLElement) => setAt(placeUnder(el, width));
  const show = (e: { currentTarget: HTMLElement }) => {
    const el = e.currentTarget;
    window.clearTimeout(timer.current);
    if (delay > 0) timer.current = window.setTimeout(() => open(el), delay); else open(el);
  };
  const hide = () => { window.clearTimeout(timer.current); setAt(null); };
  return { at, show, hide };
}

function placeUnder(el: HTMLElement, width: number): TipPlace {
  const r = el.getBoundingClientRect();
  return { left: r.left + r.width / 2, top: r.bottom + 8, maxWidth: Math.min(width, window.innerWidth - 16) };
}

/** Centred under its children, then kept inside the window. */
function keepInWindow(el: HTMLSpanElement | null) {
  if (!el) return;
  const r = el.getBoundingClientRect();
  const left = Math.max(8, Math.min(r.left, window.innerWidth - r.width - 8));
  if (Math.abs(left - r.left) > 0.5) el.style.left = `${parseFloat(el.style.left) + left - r.left}px`;
}
