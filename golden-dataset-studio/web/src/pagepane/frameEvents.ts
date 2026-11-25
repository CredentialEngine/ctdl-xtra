// Events inside the page frame. The page's own scripts never run; these are the parent's listeners.
import type { Dispatch, SetStateAction } from "react";
import { blockOf, captureElement, captureRange, captureSelection, type CapturedSelection } from "./dom";
import { hoverBox, type Resolved } from "./paint";
import type { BarAt } from "./HighlightBar";
import type { PagePaneProps } from "./PagePane";

/** What the frame's listeners read and change: refs hold the latest values, since the listeners outlive renders. */
export interface FrameContext {
  d: Document;
  latest: { current: PagePaneProps };
  scaleRef: { current: number };
  barRef: { current: BarAt | null };
  hoverables: { current: Resolved[] };
  setBar: Dispatch<SetStateAction<BarAt | null>>;
  setFrameY: (y: number) => void;
  keepHover: () => void;
  dropHover: () => void;
  apply: (scroll: boolean) => void;
}

export function listenToFrame(ctx: FrameContext): void {
  const { d } = ctx;
  d.addEventListener("click", (e) => onClick(ctx, e), true);
  d.addEventListener("mousedown", () => ctx.setBar(null));
  // the page scrolls (the reader, or the pane centring a new piece of the answer): the bar moves with its text
  d.addEventListener("scroll", () => { if (ctx.barRef.current) ctx.setFrameY(d.defaultView?.scrollY ?? 0); }, { passive: true });
  d.addEventListener("keydown", (e) => { if (e.key === "Escape") { ctx.setBar(null); d.getSelection()?.removeAllRanges(); } });
  d.addEventListener("mouseup", () => onMouseUp(ctx));
  d.addEventListener("mousemove", (e) => onMouseMove(ctx, e));
  d.addEventListener("mouseleave", () => { hoverBox(d, null); if (ctx.barRef.current?.hover) ctx.dropHover(); });
  d.defaultView?.addEventListener("resize", () => ctx.apply(false));
}

function onClick({ d, latest }: FrameContext, e: MouseEvent): void {
  const t = e.target as Element | null;
  const p = latest.current;
  const x = closestTo(t, ".gds-x");
  if (x) {
    e.preventDefault();
    e.stopPropagation();
    p.onRemove?.(x.getAttribute("data-id") ?? "");
    return;
  }
  if (closestTo(t, "a, area, form, button, input[type=submit]")) e.preventDefault();
  if (p.pickBlock && p.onPickBlock && t) pickClickedBlock(d, t, e, p.onPickBlock);
}

function pickClickedBlock(d: Document, t: Element, e: MouseEvent, onPickBlock: (sel: CapturedSelection) => void): void {
  const sel = d.getSelection();
  if (sel && !sel.isCollapsed) return; // a drag-selection is handled on mouseup
  const block = blockOf(t, d.defaultView);
  if (!block) return;
  e.preventDefault();
  onPickBlock(captureElement(block));
}

function onMouseUp(ctx: FrameContext): void {
  const p = ctx.latest.current;
  const sel = ctx.d.getSelection();
  const cap = captureSelection(sel);
  if (!cap) return;
  if (p.barActions?.length && sel && sel.rangeCount) showBarForSelection(ctx, cap, sel);
  else handOverSelection(p, cap, sel);
}

function showBarForSelection(ctx: FrameContext, cap: CapturedSelection, sel: Selection): void {
  const p = ctx.latest.current;
  const y0 = ctx.d.defaultView?.scrollY ?? 0;
  const at = { ...barAt(cap, sel.getRangeAt(0).getBoundingClientRect(), ctx.scaleRef.current), scrollY: y0 };
  ctx.setFrameY(y0);
  if (p.captureFirst && p.onSelection) {
    p.onSelection(cap);
    sel.removeAllRanges();  // it is outlined as a piece of the answer now
  }
  ctx.setBar(at);
}

function handOverSelection(p: PagePaneProps, cap: CapturedSelection, sel: Selection | null): void {
  if (p.captureSelection && p.onSelection) {
    p.onSelection(cap);
    sel?.removeAllRanges();
  } else if (p.pickBlock && p.onPickBlock) {
    p.onPickBlock(cap);
    sel?.removeAllRanges();
  }
}

function onMouseMove(ctx: FrameContext, e: MouseEvent): void {
  const p = ctx.latest.current;
  if (p.barActions?.length && !e.buttons) hoverAt(ctx, e.clientX, e.clientY);
  if (!p.pickBlock) return;
  const t = e.target as Element | null;
  hoverBox(ctx.d, t ? blockOf(t, ctx.d.defaultView) : null);
}

// Hovering text already highlighted shows the bar for it; a bar from a drag stays until it is used or dismissed.
function hoverAt(ctx: FrameContext, x: number, y: number): void {
  const cur = ctx.barRef.current;
  if (cur && !cur.hover) return;
  const s = ctx.d.getSelection();
  if (s && !s.isCollapsed) return;
  const hit = ctx.hoverables.current.find((r) => rangeContains(r.range!, x, y));
  if (!hit) {
    if (cur?.hover) ctx.dropHover();
    return;
  }
  ctx.keepHover();
  if (cur?.hover !== hit.h.id) showBarForHover(ctx, hit);
}

function showBarForHover(ctx: FrameContext, hit: Resolved): void {
  const cap = captureRange(hit.range!);
  if (!cap) return;
  const y0 = ctx.d.defaultView?.scrollY ?? 0;
  ctx.setFrameY(y0);
  ctx.setBar({ ...barAt(cap, hit.range!.getBoundingClientRect(), ctx.scaleRef.current), scrollY: y0, hover: hit.h.id });
}

const BAR_H = 30;  // the highlight bar's height in the pane (pagepane.css .gpp-hbar)

/** Where the highlight bar goes, in the pane's pixels: centred just above the selection (its rect is in the frame's
 * unscaled pixels), or just below it when there's no room above. HighlightBar keeps it inside the pane's sides. */
export function barAt(sel: CapturedSelection, r: { left: number; right: number; top: number; bottom: number }, scale: number): BarAt {
  const above = r.top * scale - BAR_H - 6;
  return { sel, x: ((r.left + r.right) / 2) * scale, y: above >= 0 ? above : r.bottom * scale + 6 };
}

function rangeContains(range: Range, x: number, y: number): boolean {
  return [...range.getClientRects()].some((q) => x >= q.left && x <= q.right && y >= q.top && y <= q.bottom);
}

function closestTo(t: Element | null, selector: string): Element | null {
  return t && typeof t.closest === "function" ? t.closest(selector) : null;
}
