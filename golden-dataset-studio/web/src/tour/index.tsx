// The tour (spec §7.8). `useTour` decides when it opens: by itself the first time a catalog is opened in this
// browser, then only from "Show the tour". `Tour` runs it: it starts on the Rules tab, lights one real area per
// step with a short card beside it, does and undoes each step's action, and returns the reader to where they were.
import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../api/client";
import type { CatalogDetail } from "../api/types";
import { go } from "../shell/router";
import {
  browserStore, clip, makeCtx, markSeen, placeCard, shouldAutoOpen, TourSession, union, type Box, type Nav, type TourCtx,
} from "./model";
import { STEPS, type Facts, type Step, type Target } from "./steps";
import "./tour.css";

export function useTour(catalog: CatalogDetail | null) {
  const [isOpen, setOpen] = useState(false);
  const short = catalog?.short ?? null;
  useEffect(() => {
    if (!short) return;
    const store = browserStore();
    if (shouldAutoOpen(store)) { markSeen(store); setOpen(true); }
  }, [short]);
  return { isOpen, open: useCallback(() => setOpen(true), []), close: useCallback(() => setOpen(false), []) };
}

export interface TourProps { isOpen: boolean; open: () => void; close: () => void; catalog: CatalogDetail; steps?: Step[] }

export function Tour({ isOpen, close, catalog, steps = STEPS }: TourProps) {
  if (!isOpen) return null;
  return <TourRun key={catalog.short} catalog={catalog} close={close} steps={steps} />;
}

const hashNav: Nav = { get: () => location.hash || "#/", set: (h) => go(h, true) };

const ABSENT_MS = 6000;
const CARD_W = 372;

interface View { boxes: Box[]; accents: Box[]; facts: Facts; state: "waiting" | "found" | "absent"; card: { left: number; top: number } | null }
const EMPTY: View = { boxes: [], accents: [], facts: {}, state: "waiting", card: null };

function boxOf(t: Target, vp: { width: number; height: number }): Box | null {
  const found = typeof t === "string" ? document.querySelector(t) : t();
  const els = (Array.isArray(found) ? found : found ? [found] : []);
  const rects = els.map((e) => e.getBoundingClientRect()).filter((r) => r.width > 0 && r.height > 0)
    .map((r) => ({ left: r.left, top: r.top, width: r.width, height: r.height }));
  const u = union(rects);
  return u ? clip(u, vp, 3) : null;
}

function TourRun({ catalog, close, steps }: { catalog: CatalogDetail; close: () => void; steps: Step[] }) {
  const [at, setAt] = useState(0);
  const [ctx, setCtx] = useState<TourCtx | null>(null);
  const [view, setView] = useState<View>(EMPTY);
  const session = useRef<TourSession | null>(null);
  const card = useRef<HTMLDivElement>(null);
  const next = useRef<HTMLButtonElement>(null);
  const step = steps[at];
  const last = at === steps.length - 1;

  // One session per opening: it remembers where the reader was, and closing it undoes the step and goes back there.
  useEffect(() => {
    const s = new TourSession(hashNav);
    session.current = s;
    let live = true;
    const start = (r: Parameters<typeof makeCtx>[2]) => { if (live) setCtx(makeCtx(catalog, s.origin, r)); };
    api.rules(catalog.short).then(start, () => start(null));
    return () => { live = false; s.close(); session.current = null; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [catalog.short]);

  // Arriving at a step: leave the last one (undoing it), go where this one needs, do what it does.
  useEffect(() => {
    if (ctx) session.current?.enter(step, ctx);
  }, [step, ctx]);

  // Light the step's areas and keep the card beside them while the screen settles, scrolls or is resized.
  useEffect(() => {
    if (!ctx) return;
    const t0 = Date.now();
    const routed = !!step.route(ctx);
    let prev = "";
    const measure = () => {
      const vp = { width: window.innerWidth, height: window.innerHeight };
      const ready = routed && (!step.ready || step.ready(ctx));
      const late = !routed || Date.now() - t0 > ABSENT_MS;
      const boxes = ready || late ? step.targets.map((t) => boxOf(t, vp)).filter((b): b is Box => !!b) : [];
      const accents = boxes.length ? (step.accents ?? []).map((t) => boxOf(t, vp)).filter((b): b is Box => !!b) : [];
      const state: View["state"] = boxes.length ? "found" : late ? "absent" : "waiting";
      const size = { width: CARD_W, height: card.current?.offsetHeight || 320 };
      const spot = boxes[0];
      const pos = spot ? placeCard(spot, size, vp, step.sides)
        : { left: (vp.width - size.width) / 2, top: Math.max(70, (vp.height - size.height) / 2) };
      const v: View = { boxes, accents, facts: state === "found" && step.read ? step.read(ctx) : {}, state,
                        card: { left: Math.round(pos.left), top: Math.round(pos.top) } };
      const key = JSON.stringify(v);
      if (key !== prev) { prev = key; setView(v); }
      // A step's action may move focus into the page (the comment box focuses itself): keep it on the card.
      const a = document.activeElement;
      if (card.current && !(a && card.current.contains(a))) next.current?.focus({ preventScroll: true });
    };
    setView(EMPTY);
    measure();
    const id = setInterval(measure, 120);
    window.addEventListener("resize", measure);
    window.addEventListener("scroll", measure, true);
    return () => {
      clearInterval(id);
      window.removeEventListener("resize", measure);
      window.removeEventListener("scroll", measure, true);
    };
  }, [step, ctx]);

  const move = useCallback((to: number) => {
    if (to >= steps.length) close();
    else if (to >= 0) setAt(to);
  }, [steps.length, close]);

  // Keys: Esc closes, ← → move, Enter goes on. Nothing reaches the screen underneath (no A / W / C there).
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const inCard = !!card.current && e.target instanceof Node && card.current.contains(e.target);
      if (e.key === "Escape") close();
      else if (e.key === "ArrowRight" || (e.key === "Enter" && !inCard)) move(at + 1);
      else if (e.key === "ArrowLeft") move(at - 1);
      else if (inCard) { e.stopPropagation(); return; }
      else if (e.key === "Tab") next.current?.focus();
      e.preventDefault();
      e.stopPropagation();
    };
    window.addEventListener("keydown", onKey, true);
    return () => window.removeEventListener("keydown", onKey, true);
  }, [at, move, close]);

  const { boxes, accents, state } = view;
  const showBody = state === "found" || (state === "absent" && boxes.length > 0);
  return (
    <div className="tour" role="dialog" aria-modal="true" aria-label="A tour of the Studio" data-step={step.id} data-state={state}>
      <svg className="tour-dim" width="100%" height="100%" aria-hidden="true">
        <defs>
          <mask id="tour-holes">
            <rect width="100%" height="100%" fill="#fff" />
            {boxes.map((b, i) => <rect key={i} x={b.left + 2} y={b.top + 2} width={b.width - 4} height={b.height - 4} rx="8" fill="#000" />)}
          </mask>
        </defs>
        <rect width="100%" height="100%" fill="rgba(16, 24, 40, .52)" mask="url(#tour-holes)" />
      </svg>
      {boxes.map((b, i) => <div key={i} className="tour-ring" style={{ left: b.left + 2, top: b.top + 2, width: b.width - 4, height: b.height - 4 }} />)}
      {accents.map((b, i) => <div key={i} className="tour-accent" style={{ left: b.left - 4, top: b.top - 4, width: b.width + 8, height: b.height + 8 }} />)}
      {ctx && (
        <div ref={card} className={`tour-card${state === "waiting" ? " waiting" : ""}`}
          style={{ left: view.card?.left ?? 0, top: view.card?.top ?? 0, width: CARD_W }}>
          <div className="tour-count">Step {at + 1} of {steps.length}</div>
          <h3>{step.title}</h3>
          <div className="tour-body">{showBody ? step.body(view.facts, ctx) : state === "absent" ? step.absent(ctx) : null}</div>
          <div className="tour-foot">
            <button className="linkish" onClick={close}>Close</button>
            <span className="tour-dots" role="tablist" aria-label="Steps">
              {steps.map((s, i) => (
                <button key={s.id} role="tab" aria-selected={i === at} aria-label={`Step ${i + 1}: ${s.title}`}
                  className={i === at ? "on" : ""} onClick={() => setAt(i)} />
              ))}
            </span>
            {at > 0 && <button className="btn" onClick={() => move(at - 1)}>Back</button>}
            <button ref={next} className="btn primary" onClick={() => move(at + 1)}>{last ? "Start reviewing" : "Next"}</button>
          </div>
          <div className="tour-hint"><kbd>←</kbd><kbd>→</kbd>move <kbd>Esc</kbd>close</div>
        </div>
      )}
    </div>
  );
}
