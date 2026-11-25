// The Studio's loop, shown when the catalog picker opens (until "Don't show this again"): annotate the records a
// rule matched (left) → generate and apply better rules (right) → repeat until every rule of the catalog is
// approved as 100% correct. A dot leaves each box with a pulse, runs along the arrow and lands on the next box with a
// pulse, then a pause (no motion when the system asks for reduced motion).
import { useEffect, useRef, useState, type ReactNode, type RefObject } from "react";
import "./loop.css";

const KEY = "studio.loop.hidden";
const W = 520, H = 360, R = 172, CX = 260, CY = 180, GAP = 40;   // the ring, in the SVG's viewBox; GAP until measured
const ANGLES = [180, 0];                                          // box positions: left, then right (clockwise)
const STEPS = [
  { n: 1, t: "Annotate records", where: "Rules tab" },
  { n: 2, t: "Generate / apply better rules", where: "Claude Code, Compare" },
];
const N = STEPS.length;
const HOLD = 1500, TRAVEL = 1100;                                 // ms: a box holds the dot, then the dot's run
const SQUEEZE = 220;                                              // ms: the box squeezes before it fires the dot

const pt = (deg: number) => [CX + R * Math.cos((deg * Math.PI) / 180), CY + R * Math.sin((deg * Math.PI) / 180)];
function arc(a: number, b: number): string {
  const [x1, y1] = pt(a), [x2, y2] = pt(b);
  return `M ${x1.toFixed(1)} ${y1.toFixed(1)} A ${R} ${R} 0 0 1 ${x2.toFixed(1)} ${y2.toFixed(1)}`;
}
/** Fired: fast off the box, then still moving when it reaches the next one (no stall at the end of the arrow):
 *  speed 1.8× the average at launch, 0.35× on arrival. */
export const fired = (p: number) => 0.65 * (1 - (1 - p) ** 2.2) + 0.35 * p;

/** How far (degrees) the ring runs from a box's center to its edge, each way: the arrows start and end on the box. */
export function edgeGap(a: number, hw: number, hh: number, dir: 1 | -1, margin = 1): number {
  const [cx, cy] = pt(a);
  for (let d = 0; d < 90; d += 0.25) {
    const [x, y] = pt(a + dir * d);
    if (Math.abs(x - cx) > hw + margin || Math.abs(y - cy) > hh + margin) return d;
  }
  return GAP;
}

export function shouldShowLoop(): boolean {
  try { return localStorage.getItem(KEY) !== "1"; } catch { return true; }
}

type LoopRefs = ReturnType<typeof useLoopRefs>;
type Gaps = [number, number][];

export function LoopModal({ onClose }: { onClose: () => void }) {
  const [hide, setHide] = useState(false);
  const refs = useLoopRefs();
  const gaps = useBoxGaps(refs);
  const close = () => { if (hide) rememberHidden(); onClose(); };
  useFocusAndEscape(refs.ok, close);
  useTravellingDot(refs);
  return (
    <LoopDialog onClose={close}>
      <LoopRing refs={refs} gaps={gaps} />
      <LoopText />
      <LoopFoot hide={hide} setHide={setHide} okRef={refs.ok} onClose={close} />
    </LoopDialog>
  );
}

function LoopDialog({ onClose, children }: { onClose: () => void; children: ReactNode }) {
  return (
    <div className="loop-back" onClick={onClose}>
      <div className="loop" role="dialog" aria-modal="true" aria-labelledby="loop-h" onClick={(e) => e.stopPropagation()}>
        <h2 id="loop-h">How the Studio works</h2>
        {children}
      </div>
    </div>
  );
}

function LoopRing({ refs, gaps }: { refs: LoopRefs; gaps: Gaps }) {
  return (
    <div className="loop-ring" ref={refs.ring}>
      <svg viewBox={`0 0 ${W} ${H}`} aria-hidden="true">
        <LoopDefs />
        {ANGLES.map((_, i) => <path key={i} ref={(el) => { refs.paths.current[i] = el; }} d={arrowPath(i, gaps)}
          className="loop-arc" markerEnd="url(#loop-arrow)" />)}
        <circle ref={refs.dot} r="6" className="loop-dot" filter="url(#loop-glow)" style={{ opacity: 0 }} />
      </svg>
      {STEPS.map((s, i) => <LoopNode key={s.n} step={s} angle={ANGLES[i]} nodeRef={(el) => { refs.nodes.current[i] = el; }} />)}
      <div className="loop-center"><span className="loop-rep">↻ Repeat</span>until every rule is <b>100% correct</b> for that catalog</div>
    </div>
  );
}

function LoopDefs() {
  return (
    <defs>
      <marker id="loop-arrow" viewBox="0 0 10 10" refX="10" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
        <path d="M0 0 L10 5 L0 10 z" className="loop-head" />
      </marker>
      <filter id="loop-glow" x="-100%" y="-100%" width="300%" height="300%">
        <feGaussianBlur stdDeviation="3" result="b" /><feMerge><feMergeNode in="b" /><feMergeNode in="SourceGraphic" /></feMerge>
      </filter>
    </defs>
  );
}

function LoopNode({ step: s, angle, nodeRef }: { step: (typeof STEPS)[number]; angle: number; nodeRef: (el: HTMLDivElement | null) => void }) {
  const [x, y] = pt(angle);
  return (
    <div ref={nodeRef} className="loop-node"
      style={{ left: `${(100 * x) / W}%`, top: `${(100 * y) / H}%` }}>
      <span className="loop-n">{s.n}</span>
      <b>{s.t}</b>
      <span className="loop-w">{s.where}</span>
    </div>
  );
}

function LoopText() {
  return <>
    <ol className="loop-list">
      {STEPS.map((s) => <li key={s.n}><b>{s.t}</b> <span className="loop-w">{s.where}</span></li>)}
      <li className="loop-rep-li">↻ Repeat until every rule is 100% correct for that catalog.</li>
    </ol>
    <p className="loop-note"><b>Note:</b> the rules made here are not xtra's rules. They only help you label many
      records at once, and each set is made for one catalog. A later version of the Studio will show you what xtra
      itself extracts.</p>
  </>;
}

function LoopFoot({ hide, setHide, okRef, onClose }: {
  hide: boolean; setHide: (hide: boolean) => void; okRef: RefObject<HTMLButtonElement>; onClose: () => void;
}) {
  return (
    <div className="loop-foot">
      <label><input type="checkbox" checked={hide} onChange={(e) => setHide(e.target.checked)} /> Don't show this again</label>
      <button ref={okRef} className="btn primary" onClick={onClose}>Got it</button>
    </div>
  );
}

function useLoopRefs() {
  return {
    ok: useRef<HTMLButtonElement>(null),
    paths: useRef<(SVGPathElement | null)[]>([]),
    nodes: useRef<(HTMLDivElement | null)[]>([]),
    dot: useRef<SVGCircleElement>(null),
    ring: useRef<HTMLDivElement>(null),
  };
}

// [leaving, arriving] gap of each box, measured from the boxes as drawn
function useBoxGaps({ ring, nodes }: LoopRefs): Gaps {
  const [gaps, setGaps] = useState<Gaps>(() => ANGLES.map(() => [GAP, GAP]));
  useEffect(() => {
    const el = ring.current;
    if (!el) return;
    return observeSize(el, () => {
      const next = measureGaps(el, nodes.current);
      setGaps((g) => (JSON.stringify(g) === JSON.stringify(next) ? g : next));
    });
  }, []);
  return gaps;
}

function useFocusAndEscape(ok: RefObject<HTMLButtonElement>, close: () => void) {
  useEffect(() => {
    ok.current?.focus();
    const on = (e: KeyboardEvent) => { if (e.key === "Escape") close(); };
    window.addEventListener("keydown", on);
    return () => window.removeEventListener("keydown", on);
  });
}

// the dot: hold on box k (it pulses as the dot lands and leaves), then run along arrow k to box k+1
function useTravellingDot(refs: LoopRefs) {
  useEffect(() => {
    const still = typeof matchMedia === "function" && matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (still || typeof requestAnimationFrame !== "function") return;
    let raf = 0;
    const step = dotStepper(refs, performance.now());
    const frame = (now: number) => { step(now); raf = requestAnimationFrame(frame); };
    raf = requestAnimationFrame(frame);
    return () => cancelAnimationFrame(raf);
  }, []);
}

function dotStepper({ nodes, paths, dot }: LoopRefs, t0: number): (now: number) => void {
  let last = "";
  return (now) => {
    const t = (now - t0) % (N * (HOLD + TRAVEL));
    const k = Math.floor(t / (HOLD + TRAVEL));
    const local = t - k * (HOLD + TRAVEL);
    // the dot lands (k:land), the box squeezes just before it fires (k:send), the dot shoots out and glides on
    const event = local < HOLD - SQUEEZE ? `${k}:land` : `${k}:send`;
    if (event !== last) {
      pulse(nodes.current[k], event.endsWith("land") ? "land" : "send");
      last = event;
    }
    moveDot(paths.current[k], dot.current, local);
  };
}

function moveDot(path: SVGPathElement | null, d: SVGCircleElement | null, local: number): void {
  if (!path || !d) return;
  if (local < HOLD) { d.style.opacity = "0"; return; }
  const q = (local - HOLD) / TRAVEL;
  const at = path.getPointAtLength(fired(q) * path.getTotalLength());
  d.setAttribute("cx", String(at.x));
  d.setAttribute("cy", String(at.y));
  d.setAttribute("r", String(6 + 4 * Math.max(0, 1 - q / 0.18)));  // a burst at launch, settling to its size
  d.style.opacity = "1";
}

/** Pulse a box: `land` (a swell as the dot arrives; the box then glows while it holds the dot) or `send` (it
 *  squeezes and fires the dot, and stops glowing). */
function pulse(el: HTMLElement | null, kind: "send" | "land") {
  if (!el) return;
  el.classList.remove("send", "land");
  void el.offsetWidth;  // restart the animation
  el.classList.add(kind);
  el.classList.toggle("holding", kind === "land");
}

function observeSize(el: HTMLElement, measure: () => void): (() => void) | undefined {
  measure();
  if (typeof ResizeObserver !== "function") return;
  const ro = new ResizeObserver(measure);
  ro.observe(el);
  return () => ro.disconnect();
}

function measureGaps(el: HTMLElement, nodes: (HTMLDivElement | null)[]): Gaps {
  const scale = W / (el.clientWidth || W);
  return ANGLES.map((a, i): [number, number] => {
    const n = nodes[i];
    if (!n || !n.offsetWidth) return [GAP, GAP];
    const hw = (n.offsetWidth / 2) * scale, hh = (n.offsetHeight / 2) * scale;
    return [edgeGap(a, hw, hh, 1), edgeGap(a, hw, hh, -1)];
  });
}

function arrowPath(i: number, gaps: Gaps): string {
  const a = ANGLES[i];
  const j = (i + 1) % N, b = ANGLES[j] <= a ? ANGLES[j] + 360 : ANGLES[j];   // clockwise to the next box
  return arc(a + gaps[i][0], b - gaps[j][1]);
}

function rememberHidden(): void {
  try { localStorage.setItem(KEY, "1"); } catch { /* private */ }
}
