// Painting highlights into the page pane's iframe without changing any page element's css path:
// - text ranges use the CSS Custom Highlight API (no DOM change at all);
// - outlines and numbered badges (classes all `gds-`-prefixed: sites' CSS has `.mark`, `.focus`, …)
//   are absolutely positioned boxes in one overlay <div id="gds-overlay">, appended as
//   the last child of <html> (never inside <body>). Badges draw their number with CSS (`content: attr(data-n)`), so
//   the overlay adds no text to any element's textContent.
// Every highlight is resolved (querySelector) before anything is added.

import { rangeFromOffsets, resolveOffsets, resolvePath } from "./dom";

/** `looked`: the container a rule checked before claiming "not on the page" (sme-fixes §6), dashed purple.
 * `expected`: text in the right answer (green outline); `excluded`: text marked "not in the answer" (red dashed, light
 * red fill); `note`: a comment's numbered bubble at the text it is about (no outline). */
export type HighlightKind = "value" | "expected" | "excluded" | "block" | "mark" | "note" | "looked";

export interface Highlight {
  id: string;
  kind: HighlightKind;
  cssPath: string;
  charStart?: number | null;
  charEnd?: number | null;
  text?: string | null;
  badge?: number | string;
  /** Draw a × at its end that removes it (PagePane's `onRemove`), e.g. one piece of a reviewer's answer. */
  removable?: boolean;
  /** A course block's verdict: its border turns green (✓) or red (✗). */
  state?: "ok" | "bad" | null;
}

export interface Resolved {
  h: Highlight;
  el: Element;
  range: Range | null; // null: the whole element
}

const OVERLAY_ID = "gds-overlay";

const NAMES: Record<string, string> = { value: "gds-value", expected: "gds-expected", excluded: "gds-excluded", mark: "gds-mark" };

// Fallback styles in case the render route's head styles are missing (e.g. an older cached render).
const OVERLAY_CSS = `
#gds-overlay .gds-badge::before{content:attr(data-n)}
#gds-overlay .gds-fill{position:absolute;pointer-events:none;mix-blend-mode:multiply}
#gds-overlay .gds-fill.gds-value{background:rgba(253,224,120,.92)}
#gds-overlay .gds-fill.gds-expected{background:rgba(190,242,214,.95)}
#gds-overlay .gds-fill.gds-mark{background:#ffe4ea}
#gds-overlay .gds-fill.gds-excluded{background:rgba(254,228,226,.9)}
#gds-overlay .gds-box.gds-excluded{border:1.5px dashed #b42318}
#gds-overlay .gds-box.gds-block.gds-ok{box-shadow:0 0 0 2px #12805c}
#gds-overlay .gds-box.gds-block.gds-bad{box-shadow:0 0 0 2px #d92d20}
#gds-overlay .gds-badge.gds-note{background:#2f54eb}
#gds-overlay .gds-box.gds-hover{box-shadow:0 0 0 2px rgba(47,84,235,.8);background:rgba(47,84,235,.05)}
#gds-overlay .gds-box.gds-looked{border:2px dashed #7c3aed;box-shadow:none;background:rgba(124,58,237,.04)}
#gds-overlay .gds-badge.gds-looked{background:#7c3aed;border-radius:4px;font-weight:600}`;

export function resolveAll(doc: Document, highlights: Highlight[]): Resolved[] {
  return highlights.flatMap((h) => {
    const resolved = resolveOne(doc, h);
    return resolved ? [resolved] : [];
  });
}

function resolveOne(doc: Document, h: Highlight): Resolved | null {
  const el = resolvePath(doc, h.cssPath);
  if (!el) return null;
  if (h.kind === "block" || h.kind === "looked") return { h, el, range: null };
  const wantsRange = h.charStart != null || !!h.text;
  const range = wantsRange ? rangeOf(el, h) : null;
  if (wantsRange && !range && h.kind === "mark") return null; // never mark a guess
  return { h, el, range };
}

function rangeOf(el: Element, h: Highlight): Range | null {
  const offsets = resolveOffsets(el, h.charStart, h.charEnd, h.text);
  return offsets ? rangeFromOffsets(el, offsets[0], offsets[1]) : null;
}

/** Paint resolved highlights. Returns the element or range to scroll to for `focusId`, if any. */
export function paint(doc: Document, resolved: Resolved[], focusId?: string | null): Rect | null {
  const win = doc.defaultView as (Window & typeof globalThis) | null;
  if (!win || !doc.documentElement) return null;
  clear(doc);
  const canvas = canvasOf(doc, win);
  let focus: Rect | null = null;
  for (const item of resolved) {
    const rects = item.range ? paintRange(canvas, item) : paintElement(canvas, item, focusId);
    if (rects && item.h.id === focusId) focus = item.range ? union(rects) : rects[0];
  }
  registerHighlights(canvas);
  return focus;
}

/** Where one paint() draws: the overlay, plus the CSS Custom Highlight registry when the browser has one. */
interface Canvas {
  doc: Document;
  win: Window;
  ov: HTMLElement;
  HL?: new (...r: Range[]) => unknown;
  reg?: Map<string, unknown>;
  ranges: Record<string, Range[]>;
}

function canvasOf(doc: Document, win: Window & typeof globalThis): Canvas {
  return {
    doc,
    win,
    ov: overlay(doc),
    HL: (win as unknown as { Highlight?: new (...r: Range[]) => unknown }).Highlight,
    reg: (win.CSS as unknown as { highlights?: Map<string, unknown> } | undefined)?.highlights,
    ranges: { value: [], expected: [], excluded: [], mark: [] },
  };
}

/** Draws a text range; returns its rects, or null when it has none on screen. */
function paintRange(canvas: Canvas, { h, range }: Resolved): Rect[] | null {
  const rects = typeof range!.getClientRects === "function" ? docRects(canvas.win, range!.getClientRects()) : [];
  if (!rects.length) return null;
  if (h.kind === "note") paintRangeNote(canvas, h, rects);
  else paintRangeMarks(canvas, h, range!, rects);
  return rects;
}

/** A comment: only its numbered bubble, at the end of the text it is about. */
function paintRangeNote({ doc, ov }: Canvas, h: Highlight, rects: Rect[]): void {
  const l = rects[rects.length - 1];
  if (h.badge != null) badge(doc, ov, h.kind, h.badge, l.left + l.width + 1, l.top - 10);
}

function paintRangeMarks(canvas: Canvas, h: Highlight, range: Range, rects: Rect[]): void {
  const { doc, ov, reg, HL, ranges } = canvas;
  const kind = h.kind;
  if (reg && HL) ranges[kind]?.push(range);
  else rects.forEach((r) => box(doc, ov, `gds-fill gds-${kind}`, r));
  rects.forEach((r) => box(doc, ov, `gds-box gds-${kind}`, r, kind === "mark" ? 1 : 0));
  if (h.badge != null) {
    const f = rects[0];
    // top-left corner, so it covers as little of the surrounding text as possible
    badge(doc, ov, kind, h.badge, Math.max(0, f.left - 11), f.top - 14);
  }
  if (h.removable) {
    const l = rects[rects.length - 1];
    removeButton(doc, ov, h.id, l.left + l.width + 2, l.top - 9);
  }
}

/** Draws a whole element; returns its rect, or null when it has none on screen. */
function paintElement(canvas: Canvas, { h, el }: Resolved, focusId?: string | null): Rect[] | null {
  const rects = docRects(canvas.win, [el.getBoundingClientRect()]);
  if (!rects.length) return null;
  const r = rects[0];
  if (h.kind === "note") paintElementNote(canvas, h, r);
  else paintElementBox(canvas, h, r, h.id === focusId);
  return rects;
}

function paintElementNote({ doc, ov }: Canvas, h: Highlight, r: Rect): void {
  if (h.badge != null) badge(doc, ov, h.kind, h.badge, r.left + r.width + 1, r.top - 10);
}

function paintElementBox({ doc, ov }: Canvas, h: Highlight, r: Rect, focused: boolean): void {
  const kind = h.kind;
  const st = h.state ? ` gds-${h.state}` : "";
  box(doc, ov, `gds-box gds-${kind} gds-whole${focused ? " gds-focus" : ""}${st}`, r, kind === "block" ? 2 : 3);
  if (h.badge == null) return;
  if (kind === "block") badge(doc, ov, kind, h.badge, Math.max(0, r.left - 10), r.top - 8);
  else badge(doc, ov, kind, h.badge, Math.max(0, r.left - 26), r.top);
}

function registerHighlights({ reg, HL, ranges }: Canvas): void {
  if (!reg || !HL) return;
  for (const [kind, rs] of Object.entries(ranges)) {
    if (!rs.length) continue;
    const hl = new HL(...rs) as { priority?: number };
    if (kind === "expected" || kind === "excluded") hl.priority = 1;  // a reviewer's piece shows over the value found
    reg.set(NAMES[kind], hl);
  }
}

/** A hover outline for "pick a block" mode (one box, replaced on every call; null removes it). */
export function hoverBox(doc: Document, el: Element | null): void {
  const win = doc.defaultView;
  const ov = overlay(doc);
  ov.querySelectorAll(".gds-box.gds-hover").forEach((n) => n.remove());
  if (!el || !win) return;
  const r = docRects(win, [el.getBoundingClientRect()]);
  if (r.length) box(doc, ov, "gds-box gds-hover", r[0], 2);
}

/** Scroll the frame (only the frame, never the parent page) so `r` sits in the middle. */
export function scrollToRect(win: Window, r: Rect): void {
  const y = r.top + r.height / 2 - win.innerHeight / 2;
  win.scrollTo({ top: Math.max(0, y), left: 0, behavior: "auto" });
}

export function clear(doc: Document): void {
  const win = doc.defaultView as (Window & typeof globalThis) | null;
  const reg = (win?.CSS as unknown as { highlights?: Map<string, unknown> } | undefined)?.highlights;
  if (reg) Object.values(NAMES).forEach((n) => reg.delete(n));
  const ov = doc.getElementById(OVERLAY_ID);
  if (ov) ov.querySelectorAll(".gds-box, .gds-badge, .gds-fill, .gds-x").forEach((n) => n.remove());
}

function overlay(doc: Document): HTMLElement {
  let ov = doc.getElementById(OVERLAY_ID) as HTMLElement | null;
  if (!ov) {
    ov = doc.createElement("div");
    ov.id = OVERLAY_ID;
    ov.setAttribute("aria-hidden", "true");
    ov.style.cssText = "position:absolute;left:0;top:0;width:0;height:0;overflow:visible;z-index:2147483646;pointer-events:none";
    const st = doc.createElement("style");
    st.textContent = OVERLAY_CSS;
    ov.appendChild(st);
    doc.documentElement.appendChild(ov); // after <body>: no body element's path changes
  }
  return ov;
}

interface Rect { left: number; top: number; width: number; height: number }

function docRects(win: Window, rects: ArrayLike<DOMRect>): Rect[] {
  const out: Rect[] = [];
  for (let i = 0; i < rects.length; i++) {
    const r = rects[i];
    if (r.width < 0.5 || r.height < 0.5) continue;
    out.push({ left: r.left + win.scrollX, top: r.top + win.scrollY, width: r.width, height: r.height });
  }
  return out;
}

function box(doc: Document, parent: HTMLElement, cls: string, r: Rect, pad = 0): HTMLElement {
  const b = doc.createElement("div");
  b.className = cls;
  b.style.cssText = `position:absolute;left:${r.left - pad}px;top:${r.top - pad}px;width:${r.width + 2 * pad}px;height:${r.height + 2 * pad}px`;
  parent.appendChild(b);
  return b;
}

/** A clickable × (the overlay itself lets clicks through to the page; this one doesn't). */
function removeButton(doc: Document, parent: HTMLElement, id: string, x: number, y: number): void {
  const b = doc.createElement("div");
  b.className = "gds-x";
  b.setAttribute("data-id", id);
  b.setAttribute("title", "Remove this piece of your answer");
  b.textContent = "×";
  b.style.cssText = `position:absolute;left:${x}px;top:${y}px;width:18px;height:18px;border-radius:50%;background:#1f7a55;`
    + "color:#fff;font:700 14px/18px system-ui,sans-serif;text-align:center;cursor:pointer;pointer-events:auto;"
    + "box-shadow:0 1px 3px rgba(0,0,0,.35);user-select:none";
  parent.appendChild(b);
}

function badge(doc: Document, parent: HTMLElement, kind: string, n: number | string, x: number, y: number): void {
  const b = doc.createElement("div");
  b.className = `gds-badge gds-${kind}`;
  b.setAttribute("data-n", String(n));
  b.style.cssText = `position:absolute;left:${x}px;top:${y}px`;
  parent.appendChild(b);
}

function union(rects: Rect[]): Rect {
  const l = Math.min(...rects.map((r) => r.left));
  const t = Math.min(...rects.map((r) => r.top));
  const rr = Math.max(...rects.map((r) => r.left + r.width));
  const b = Math.max(...rects.map((r) => r.top + r.height));
  return { left: l, top: t, width: rr - l, height: b - t };
}
