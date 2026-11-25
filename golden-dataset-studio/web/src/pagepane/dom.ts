// Pure DOM helpers for the page pane: css paths in the engine's format, textContent offsets, the text-search
// fallback, and selection capture. Nothing here mutates the page.

export interface CapturedSelection {
  text: string;
  css_path: string;
  char_start: number;
  char_end: number;
  prefix: string;
  suffix: string;
  /** Where it starts and ends in the whole page's text: puts several selections in page order, finds overlaps. */
  doc_start?: number;
  doc_end?: number;
}

const CONTEXT = 30;

const INLINE = /^(inline|contents)/;

export function captureSelection(sel: Selection | null): CapturedSelection | null {
  if (!sel || sel.rangeCount === 0 || sel.isCollapsed) return null;
  return captureRange(sel.getRangeAt(0));
}

/** What the reviewer selected, as the annotation's `expected` (spec §9), or null for an empty selection. */
export function captureRange(range: Range): CapturedSelection | null {
  if (range.collapsed) return null;
  const el = containerOf(range);
  if (!el) return null;
  const span = trimmedSpan(el, range);
  return span ? selectionOf(el, range, span) : null;
}

interface Span { rawStart: number; start: number; end: number }

// Whitespace a drag picks up at either end (the line break after a paragraph, an empty element under it) isn't
// part of the selection: left in, it would be outlined (and get its own ×) on the page.
function trimmedSpan(el: Element, range: Range): Span | null {
  const rawStart = textOffset(el, range.startContainer, range.startOffset);
  const rawEnd = textOffset(el, range.endContainer, range.endOffset);
  const raw = (el.textContent ?? "").slice(rawStart, rawEnd);
  if (!raw.trim()) return null;
  return { rawStart, start: rawStart + (raw.length - raw.trimStart().length), end: rawEnd - (raw.length - raw.trimEnd().length) };
}

function selectionOf(el: Element, range: Range, { rawStart, start, end }: Span): CapturedSelection {
  const tc = el.textContent ?? "";
  const text = tc.slice(start, end);
  const docStart = textOffset(el.ownerDocument.documentElement, range.startContainer, range.startOffset) + (start - rawStart);
  return {
    text,
    css_path: cssPathOf(el),
    char_start: start,
    char_end: end,
    prefix: tc.slice(Math.max(0, start - CONTEXT), start),
    suffix: tc.slice(end, end + CONTEXT),
    doc_start: docStart,
    doc_end: docStart + text.length,
  };
}

/** A whole element as a capture (for "Add a course this rule missed": the block that was clicked). */
export function captureElement(el: Element): CapturedSelection {
  const tc = el.textContent ?? "";
  return { text: tc.trim(), css_path: cssPathOf(el), char_start: 0, char_end: tc.length, prefix: "", suffix: "" };
}

/** The nearest block-level ancestor-or-self of a clicked node (skips inline wrappers like <span>, <a>, <b>). */
export function blockOf(node: Node, win: Window | null): Element | null {
  let el: Element | null = node.nodeType === 1 ? (node as Element) : node.parentElement;
  while (el && el.parentElement && el.localName !== "body") {
    const display = win ? win.getComputedStyle(el).display : "";
    if (display && !INLINE.test(display)) return el;
    if (!display && !["span", "a", "b", "i", "em", "strong", "small", "u", "sup", "sub"].includes(el.localName)) return el;
    el = el.parentElement;
  }
  return el;
}

/** The `[start, end)` to highlight inside `el`: the stored offsets when they hold `text` (or no text is given),
 * otherwise the first place `text` occurs; null when neither works. */
export function resolveOffsets(
  el: Element,
  charStart: number | null | undefined,
  charEnd: number | null | undefined,
  text: string | null | undefined,
): [number, number] | null {
  const tc = el.textContent ?? "";
  const fits = charStart != null && charEnd != null && charStart >= 0 && charStart <= charEnd && charEnd <= tc.length;
  if (fits && (!text || tc.slice(charStart!, charEnd!).trim() === text.trim())) return [charStart!, charEnd!];
  if (text) {
    const found = findText(tc, text);
    if (found) return found;
  }
  return null;
}

/** Where `needle` occurs in `hay`: exactly, else ignoring differences in whitespace. Positions are in `hay`. */
export function findText(hay: string, needle: string): [number, number] | null {
  const want = needle.trim();
  if (!want) return null;
  const i = hay.indexOf(want);
  if (i >= 0) return [i, i + want.length];
  return findIgnoringWhitespace(hay, want);
}

function findIgnoringWhitespace(hay: string, want: string): [number, number] | null {
  const { text, origins } = collapseWhitespace(hay);
  const collapsed = want.replace(/\s+/g, " ");
  const j = text.indexOf(collapsed);
  if (j < 0) return null;
  return [origins[j], origins[j + collapsed.length - 1] + 1];
}

/** `hay` with each run of whitespace as one space, and where each of its characters came from in `hay`. */
function collapseWhitespace(hay: string): { text: string; origins: number[] } {
  const origins: number[] = [];
  let text = "";
  let prevSpace = false;
  for (let k = 0; k < hay.length; k++) {
    const space = /\s/.test(hay[k]);
    if (space && prevSpace) continue;
    text += space ? " " : hay[k];
    origins.push(k);
    prevSpace = space;
  }
  return { text, origins };
}

/** A DOM Range covering `[start, end)` of `el.textContent`, or null when the offsets don't fit. */
export function rangeFromOffsets(el: Element, start: number, end: number): Range | null {
  if (start < 0 || end < start) return null;
  const nodes = textNodes(el);
  return rangeAcross(el.ownerDocument, nodes, start, end) ?? caretAtEnd(el.ownerDocument, nodes, start, end);
}

type TextPoint = [Text, number];

function rangeAcross(doc: Document, nodes: Text[], start: number, end: number): Range | null {
  let pos = 0;
  let startPoint: TextPoint | null = null;
  for (const node of nodes) {
    const len = node.data.length;
    if (!startPoint && start < pos + len) startPoint = [node, start - pos];
    if (startPoint && end <= pos + len) return rangeBetween(doc, startPoint, [node, end - pos]);
    pos += len;
  }
  return null;
}

function caretAtEnd(doc: Document, nodes: Text[], start: number, end: number): Range | null {
  const total = nodes.reduce((sum, node) => sum + node.data.length, 0);
  if (start !== end || start !== total || !nodes.length) return null;
  const last = nodes[nodes.length - 1];
  return rangeBetween(doc, [last, last.data.length], [last, last.data.length]);
}

function rangeBetween(doc: Document, [startNode, startOffset]: TextPoint, [endNode, endOffset]: TextPoint): Range {
  const range = doc.createRange();
  range.setStart(startNode, startOffset);
  range.setEnd(endNode, endOffset);
  return range;
}

/** The engine's document-root css path: `html > body:nth-of-type(1) > div:nth-of-type(2) > …`. */
export function cssPathOf(el: Element): string {
  const steps: string[] = [];
  for (let cur: Element | null = el; cur; cur = cur.parentElement) steps.push(pathStepOf(cur));
  return steps.reverse().join(" > ");
}

function pathStepOf(el: Element): string {
  const tag = el.localName.toLowerCase();
  if (!el.parentElement) return tag;
  return `${tag}:nth-of-type(${sameTagPosition(el, tag)})`;
}

function sameTagPosition(el: Element, tag: string): number {
  let position = 1;
  for (let sib = el.previousElementSibling; sib; sib = sib.previousElementSibling) {
    if (sib.localName.toLowerCase() === tag) position++;
  }
  return position;
}

/** The element a css path names (null when it doesn't resolve or isn't valid CSS). */
export function resolvePath(doc: Document, cssPath: string): Element | null {
  try {
    return doc.querySelector(cssPath);
  } catch {
    return null;
  }
}

/** The nearest element containing the whole range. */
export function containerOf(range: Range): Element | null {
  let n: Node | null = range.commonAncestorContainer;
  while (n && n.nodeType !== 1) n = n.parentNode;
  return n as Element | null;
}

/** Offset of (node, offset) within `el.textContent`. */
export function textOffset(el: Element, node: Node, offset: number): number {
  const doc = el.ownerDocument;
  const r = doc.createRange();
  r.selectNodeContents(el);
  r.setEnd(node, offset);
  return r.toString().length;
}

function textNodes(el: Node): Text[] {
  const doc = el.ownerDocument ?? (el as Document);
  const out: Text[] = [];
  const walker = doc.createTreeWalker(el, 4 /* NodeFilter.SHOW_TEXT */);
  for (let n = walker.nextNode(); n; n = walker.nextNode()) out.push(n as Text);
  return out;
}
