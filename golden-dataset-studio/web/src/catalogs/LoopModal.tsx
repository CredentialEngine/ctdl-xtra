// The Studio's loop, shown when the catalog picker opens (until "Don't show this again"): annotate the records a
// rule matched → Claude Code generates better rules → apply them → repeat until every rule of the catalog is
// approved as 100% correct. A dot leaves each box with a pulse, runs along the arrow and lands on the next box with a
// pulse, then a pause (no motion when the system asks for reduced motion).
import { useEffect, useRef, useState } from "react";
import "./loop.css";

const KEY = "studio.loop.hidden";
const W = 520, H = 400, R = 148, CX = 260, CY = 212, GAP = 40;   // the ring, in the SVG's viewBox; GAP until measured
const ANGLES = [-90, 30, 150];                                    // box positions, clockwise from the top
const STEPS = [
  { n: 1, t: "Annotate records", where: "Rules tab" },
  { n: 2, t: "Generate better rules", where: "Claude Code" },
  { n: 3, t: "Apply new rules", where: "Compare tab" },
];
const HOLD = 900, TRAVEL = 1300;                                  // ms: pause on a box, then the dot's run

const pt = (deg: number) => [CX + R * Math.cos((deg * Math.PI) / 180), CY + R * Math.sin((deg * Math.PI) / 180)];
function arc(a: number, b: number): string {
  const [x1, y1] = pt(a), [x2, y2] = pt(b);
  return `M ${x1.toFixed(1)} ${y1.toFixed(1)} A ${R} ${R} 0 0 1 ${x2.toFixed(1)} ${y2.toFixed(1)}`;
}
const ease = (p: number) => (p < 0.5 ? 2 * p * p : 1 - (-2 * p + 2) ** 2 / 2);

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

/** Pulse a box: `send` (a quick press as the dot leaves) or `land` (a swell and a glow as it arrives). */
function pulse(el: HTMLElement | null, kind: "send" | "land") {
  if (!el) return;
  el.classList.remove("send", "land");
  void el.offsetWidth;  // restart the animation
  el.classList.add(kind);
}

export function LoopModal({ onClose }: { onClose: () => void }) {
  const [hide, setHide] = useState(false);
  const ok = useRef<HTMLButtonElement>(null);
  const paths = useRef<(SVGPathElement | null)[]>([]);
  const nodes = useRef<(HTMLDivElement | null)[]>([]);
  const dot = useRef<SVGCircleElement>(null);
  const ring = useRef<HTMLDivElement>(null);
  // [leaving, arriving] gap of each box, measured from the boxes as drawn
  const [gaps, setGaps] = useState<[number, number][]>(() => ANGLES.map(() => [GAP, GAP]));
  useEffect(() => {
    const el = ring.current;
    if (!el) return;
    const measure = () => {
      const scale = W / (el.clientWidth || W);
      const next = ANGLES.map((a, i): [number, number] => {
        const n = nodes.current[i];
        if (!n || !n.offsetWidth) return [GAP, GAP];
        const hw = (n.offsetWidth / 2) * scale, hh = (n.offsetHeight / 2) * scale;
        return [edgeGap(a, hw, hh, 1), edgeGap(a, hw, hh, -1)];
      });
      setGaps((g) => (JSON.stringify(g) === JSON.stringify(next) ? g : next));
    };
    measure();
    if (typeof ResizeObserver !== "function") return;
    const ro = new ResizeObserver(measure);
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  const close = () => { if (hide) { try { localStorage.setItem(KEY, "1"); } catch { /* private */ } } onClose(); };

  useEffect(() => {
    ok.current?.focus();
    const on = (e: KeyboardEvent) => { if (e.key === "Escape") close(); };
    window.addEventListener("keydown", on);
    return () => window.removeEventListener("keydown", on);
  });

  // the dot: hold on box k (it pulses as the dot lands and leaves), then run along arrow k to box k+1
  useEffect(() => {
    const still = typeof matchMedia === "function" && matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (still || typeof requestAnimationFrame !== "function") return;
    let raf = 0, last = -1;
    const t0 = performance.now();
    const frame = (now: number) => {
      const t = (now - t0) % (3 * (HOLD + TRAVEL));
      const k = Math.floor(t / (HOLD + TRAVEL));
      const local = t - k * (HOLD + TRAVEL);
      const phase = 2 * k + (local < HOLD ? 0 : 1);           // even: holding on box k; odd: running from k
      if (phase !== last) {
        pulse(nodes.current[k], phase % 2 === 0 ? "land" : "send");
        last = phase;
      }
      const path = paths.current[k], d = dot.current;
      if (path && d) {
        if (local < HOLD) d.style.opacity = "0";
        else {
          const p = ease((local - HOLD) / TRAVEL);
          const at = path.getPointAtLength(p * path.getTotalLength());
          d.setAttribute("cx", String(at.x));
          d.setAttribute("cy", String(at.y));
          d.style.opacity = "1";
        }
      }
      raf = requestAnimationFrame(frame);
    };
    raf = requestAnimationFrame(frame);
    return () => cancelAnimationFrame(raf);
  }, []);

  return (
    <div className="loop-back" onClick={close}>
      <div className="loop" role="dialog" aria-modal="true" aria-labelledby="loop-h" onClick={(e) => e.stopPropagation()}>
        <h2 id="loop-h">How the Studio works</h2>
        <div className="loop-ring" ref={ring}>
          <svg viewBox={`0 0 ${W} ${H}`} aria-hidden="true">
            <defs>
              <marker id="loop-arrow" viewBox="0 0 10 10" refX="10" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
                <path d="M0 0 L10 5 L0 10 z" className="loop-head" />
              </marker>
              <filter id="loop-glow" x="-100%" y="-100%" width="300%" height="300%">
                <feGaussianBlur stdDeviation="3" result="b" /><feMerge><feMergeNode in="b" /><feMergeNode in="SourceGraphic" /></feMerge>
              </filter>
            </defs>
            {ANGLES.map((a, i) => (
              <path key={i} ref={(el) => { paths.current[i] = el; }}
                d={arc(a + gaps[i][0], ANGLES[(i + 1) % 3] + (i === 2 ? 360 : 0) - gaps[(i + 1) % 3][1])}
                className="loop-arc" markerEnd="url(#loop-arrow)" />
            ))}
            <circle ref={dot} r="6" className="loop-dot" filter="url(#loop-glow)" style={{ opacity: 0 }} />
          </svg>
          {STEPS.map((s, i) => {
            const [x, y] = pt(ANGLES[i]);
            return (
              <div key={s.n} ref={(el) => { nodes.current[i] = el; }} className="loop-node"
                style={{ left: `${(100 * x) / W}%`, top: `${(100 * y) / H}%` }}>
                <span className="loop-n">{s.n}</span>
                <b>{s.t}</b>
                <span className="loop-w">{s.where}</span>
              </div>
            );
          })}
          <div className="loop-center"><span className="loop-rep">↻ Repeat</span>until every rule is <b>100% correct</b> for that catalog</div>
        </div>
        <ol className="loop-list">
          {STEPS.map((s) => <li key={s.n}><b>{s.t}</b> <span className="loop-w">{s.where}</span></li>)}
          <li className="loop-rep-li">↻ Repeat until every rule is 100% correct for that catalog.</li>
        </ol>
        <div className="loop-foot">
          <label><input type="checkbox" checked={hide} onChange={(e) => setHide(e.target.checked)} /> Don't show this again</label>
          <button ref={ok} className="btn primary" onClick={close}>Got it</button>
        </div>
      </div>
    </div>
  );
}
