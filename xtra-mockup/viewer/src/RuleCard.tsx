import type { ReactNode } from 'react'
import type { Evidence, RuleInfo, TableInfo } from './types'
import type { Hover, Jump } from './Why'

// One colour per named part of a pattern, used both in the pattern and in the text it matched.
const TINTS = ['#ffe08a', '#a8e6d9', '#d9c8ff', '#ffc9c9', '#b9dcff', '#d3f0a4']
const PLAIN_PART: Record<string, string> = { quote: 'taken' }

type Piece = string | { name: string; pieces: Piece[] }

/** Split a pattern into plain text and its named groups, nested as written. */
function groupsOf(pattern: string): Piece[] {
  const root: Piece[] = []
  const stack: { pieces: Piece[]; named: boolean }[] = [{ pieces: root, named: true }]
  const put = (s: string) => {
    const top = stack[stack.length - 1].pieces
    if (typeof top[top.length - 1] === 'string') top[top.length - 1] += s
    else top.push(s)
  }
  for (let i = 0; i < pattern.length; i++) {
    const c = pattern[i]
    if (c === '\\') (put(pattern.slice(i, i + 2)), i++)
    else if (c === '[') {
      // A character class is copied whole: brackets inside it are not groups.
      let j = i + 1
      if (pattern[j] === '^') j++
      if (pattern[j] === ']') j++
      while (j < pattern.length && pattern[j] !== ']') j += pattern[j] === '\\' ? 2 : 1
      put(pattern.slice(i, j + 1))
      i = j
    } else if (c === '(') {
      const named = pattern.slice(i).match(/^\(\?P<([A-Za-z_]\w*)>/)
      if (named) {
        const group = { name: named[1], pieces: [] as Piece[] }
        stack[stack.length - 1].pieces.push(group)
        stack.push({ pieces: group.pieces, named: true })
        put(named[0])
        i += named[0].length - 1
      } else {
        put(c)
        stack.push({ pieces: stack[stack.length - 1].pieces, named: false })
      }
    } else if (c === ')') {
      put(c)
      if (stack.length > 1) stack.pop()
    } else put(c)
  }
  return root
}

const namesIn = (pieces: Piece[]): string[] => pieces.flatMap((p) => (typeof p === 'string' ? [] : [p.name, ...namesIn(p.pieces)]))

function Pattern({ pieces, tint }: { pieces: Piece[]; tint: (name: string) => string }): ReactNode {
  return pieces.map((p, i) =>
    typeof p === 'string' ? p : (
      <span key={i} className="rx-part" style={{ background: tint(p.name) }} title={`The part named “${p.name}”`}>
        <Pattern pieces={p.pieces} tint={tint} />
      </span>
    ),
  )
}

/** The matched text, with each named part in its colour. Where parts overlap, the smallest wins. */
function Matched({ m, tint }: { m: NonNullable<Evidence['matched']>; tint: (name: string) => string }) {
  const cuts = [...new Set([m.start, m.end, ...m.parts.flatMap((p) => [p.start, p.end])])].filter((n) => n >= m.start && n <= m.end).sort((a, b) => a - b)
  return (
    <span className="rx-text">
      {cuts.slice(0, -1).map((from, i) => {
        const to = cuts[i + 1]
        const inside = m.parts.filter((p) => p.start <= from && p.end >= to).sort((a, b) => a.end - a.start - (b.end - b.start))[0]
        const text = m.text.slice(from - m.start, to - m.start)
        return inside ? <span key={i} className="rx-part" style={{ background: tint(inside.name) }} title={`“${inside.name}”`}>{text}</span> : <span key={i}>{text}</span>
      })}
    </span>
  )
}

type Props = { rule: RuleInfo; evidence: Evidence[]; onHover: (h: Hover) => void; onLocate?: (hint: Omit<Jump, 'tick'>) => void }

/** One rule, in full: its name, what it does in plain words, its pattern, and what the pattern matched here. */
export function RuleCard({ rule, evidence, onHover, onLocate }: Props) {
  const pieces = groupsOf(rule.pattern)
  const names = namesIn(pieces)
  const tint = (name: string) => TINTS[Math.max(0, names.indexOf(name)) % TINTS.length]
  const hits = evidence.filter((e) => e.matched)
  const first = hits[0]
  const light = (e: Evidence | undefined) => onHover(e?.matched && e.document ? { document: e.document, start: e.matched.start, end: e.matched.end } : null)
  return (
    <div className="rulecard">
      <div className="rc-head">
        <span className="rc-kind">Rule</span>
        <code>{rule.name}</code>
        <span className="faint">looks in {rule.wherePlain.replace(/^The /, 'the ')}</span>
      </div>
      <p>{rule.description}</p>
      <div className="rc-grid">
        <span>Pattern</span>
        <code className="rx" title={first ? 'Point here to light up on the page everything this pattern matched' : undefined} onMouseEnter={() => light(first)} onMouseLeave={() => onHover(null)} onClick={() => first && onLocate?.({ n: first.n })}>
          <Pattern pieces={pieces} tint={tint} />
        </code>
        {hits.map((e) => (
          <Rows key={e.n} e={e} names={names} tint={tint} light={light} onHover={onHover} />
        ))}
        {!hits.length && evidence.some((e) => e.kind === 'markup') && (
          <>
            <span>Matched</span>
            <span className="mono">{evidence.find((e) => e.kind === 'markup')!.source?.quote} <span className="faint">in the page's HTML, which the rendered page does not show</span></span>
          </>
        )}
      </div>
    </div>
  )
}

function Rows({ e, names, tint, light, onHover }: { e: Evidence; names: string[]; tint: (n: string) => string; light: (e: Evidence | undefined) => void; onHover: (h: Hover) => void }) {
  const m = e.matched!
  const parts = [...m.parts].sort((a, b) => names.indexOf(a.name) - names.indexOf(b.name))
  const squash = (s: string) => (s.length > 220 ? s.slice(0, 150) + ' … ' + s.slice(-50) : s)
  return (
    <>
      <span>Matched</span>
      <span className="rx-match" onMouseEnter={() => light(e)} onMouseLeave={() => onHover(null)}>
        {m.text.length > 220 ? <span className="rx-text">{squash(m.text)}</span> : <Matched m={m} tint={tint} />}
      </span>
      <span>Parts</span>
      <span className="rx-parts">
        {parts.map((p) => {
          const text = m.text.slice(p.start - m.start, p.end - m.start)
          return (
            <span key={p.name} className="rx-row" onMouseEnter={() => e.document && onHover({ document: e.document, start: p.start, end: p.end })} onMouseLeave={() => onHover(null)}>
              <span className="rx-part mono" style={{ background: tint(p.name) }}>{p.name}</span>
              {PLAIN_PART[p.name] && <span className="faint">{PLAIN_PART[p.name]}</span>}
              <span className="rx-val">“{text.length > 90 ? text.slice(0, 60) + ' … ' + text.slice(-20) : text}”</span>
            </span>
          )
        })}
      </span>
    </>
  )
}

/** A table that turns catalog wording into a CTDL value: its name, what it is for, and the row used here. */
export function TableCard({ table, evidence }: { table: TableInfo; evidence: Evidence }) {
  const row = table.rows.find((r) => evidence.from?.replace(/[“”]/g, '') === r.wording)
  return (
    <div className="rulecard">
      <div className="rc-head">
        <span className="rc-kind">Table</span>
        <code>{table.name}</code>
        <span className="faint">{table.rows.length} rows</span>
      </div>
      <p>{table.description}</p>
      <div className="rc-grid">
        <span>Row used</span>
        <span className="rx-row"><span className="rx-val">{evidence.from}</span> <span className="faint">→</span> <b>{evidence.result}</b></span>
        {row?.because && (<><span>Because</span><span>{row.because}</span></>)}
      </div>
    </div>
  )
}
