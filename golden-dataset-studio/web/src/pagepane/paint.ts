// Painting highlights into the page pane's iframe without changing any page element's css path:
// - text ranges use the CSS Custom Highlight API (no DOM change at all);
// - outlines and numbered badges (classes all `gds-`-prefixed: sites' CSS has `.mark`, `.focus`, …)
//   are absolutely positioned boxes in one overlay <div id="gds-overlay">, appended as
//   the last child of <html> (never inside <body>). Badges draw their number with CSS (`content: attr(data-n)`), so
//   the overlay adds no text to any element's textContent.
// Every highlight is resolved (querySelector) before anything is added.

import { rangeFromOffsets, resolveOffsets, resolvePath } from "./dom";

export type HighlightKind = "value" | "expected" | "block" | "mark";

export interface Highlight {
  id: string;
  kind: HighlightKind;
  cssPath: string;
  charStart?: number | null;
  charEnd?: number | null;
  text?: string | null;
  badge?: number | string;
}

export interface Resolved {
  h: Highlight;
  el: Element;
  range: Range | null; // null: the whole element
}

const OVERLAY_ID = "gds-overlay";
const NAMES: Record<string, string> = { value: "gds-value", expected: "gds-expected", mark: "gds-mark" };

// Fallback styles in case the render route's head styles are missing (e.g. an older cached render).
const OVERLAY_CSS = `
#gds-overlay .gds-badge::before{content:attr(data-n)}
#gds-overlay .gds-fill{position:absolute;pointer-events:none;mix-blend-mode:multiply}
#gds-overlay .gds-fill.gds-value{background:rgba(253,224,120,.92)}
#gds-overlay .gds-fill.gds-expected{background:rgba(190,242,214,.95)}
#gds-overlay .gds-fill.gds-mark{background:#ffe4ea}
#gds-overlay .gds-box.gds-hover{box-shadow:0 0 0 2px rgba(47,84,235,.8);background:rgba(47,84,235,.05)}`;

export function resolveAll(doc: Document, highlights: Highlight[]): Resolved[] {
  const out: Resolved[] = [];
  for (const h of highlights) {
    const el = resolvePath(doc, h.cssPath);
    if (!el) continue;
    if (h.kind === "block") {
      out.push({ h, el, range: null });
      continue;
    }
    const wantsRange = h.charStart != null || !!h.text;
    const offs = wantsRange ? resolveOffsets(el, h.charStart, h.charEnd, h.text) : null;
    const range = offs ? rangeFromOffsets(el, offs[0], offs[1]) : null;
    if (wantsRange && !range && h.kind === "mark") continue; // never mark a guess
    out.push({ h, el, range });
  }
  return out;
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

export function clear(doc: Document): void {
  const win = doc.defaultView as (Window & typeof globalThis) | null;
  const reg = (win?.CSS as unknown as { highlights?: Map<string, unknown> } | undefined)?.highlights;
  if (reg) Object.values(NAMES).forEach((n) => reg.delete(n));
  const ov = doc.getElementById(OVERLAY_ID);
  if (ov) ov.querySelectorAll(".gds-box, .gds-badge, .gds-fill").forEach((n) => n.remove());
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

function badge(doc: Document, parent: HTMLElement, kind: string, n: number | string, x: number, y: number): void {
  const b = doc.createElement("div");
  b.className = `gds-badge gds-${kind}`;
  b.setAttribute("data-n", String(n));
  b.style.cssText = `position:absolute;left:${x}px;top:${y}px`;
  parent.appendChild(b);
}

/** Paint resolved highlights. Returns the element or range to scroll to for `focusId`, if any. */
export function paint(doc: Document, resolved: Resolved[], focusId?: string | null): Rect | null {
  const win = doc.defaultView as (Window & typeof globalThis) | null;
  if (!win || !doc.documentElement) return null;
  clear(doc);
  const ov = overlay(doc);
  const HL = (win as unknown as { Highlight?: new (...r: Range[]) => unknown }).Highlight;
  const reg = (win.CSS as unknown as { highlights?: Map<string, unknown> } | undefined)?.highlights;
  const ranges: Record<string, Range[]> = { value: [], expected: [], mark: [] };
  let focus: Rect | null = null;

  for (const { h, el, range } of resolved) {
    const kind = h.kind;
    if (range) {
      const rects = typeof range.getClientRects === "function" ? docRects(win, range.getClientRects()) : [];
      if (!rects.length) continue;
      if (reg && HL) ranges[kind]?.push(range);
      else rects.forEach((r) => box(doc, ov, `gds-fill gds-${kind}`, r));
      rects.forEach((r) => box(doc, ov, `gds-box gds-${kind}`, r, kind === "mark" ? 1 : 0));
      if (h.badge != null) {
        const f = rects[0];
        // top-left corner, so it covers as little of the surrounding text as possible
        badge(doc, ov, kind, h.badge, Math.max(0, f.left - 11), f.top - 14);
      }
      if (h.id === focusId) focus = union(rects);
    } else {
      const rects = docRects(win, [el.getBoundingClientRect()]);
      if (!rects.length) continue;
      const r = rects[0];
      const focused = h.id === focusId;
      box(doc, ov, `gds-box gds-${kind} gds-whole${focused ? " gds-focus" : ""}`, r, kind === "block" ? 2 : 3);
      if (h.badge != null) {
        if (kind === "block") badge(doc, ov, kind, h.badge, Math.max(0, r.left - 10), r.top - 8);
        else badge(doc, ov, kind, h.badge, Math.max(0, r.left - 26), r.top);
      }
      if (focused) focus = r;
    }
  }
  if (reg && HL) {
    for (const [kind, rs] of Object.entries(ranges)) if (rs.length) reg.set(NAMES[kind], new HL(...rs));
  }
  return focus;
}

function union(rects: Rect[]): Rect {
  const l = Math.min(...rects.map((r) => r.left));
  const t = Math.min(...rects.map((r) => r.top));
  const rr = Math.max(...rects.map((r) => r.left + r.width));
  const b = Math.max(...rects.map((r) => r.top + r.height));
  return { left: l, top: t, width: rr - l, height: b - t };
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
