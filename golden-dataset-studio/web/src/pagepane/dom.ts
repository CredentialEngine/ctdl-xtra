// Pure DOM helpers for the page pane: css paths in the engine's format, textContent offsets, the text-search
// fallback, and selection capture. Nothing here mutates the page.

export interface CapturedSelection {
  text: string;
  css_path: string;
  char_start: number;
  char_end: number;
  prefix: string;
  suffix: string;
}

const CONTEXT = 30;

/** The engine's document-root css path: `html > body:nth-of-type(1) > div:nth-of-type(2) > …`. */
export function cssPathOf(el: Element): string {
  const parts: string[] = [];
  let cur: Element | null = el;
  while (cur) {
    const tag = cur.localName.toLowerCase();
    const parent: Element | null = cur.parentElement;
    if (!parent) {
      parts.push(tag);
      break;
    }
    let n = 1;
    for (let sib = cur.previousElementSibling; sib; sib = sib.previousElementSibling) {
      if (sib.localName.toLowerCase() === tag) n++;
    }
    parts.push(`${tag}:nth-of-type(${n})`);
    cur = parent;
  }
  return parts.reverse().join(" > ");
}

/** The element a css path names (null when it doesn't resolve or isn't valid CSS). */
export function resolvePath(doc: Document, cssPath: string): Element | null {
  try {
    return doc.querySelector(cssPath);
  } catch {
    return null;
  }
}

function textNodes(el: Node): Text[] {
  const doc = el.ownerDocument ?? (el as Document);
  const out: Text[] = [];
  const walker = doc.createTreeWalker(el, 4 /* NodeFilter.SHOW_TEXT */);
  for (let n = walker.nextNode(); n; n = walker.nextNode()) out.push(n as Text);
  return out;
}

/** Offset of (node, offset) within `el.textContent`. */
export function textOffset(el: Element, node: Node, offset: number): number {
  const doc = el.ownerDocument;
  const r = doc.createRange();
  r.selectNodeContents(el);
  r.setEnd(node, offset);
  return r.toString().length;
}

/** A DOM Range covering `[start, end)` of `el.textContent`, or null when the offsets don't fit. */
export function rangeFromOffsets(el: Element, start: number, end: number): Range | null {
  if (start < 0 || end < start) return null;
  const nodes = textNodes(el);
  let pos = 0;
  let startNode: Text | null = null;
  let startOff = 0;
  for (const n of nodes) {
    const len = n.data.length;
    if (!startNode && start < pos + len) {
      startNode = n;
      startOff = start - pos;
    }
    if (startNode && end <= pos + len) {
      const r = el.ownerDocument.createRange();
      r.setStart(startNode, startOff);
      r.setEnd(n, end - pos);
      return r;
    }
    pos += len;
  }
  if (start === end && start === pos && nodes.length) {
    const last = nodes[nodes.length - 1];
    const r = el.ownerDocument.createRange();
    r.setStart(last, last.data.length);
    r.setEnd(last, last.data.length);
    return r;
  }
  return null;
}

/** Where `needle` occurs in `hay`: exactly, else ignoring differences in whitespace. Positions are in `hay`. */
export function findText(hay: string, needle: string): [number, number] | null {
  const want = needle.trim();
  if (!want) return null;
  const i = hay.indexOf(want);
  if (i >= 0) return [i, i + want.length];
  // whitespace-insensitive: collapse runs of whitespace in both, keeping a map back to `hay`
  const map: number[] = [];
  let norm = "";
  let prevSpace = false;
  for (let k = 0; k < hay.length; k++) {
    const space = /\s/.test(hay[k]);
    if (space && prevSpace) continue;
    norm += space ? " " : hay[k];
    map.push(k);
    prevSpace = space;
  }
  const w = want.replace(/\s+/g, " ");
  const j = norm.indexOf(w);
  if (j < 0) return null;
  const endIdx = j + w.length - 1;
  return [map[j], map[endIdx] + 1];
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

/** The nearest element containing the whole range. */
export function containerOf(range: Range): Element | null {
  let n: Node | null = range.commonAncestorContainer;
  while (n && n.nodeType !== 1) n = n.parentNode;
  return n as Element | null;
}

/** What the reviewer selected, as the annotation's `expected` (spec §9), or null for an empty selection. */
export function captureRange(range: Range): CapturedSelection | null {
  if (range.collapsed) return null;
  const el = containerOf(range);
  if (!el) return null;
  const start = textOffset(el, range.startContainer, range.startOffset);
  const end = textOffset(el, range.endContainer, range.endOffset);
  const tc = el.textContent ?? "";
  const text = tc.slice(start, end);
  if (!text.trim()) return null;
  return {
    text,
    css_path: cssPathOf(el),
    char_start: start,
    char_end: end,
    prefix: tc.slice(Math.max(0, start - CONTEXT), start),
    suffix: tc.slice(end, end + CONTEXT),
  };
}

export function captureSelection(sel: Selection | null): CapturedSelection | null {
  if (!sel || sel.rangeCount === 0 || sel.isCollapsed) return null;
  return captureRange(sel.getRangeAt(0));
}

/** A whole element as a capture (for "Add a course this rule missed": the block that was clicked). */
export function captureElement(el: Element): CapturedSelection {
  const tc = el.textContent ?? "";
  return { text: tc.trim(), css_path: cssPathOf(el), char_start: 0, char_end: tc.length, prefix: "", suffix: "" };
}

const INLINE = /^(inline|contents)/;

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
