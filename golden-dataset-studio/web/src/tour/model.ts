// The tour's logic without React (spec §7.8): when it opens by itself, where it starts, where its card goes,
// and the bookkeeping that undoes each step when the reader leaves it.
import type { RulesResponse, RuleSummary } from "../api/types";
import { defaultRule } from "../rules/RulesTab";
import { href, parseRoute } from "../shell/router";

// --- opens once per browser ---------------------------------------------------------------------------------
export const SEEN_KEY = "studio.tour.seen";

export interface KeyStore { getItem(k: string): string | null; setItem(k: string, v: string): void }

export function browserStore(): KeyStore | null {
  try { return window.localStorage; } catch { return null; }
}

/** True the first time a catalog is opened in this browser. Without working storage the tour never opens by itself
 *  (it would otherwise open on every load); the button still works. */
export function shouldAutoOpen(store: KeyStore | null): boolean {
  if (!store) return false;
  try { return store.getItem(SEEN_KEY) === null; } catch { return false; }
}

export function markSeen(store: KeyStore | null): void {
  try { store?.setItem(SEEN_KEY, "1"); } catch { /* private mode: nothing to remember with */ }
}

// --- what the steps need to know about this catalog ----------------------------------------------------------
export interface TourCtx {
  catalog: string;
  /** The Rules tab route the tour works on (a field rule). */
  base: string;
  ruleId: string | null;
  /** A record locator's view, or null when the catalog has none. */
  locator: string | null;
  locatorId: string | null;
  /** A rule Approve is greyed out on (a course marked wrong or missing): the reader's own if so, else the first. */
  blocked: string;
  blockedId: string | null;
  /** Compare needs two ruleset versions. */
  compare: string | null;
  /** The Evals tab. */
  evals: string;
  crawl: string;
  /** Text the rule head shows for a rule, to tell when the Rules tab has caught up with a route. */
  headText: Record<string, string>;
}

const allRules = (rules: RulesResponse | null): RuleSummary[] => rules?.groups.flatMap((g) => g.rules) ?? [];

export function headText(r: RuleSummary): string {
  return r.kind === "field" ? r.ctdl_property ?? r.property_label ?? r.title : r.title;
}

/** Where the tour works: the reader's own field rule when they are on one, else the Rules tab's default rule. */
export function makeCtx(catalog: { short: string; crawl: string; ruleset_version: number; rulesets: unknown[] },
                        origin: string, rules: RulesResponse | null): TourCtx {
  const cat = catalog.short;
  const list = allRules(rules);
  const o = parseRoute(origin);
  const mine = o.catalog === cat && o.tab === "rules" && o.id ? list.find((r) => r.rule_id === o.id) : undefined;
  let base: string, ruleId: string | null;
  if (mine && mine.kind === "field") { base = origin.startsWith("#") ? origin : `#${origin}`; ruleId = mine.rule_id; }
  else { ruleId = defaultRule(rules); base = href(cat, "rules", ruleId); }
  const loc = list.find((r) => r.rule_id === "locator-program-requirement") ?? list.find((r) => r.kind === "locator");
  const isBlocked = (r: RuleSummary) => r.open_wrong + r.open_missing > 0 && r.status !== "approved";
  const mineNow = list.find((r) => r.rule_id === ruleId);
  const blk = mineNow && isBlocked(mineNow) ? mineNow
    : list.find((r) => isBlocked(r) && r.kind === "field") ?? list.find(isBlocked) ?? null;
  const twoVersions = catalog.ruleset_version > 1 || catalog.rulesets.length > 1;
  return {
    catalog: cat, base, ruleId, crawl: catalog.crawl,
    locator: loc ? href(cat, "rules", loc.rule_id) : null, locatorId: loc?.rule_id ?? null,
    blocked: blk && blk.rule_id !== ruleId ? href(cat, "rules", blk.rule_id) : base, blockedId: blk?.rule_id ?? ruleId,
    compare: twoVersions ? href(cat, "compare") : null,
    evals: href(cat, "evals"),
    headText: Object.fromEntries(list.map((r) => [r.rule_id, headText(r)])),
  };
}

// --- undo bookkeeping -----------------------------------------------------------------------------------------
export type Undo = () => void;

export interface Nav { get(): string; set(hash: string): void }

/** Calls `then` once `ready()` holds (checked every `every` ms), or never if it doesn't within `timeout`.
 *  Returns a cancel function. */
export type Waiter = (ready: () => boolean, then: () => void) => () => void;

export function poll(every = 80, timeout = 8000): Waiter {
  return (ready, then) => {
    const t0 = Date.now();
    let id: ReturnType<typeof setInterval> | null = null;
    const stop = () => { if (id !== null) clearInterval(id); id = null; };
    const check = () => {
      if (ready()) { stop(); then(); return true; }
      if (Date.now() - t0 > timeout) stop();
      return false;
    };
    if (!check()) id = setInterval(check, every);
    return stop;
  };
}

export interface SessionStep {
  route(ctx: TourCtx): string | null;
  ready?(ctx: TourCtx): boolean;
  arrive?(ctx: TourCtx): Undo | void;
}

/**
 * One run of the tour. Each step says which route it needs and what it does once the screen is there; `enter`
 * first undoes the step being left, then goes there and does it. `close` undoes the last step and goes back to
 * where the reader was. Routes change with `replace`, so the tour leaves nothing in the browser's history.
 */
export class TourSession {
  readonly origin: string;
  private undo: Undo | null = null;
  private cancel: (() => void) | null = null;
  constructor(private nav: Nav, private wait: Waiter = poll()) { this.origin = nav.get(); }

  enter(step: SessionStep, ctx: TourCtx): void {
    this.leave();
    const want = step.route(ctx);
    if (!want) return;
    if (this.nav.get() !== want) this.nav.set(want);
    if (!step.arrive) return;
    const ready = step.ready ? () => step.ready!(ctx) : () => true;
    this.cancel = this.wait(ready, () => {
      this.cancel = null;
      const u = step.arrive!(ctx);
      this.undo = typeof u === "function" ? u : null;
    });
  }

  leave(): void {
    this.cancel?.();
    this.cancel = null;
    const u = this.undo;
    this.undo = null;
    try { u?.(); } catch { /* the screen moved on by itself */ }
  }

  close(): void {
    this.leave();
    if (this.nav.get() !== this.origin) this.nav.set(this.origin);
  }
}

// --- where the card goes ---------------------------------------------------------------------------------------
export interface Box { left: number; top: number; width: number; height: number }
export type Side = "right" | "left" | "below" | "above";
const GAP = 14, EDGE = 12, TOP = 56;

const clamp = (n: number, lo: number, hi: number) => Math.max(lo, Math.min(n, Math.max(lo, hi)));

/** The card beside the anchor on the first side it fits, else over the anchor's top-right corner. */
export function placeCard(a: Box, card: { width: number; height: number }, vp: { width: number; height: number },
                          sides: Side[] = ["right", "left", "below", "above"]): { left: number; top: number; side: Side | "inside" } {
  const { width: w, height: h } = card;
  const vTop = clamp(a.top, TOP, vp.height - h - EDGE);
  const hLeft = clamp(a.left, EDGE, vp.width - w - EDGE);
  for (const s of sides) {
    if (s === "right" && a.left + a.width + GAP + w <= vp.width - EDGE) return { left: a.left + a.width + GAP, top: vTop, side: s };
    if (s === "left" && a.left - GAP - w >= EDGE) return { left: a.left - GAP - w, top: vTop, side: s };
    if (s === "below" && a.top + a.height + GAP + h <= vp.height - EDGE) return { left: hLeft, top: a.top + a.height + GAP, side: s };
    if (s === "above" && a.top - GAP - h >= TOP) return { left: hLeft, top: a.top - GAP - h, side: s };
  }
  return { left: clamp(a.left + a.width - w - GAP, EDGE, vp.width - w - EDGE), top: clamp(a.top + GAP, TOP, vp.height - h - EDGE), side: "inside" };
}

/** A box cut to the viewport (a long list is lit only where it shows); null when nothing of it shows. */
export function clip(b: Box, vp: { width: number; height: number }, m = 0): Box | null {
  const left = Math.max(b.left, m), top = Math.max(b.top, m);
  const right = Math.min(b.left + b.width, vp.width - m), bottom = Math.min(b.top + b.height, vp.height - m);
  if (right - left < 2 || bottom - top < 2) return null;
  return { left, top, width: right - left, height: bottom - top };
}

export function union(bs: Box[]): Box | null {
  if (!bs.length) return null;
  const l = Math.min(...bs.map((b) => b.left)), t = Math.min(...bs.map((b) => b.top));
  const r = Math.max(...bs.map((b) => b.left + b.width)), btm = Math.max(...bs.map((b) => b.top + b.height));
  return { left: l, top: t, width: r - l, height: btm - t };
}
