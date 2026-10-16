// Positions are counted against one fixed text per document: every text node under <body>, in
// reading order (specification section 8.3). The extract step counts the same way, so a position
// written there lands on the same characters here.

import type { Segment } from './types'

export type TextIndex = { nodes: Text[]; starts: number[]; text: string }

export function buildIndex(doc: Document): TextIndex {
  const nodes: Text[] = []
  const starts: number[] = []
  const parts: string[] = []
  let at = 0
  if (doc.body) {
    const walker = doc.createTreeWalker(doc.body, NodeFilter.SHOW_TEXT)
    for (let n = walker.nextNode(); n; n = walker.nextNode()) {
      nodes.push(n as Text)
      starts.push(at)
      parts.push((n as Text).data)
      at += (n as Text).data.length
    }
  }
  return { nodes, starts, text: parts.join('') }
}

function nodeAt(index: TextIndex, position: number): number {
  let lo = 0
  let hi = index.starts.length - 1
  while (lo < hi) {
    const mid = (lo + hi + 1) >> 1
    if (index.starts[mid] <= position) lo = mid
    else hi = mid - 1
  }
  return lo
}

export type Resolved = { start: number; end: number; state: 'exact' | 're-found' | 'stale' }

/** Check the stored quote against the stored position before highlighting. Never highlight a guess. */
export function resolve(text: string, s: Segment): Resolved {
  if (text.slice(s.start, s.end) === s.quote) return { start: s.start, end: s.end, state: 'exact' }
  const withContext = text.indexOf(s.before + s.quote + s.after)
  if (withContext >= 0) {
    const start = withContext + s.before.length
    return { start, end: start + s.quote.length, state: 're-found' }
  }
  const alone = text.indexOf(s.quote)
  if (alone >= 0 && text.indexOf(s.quote, alone + 1) < 0) return { start: alone, end: alone + s.quote.length, state: 're-found' }
  return { start: s.start, end: s.end, state: 'stale' }
}

const MARK = 'data-xtra'

/** Wrap [start, end) in marks. Returns the marks made, first one first. */
export function wrap(doc: Document, start: number, end: number, className: string, data: Record<string, string> = {}): HTMLElement[] {
  const index = buildIndex(doc)
  const made: HTMLElement[] = []
  if (end <= start || !index.nodes.length) return made
  const first = nodeAt(index, start)
  const targets: { node: Text; from: number; to: number }[] = []
  for (let i = first; i < index.nodes.length && index.starts[i] < end; i++) {
    const node = index.nodes[i]
    const from = Math.max(0, start - index.starts[i])
    const to = Math.min(node.data.length, end - index.starts[i])
    if (to > from) targets.push({ node, from, to })
  }
  for (const { node, from, to } of targets) {
    let piece = node
    if (from > 0) piece = piece.splitText(from)
    if (to - from < piece.data.length) piece.splitText(to - from)
    if (!piece.data.trim() && targets.length > 1) continue // white space between blocks
    const mark = doc.createElement('span')
    mark.setAttribute(MARK, '')
    mark.className = className
    for (const [k, v] of Object.entries(data)) mark.dataset[k] = v
    piece.parentNode!.insertBefore(mark, piece)
    mark.appendChild(piece)
    made.push(mark)
  }
  if (made.length) made[0].classList.add('xh-first')
  return made
}

export function clearMarks(doc: Document, selector = `[${MARK}]`): void {
  const parents = new Set<Node>()
  doc.querySelectorAll(selector).forEach((mark) => {
    const parent = mark.parentNode!
    while (mark.firstChild) parent.insertBefore(mark.firstChild, mark)
    parent.removeChild(mark)
    parents.add(parent)
  })
  parents.forEach((p) => (p as Element).normalize?.())
}

/** The position in the document text of a point inside a text node. */
export function offsetOf(doc: Document, node: Node, offset: number): number | null {
  const index = buildIndex(doc)
  if (node.nodeType === Node.TEXT_NODE) {
    const i = index.nodes.indexOf(node as Text)
    return i < 0 ? null : index.starts[i] + offset
  }
  // An element boundary: use the first text node at or after the child at `offset`.
  const child = node.childNodes[offset] ?? null
  for (let i = 0; i < index.nodes.length; i++) {
    const n = index.nodes[i]
    if (child ? child === n || child.contains(n) || (child.compareDocumentPosition(n) & Node.DOCUMENT_POSITION_FOLLOWING) : node.compareDocumentPosition(n) & Node.DOCUMENT_POSITION_FOLLOWING && !node.contains(n)) {
      return index.starts[i]
    }
  }
  return index.text.length
}

export function elementAt(doc: Document, position: number): Element | null {
  const index = buildIndex(doc)
  if (!index.nodes.length) return null
  return index.nodes[nodeAt(index, position)].parentElement
}

/** A sentence-sized excerpt around a segment, for evidence that sits on another page. */
export function excerpt(text: string, start: number, end: number, reach = 170): { before: string; quote: string; after: string } {
  let from = Math.max(0, start - reach)
  let to = Math.min(text.length, end + reach)
  const lead = text.slice(from, start)
  const stop = Math.max(lead.lastIndexOf('. '), lead.lastIndexOf('\n'))
  if (stop >= 0) from += stop + 1
  const tail = text.slice(end, to)
  const close = tail.search(/\.\s|\n/)
  if (close >= 0) to = end + close + 1
  const tidy = (s: string) => s.replace(/\s+/g, ' ')
  return { before: tidy(text.slice(from, start)).trimStart(), quote: tidy(text.slice(start, end)), after: tidy(text.slice(end, to)).trimEnd() }
}

/** A link that makes a browser scroll to and highlight the phrase on the live page (section 8.4). */
export function textFragment(address: string, quote: string): string {
  const words = quote.replace(/\s+/g, ' ').trim().split(' ')
  const enc = (s: string) => encodeURIComponent(s).replace(/-/g, '%2D')
  const fragment = words.length > 12 ? `${enc(words.slice(0, 5).join(' '))},${enc(words.slice(-5).join(' '))}` : enc(words.join(' '))
  return `${address.split('#')[0]}#:~:text=${fragment}`
}
