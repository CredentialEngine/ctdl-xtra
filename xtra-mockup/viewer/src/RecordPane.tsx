import { useEffect, useMemo, useRef, useState } from 'react'
import { ValueEditor, emptyFor, labelOf, summarise, type EditContext } from './Editor'
import { Icon, IconButton, Sign } from './Rich'
import { toggleAccept } from './state'
import type { Course, CourseRow, DocMeta, Entry, Forms, Level, Review, Rules, Teaching } from './types'
import { CONFIDENCE, Failed, ModelOutput, Why, fromSource, type Hover, type Jump } from './Why'

const LANGUAGE_KEY = /^[a-z]{2,3}(-[A-Za-z]{2,4})?$/
const isObject = (v: unknown): v is Record<string, unknown> => typeof v === 'object' && v !== null && !Array.isArray(v)
const isLanguageMap = (v: unknown) => isObject(v) && !('@type' in v) && Object.keys(v).length > 0 && Object.keys(v).every((k) => LANGUAGE_KEY.test(k))
const foldable = (v: unknown) => isObject(v) || (Array.isArray(v) && v.some(isObject))

/** The nearest enclosing value that has a provenance entry: every click lands somewhere (section 8.1). */
export function nearest(path: string, provenance: Record<string, Entry>): string | null {
  for (let p = path; p; p = p.slice(0, p.lastIndexOf('/'))) if (provenance[p]) return p
  return null
}

// Fields that are not read from the page. In the Fields view they come last, so the first
// thing a reader meets is the course, not the plumbing.
const HOUSEKEEPING = ['/@context', '/@id', '/@type']
// The identifier comes first: whether the course already exists is the first thing to settle.
const CTID = '/ceterms:ctid'

export function topLevelStops(course: Course): string[] {
  const all = Object.keys(course.record).map((k) => `/${k}`).filter((p) => course.provenance[p])
  return [...all.filter((p) => p === CTID), ...all.filter((p) => p !== CTID && !HOUSEKEEPING.includes(p)), ...all.filter((p) => HOUSEKEEPING.includes(p))]
}

/** A value as a person would say it: "3 · Semester Hour", not an object. */
export function display(value: unknown, entry?: Entry): string {
  if (entry?.chip) return entry.chip
  if (isLanguageMap(value)) return Object.values(value as Record<string, unknown>).flat().join(' · ')
  if (Array.isArray(value)) return value.every((v) => typeof v !== 'object') ? value.join(', ') : `${value.length} items`
  if (isObject(value)) return String(value['@type'] ?? 'object').replace(/^\w+:/, '')
  return String(value)
}

// ------------------------------------------------------------------------------------- fields

type FieldsProps = {
  course: Course
  teaching: Teaching
  rules: Rules
  forms: Forms
  courses: CourseRow[]
  docs: Record<string, DocMeta>
  path: string | null
  stops: string[]
  level: Level
  setLevel: (l: Level) => void
  reasoning: boolean
  setReasoning: (on: boolean) => void
  reviews: Record<string, Review>
  onSelect: (path: string | null) => void
  onLocate: (path: string, hint?: Omit<Jump, 'tick'>) => void
  onFlip: (path: string) => void
  onTerm: (term: string | null) => void
  onReject: (path: string) => void
  onComment: (path: string) => void
  onReview: (path: string, fn: (r: Review) => Review) => void
  onHover: (h: Hover) => void
}

/** Opens and closes its contents by growing and shrinking, so the eye can follow where the box came from.
 *  The contents stay in the page until the closing has finished. */
function Expand({ open, children }: { open: boolean; children: React.ReactNode }) {
  const [present, setPresent] = useState(open)
  const [grown, setGrown] = useState(false)
  useEffect(() => {
    if (open) {
      setPresent(true)
      // Two frames: one to put it in the page closed, one to start it growing.
      const frame = requestAnimationFrame(() => requestAnimationFrame(() => setGrown(true)))
      return () => cancelAnimationFrame(frame)
    }
    setGrown(false)
    const timer = setTimeout(() => setPresent(false), 240)
    return () => clearTimeout(timer)
  }, [open])
  if (!present) return null
  return (
    <div className={'expand' + (grown ? ' open' : '')}>
      <div className="expand-in">{children}</div>
    </div>
  )
}

/** What stands behind the CTID field's "not built yet": is this course already in the Credential
 *  Registry? Answering needs a way to work out a resource's CTID that gives the same answer every time,
 *  and a look-up. Nothing here contacts the Registry or the Finder. */
function CtidDetail({ course }: { course: Course }) {
  const ctid = String(course.record['ceterms:ctid'] ?? '')
  return (
        <div className="stub-body">
          <p><b>This identifier is a placeholder.</b> Before a course is proposed as new, a reviewer should be able to confirm here whether the Credential Registry already holds it, and if it does, this field should show the CTID it already has. That check does not exist yet. Two things are needed:</p>
          <ol>
            <li><b>A stable CTID.</b> A way to work out the identifier for a resource that gives the same answer every time, for anyone, from what the resource is. Today the identifier is made at random the first time a course is seen and remembered in a ledger on this machine.</li>
            <li><b>A look-up.</b> Ask the Registry whether a record with that identifier already exists, and show it beside xTRA’s proposal.</li>
          </ol>
          <p>
            <b>The approach we will probably take:</b> it depends on the class of the resource. For a course, take the course’s own ID from the catalog
            (here <span className="mono">{String(course.record['ceterms:codedNotation'] ?? course.code)}</span>), together with the organization that owns it, and look for a course with that ID
            in Credential Engine’s Credential Finder database. If one is found, it is shown here beside xTRA’s proposal, and you say whether they are the same course. Other classes would be
            matched on whatever identifies them.
          </p>
          <div className="stub-row">
            <span>Would look up</span>
            <span><span className="mono">{String(course.record['ceterms:codedNotation'] ?? course.code)}</span> <span className="faint">a Course, in the Credential Finder</span></span>
            <span className="faint">not looked up: nothing here contacts the Finder or the Registry</span>
          </div>
          <div className="stub-row">
            <span>Identifier today</span>
            <span className="mono">{ctid}</span>
            <span className="faint">a placeholder; not looked up</span>
          </div>
          <div className="stub-row">
            <span>Your verdict</span>
            <span>
              <button className="btn" disabled title="Not built yet">Already exists</button>{' '}
              <button className="btn" disabled title="Not built yet">New to the Registry</button>
            </span>
          </div>
        </div>
  )
}

/** Why a field must be present on every course, if it must. */
function requiredNote(term: string, forms: Forms): string | null {
  if (forms.required.includes(term)) return 'Required: Credential Engine will not accept a course without it.'
  if (forms.requiredOneOf.includes(term)) return `Required, unless the other is given: ${forms.requiredOneOf.map((t) => forms.properties[t]?.label ?? t).join(' or ')}.`
  return null
}
const Required = ({ term, forms }: { term: string; forms: Forms }) => {
  const note = requiredNote(term, forms)
  return note ? <span className="req" title={note} aria-label="Required">*</span> : null
}

/** A field CTDL allows on this kind of record that xTRA proposed nothing for. Shown empty, with a grey
 *  edge where a proposal would carry its confidence, so the reader sees the whole of what could be said. */
function BlankCard({ term, ctx, review, onTerm, onReview }: { term: string; ctx: EditContext; review: Review; onTerm: (t: string) => void; onReview: (fn: (r: Review) => Review) => void }) {
  const [editing, setEditing] = useState(false)
  const prop = ctx.forms.properties[term]
  const filled = review.value !== undefined && review.value !== null
  return (
    <div className={'card blank' + (filled ? ' filled' : '')} onClick={(e) => e.stopPropagation()}>
      <div className="card-head">
        <button className="fname" title="What CTDL says this field is" onClick={() => onTerm(term)}>{prop?.label ?? term}</button>
        <Required term={term} forms={ctx.forms} />
        {filled && <span className="tag">added by you</span>}
        <span className="sp" />
        <button className="prop mono" title="What CTDL says this field is" onClick={() => onTerm(term)}>{term}</button>
      </div>
      <div className="card-body">
        {editing ? (
          <ValueEditor fixed term={term} value={filled ? review.value : emptyFor(term, ctx)} ctx={ctx} onSave={(next) => (setEditing(false), onReview((r) => ({ ...r, value: next ?? undefined })))} onCancel={() => setEditing(false)} />
        ) : (
          <div className="fvalue" title={filled ? 'Double-click to edit' : 'xTRA proposed nothing for this field. Click to fill it in.'} onClick={() => !filled && setEditing(true)} onDoubleClick={() => setEditing(true)}>
            {filled ? <div className="clamp">{summarise(review.value, ctx)}</div> : <span className="none">No proposal</span>}
          </div>
        )}
      </div>
      {!editing && (
        <div className="acts">
          <IconButton name="edit" title={filled ? 'Edit the value' : 'Fill this field in'} onClick={() => setEditing(true)} />
          <IconButton name="info" title="What CTDL says this field is" onClick={() => onTerm(term)} />
          {filled && <IconButton name="undo" title="Clear what you added" onClick={() => onReview((r) => ({ ...r, value: undefined }))} />}
        </div>
      )}
    </div>
  )
}

/** The default view of a record: one card per field, in plain words. JSON is one tab away. */
export function Fields(p: FieldsProps) {
  const all = topLevelStops(p.course)
  const active = useRef<HTMLDivElement>(null)
  useEffect(() => {
    active.current?.scrollIntoView({ block: 'nearest' })
  }, [p.path])
  // Everything CTDL allows on this kind of record that the record does not have: required ones first.
  const blanks = useMemo(() => {
    const cls = p.forms.classes[String(p.course.record['@type'])] ?? p.forms.classes[p.forms.root]
    const must = (t: string) => Number(p.forms.required.includes(t) || p.forms.requiredOneOf.includes(t))
    return (cls?.properties ?? [])
      .filter((t) => !(t in p.course.record))
      .sort((a, b) => must(b) - must(a) || (p.forms.properties[a]?.label ?? a).localeCompare(p.forms.properties[b]?.label ?? b))
  }, [p.forms, p.course])
  const [showBlanks, setShowBlanks] = useState(() => localStorage.getItem('xtra-blanks') !== 'hidden')
  const toggleBlanks = () => setShowBlanks((on) => (localStorage.setItem('xtra-blanks', on ? 'hidden' : 'shown'), !on))
  const ctx = useMemo<EditContext>(
    () => ({
      forms: p.forms,
      courses: p.courses,
      references: p.course.references,
      labels: Object.fromEntries(Object.values(p.teaching.slots).filter((s) => s.term).map((s) => [s.term!, s.label])),
    }),
    [p.forms, p.courses, p.course.references, p.teaching],
  )
  const done = all.filter((x) => p.reviews[x]?.accepted).length
  const rejected = all.filter((x) => p.reviews[x]?.rejected).length
  const commented = all.filter((x) => p.reviews[x]?.comment && !p.reviews[x]?.rejected).length
  const edited = all.filter((x) => p.reviews[x]?.value !== undefined).length
  const moved = all.filter((x) => p.reviews[x]?.segments?.length).length
  return (
    <>
      <div className="fields" onClick={() => p.onSelect(null)}>
        {all.map((path) => [
          path === HOUSEKEEPING.find((h) => all.includes(h)) && <div key="g" className="group-label">Not read from the page</div>,
          <Card key={path} {...p} ctx={ctx} cardPath={path} activeRef={path === p.path ? active : undefined} dimmed={!p.stops.includes(path)} />,
        ])}
        {blanks.length > 0 && (
          <button className="group-label fold" onClick={(e) => (e.stopPropagation(), toggleBlanks())} title="Every other field CTDL allows on this kind of record">
            <span className="tw">{showBlanks ? '▾' : '▸'}</span> No proposal from xTRA · {blanks.length} more fields CTDL allows
          </button>
        )}
        {showBlanks && blanks.map((term) => (
          <BlankCard key={term} term={term} ctx={ctx} review={p.reviews['/' + term] ?? {}} onTerm={p.onTerm} onReview={(fn) => p.onReview('/' + term, fn)} />
        ))}
      </div>
      <div className="tally">
        <span>Accepted <b>{done}</b> of {all.length}</span>
        {rejected > 0 && <span>Rejected <b>{rejected}</b></span>}
        {commented > 0 && <span>Commented <b>{commented}</b></span>}
        {edited > 0 && <span>Edited <b>{edited}</b></span>}
        {moved > 0 && <span>Re-attributed <b>{moved}</b></span>}
        <span className="sp" />
        <span className="faint">Kept in this browser only</span>
      </div>
    </>
  )
}

function Card(p: FieldsProps & { ctx: EditContext; cardPath: string; activeRef?: React.RefObject<HTMLDivElement | null>; dimmed: boolean }) {
  const path = p.cardPath
  const entry = p.course.provenance[path]
  const slot = p.teaching.slots[entry.slot]
  const value = p.course.record[path.slice(1)]
  const review = p.reviews[path] ?? {}
  const isActive = p.path === path
  const [editing, setEditing] = useState(false)
  const term = path.slice(1)
  // Made by the system, not read or judged: nothing here for a reviewer to change.
  const locked = ['@context', '@id', 'ceterms:ctid'].includes(term)
  // An edit made before the form existed was kept as text; it cannot be shown in the form.
  const edited = review.value !== undefined && !(typeof review.value === 'string' && typeof value !== 'string') ? review.value : undefined
  const changed = edited !== undefined || !!review.property
  useEffect(() => {
    if (!isActive) setEditing(false)
  }, [isActive])
  const startEditing = () => !locked && (p.onSelect(path), setEditing(true))
  const save = (next: unknown, property: string) => {
    setEditing(false)
    const same = JSON.stringify(next) === JSON.stringify(value)
    p.onReview(path, (r) => ({ ...r, value: same ? undefined : next ?? null, property: property === term ? undefined : property }))
  }
  // A requirement is shown as its sentence, with how far it could be structured as a small tag.
  const sentences = entry.structure?.map((s) => s.sentence.quote.replace(/\s+/g, ' ')).join(' ')
  const shown = edited === null ? 'Removed from the record' : edited !== undefined ? summarise(edited, p.ctx) : sentences ?? display(value, entry)
  const sourced = fromSource(entry)
  const failed = entry.checks.filter((c) => c.status === 'fail')
  const isCtid = path === CTID
  const [detail, setDetail] = useState(false)
  const toggleWhy = () => {
    const opening = !(isActive && p.reasoning)
    p.onSelect(path)
    p.setReasoning(opening)
  }
  const warn = entry.flags.filter((f) => ['partly-structured', 'loses-detail', 'sentence-only', 'placeholder', 'referenced-no-record'].includes(f.id))

  return (
    <div
      ref={p.activeRef}
      className={`card c-${entry.confidence.level}` + (isActive ? ' active' : '') + (review.accepted ? ' accepted' : '') + (review.rejected ? ' rejected' : '') + (isCtid ? ' ctid' : '') + (p.dimmed ? ' dimmed' : '')}
      onClick={(e) => (e.stopPropagation(), p.onSelect(path))}
    >
      <div className="card-head">
        <button className="fname" title="What CTDL says this field is" onClick={(e) => (e.stopPropagation(), p.onTerm(review.property ?? term))}>{isCtid ? 'CTID' : review.property ? labelOf(review.property, p.ctx) : slot?.label ?? term}</button>
        <Required term={review.property ?? term} forms={p.forms} />
        {isCtid && <button className={'stub-tag' + (detail ? ' on' : '')} title="A placeholder. Checking whether this course already has a CTID is not built yet. Click for the detail." onClick={(e) => (e.stopPropagation(), setDetail(!detail))}>not built yet</button>}
        {review.accepted && <span className="tag ok">accepted</span>}
        {review.rejected && <span className="tag no">rejected</span>}
        {review.comment && !review.rejected && !review.accepted && <span className="tag">commented</span>}
        {changed && <span className="tag">{review.property ? `edited · was ${slot?.label ?? term}` : 'edited'}</span>}
        {entry.structure && <span className="tag">{entry.structure.some((s) => s.builtBy === 'language model') && <Sign kind="lm" />}{entry.structure.map((s) => (s.tree ? s.summary : 'sentence only')).join(' · ')}</span>}
        <span className="sp" />
        <button className="prop mono" title="What CTDL says this field is" onClick={(e) => (e.stopPropagation(), p.onTerm(review.property ?? term))}>{review.property ?? term}</button>
      </div>
      <div className="card-body">
        {editing ? (
          <ValueEditor term={term} value={edited !== undefined && edited !== null ? edited : value} ctx={p.ctx} onSave={save} onCancel={() => setEditing(false)} />
        ) : (
          <div
            className={'fvalue' + (sourced ? ' sourced' : '')}
            title={sourced ? 'Show where this is on the page. Double-click to edit.' : locked ? 'Made by the system.' : 'Not read from a page. Double-click to edit.'}
            onClick={(e) => sourced && (e.stopPropagation(), p.onLocate(path))}
            onDoubleClick={startEditing}
          >
            <div className={isActive ? undefined : 'clamp'}>{shown}</div>
          </div>
        )}
      </div>
      {review.comment && (
        <button className={'said' + (review.rejected ? ' no' : '')} title={review.rejected ? 'Change the reason (C)' : 'Change the comment (C)'} onClick={(e) => (e.stopPropagation(), p.onSelect(path), p.onComment(path))}>
          {review.rejected ? <span className="x">✗</span> : <Icon name="comment" size={13} />} <span>{review.comment}</span>
        </button>
      )}
      {/* The actions sit beneath the value and open on hover, so nothing in the heading moves under the pointer. */}
      {!editing && (
        <div className="acts">
          <IconButton name="check" title={review.accepted ? 'Accepted. Click to undo (A)' : 'Accept (A)'} on={review.accepted} onClick={() => p.onReview(path, toggleAccept)} />
          <IconButton name="close" title={review.rejected ? 'Rejected. Click to undo (R)' : 'Reject, and say why (R)'} on={review.rejected} onClick={() => (p.onSelect(path), p.onReject(path))} />
          <IconButton name="comment" title={review.comment ? 'Change what you wrote (C)' : 'Leave a comment (C)'} on={!!review.comment && !review.rejected} onClick={() => (p.onSelect(path), p.onComment(path))} />
          <IconButton name="edit" title={locked ? 'Made by the system. There is nothing here to edit.' : 'Edit the value'} disabled={locked} onClick={startEditing} />
          {isCtid ? (
            <IconButton name="info" title="Why this is a placeholder, and what is not built yet" on={detail} onClick={() => (p.onSelect(path), setDetail(!detail))} />
          ) : (
            <IconButton name="info" title="Why this value" on={isActive && p.reasoning} onClick={toggleWhy} />
          )}
          <IconButton name="code" title="Show this field in Raw (V)" onClick={() => p.onFlip(path)} />
          {changed && <IconButton name="undo" title="Put the suggested value back" onClick={() => p.onReview(path, (r) => ({ ...r, value: undefined, property: undefined }))} />}
        </div>
      )}
      {/* Confidence is the colour of the card's right edge; clicking it opens the reasoning. */}
      <button
        className={'confbar' + (isActive && p.reasoning ? ' open' : '')}
        title={`${CONFIDENCE[entry.confidence.level]}. ${entry.confidence.why} Click for the reasoning.`}
        aria-label={`${CONFIDENCE[entry.confidence.level]}. Show the reasoning.`}
        onClick={(e) => (e.stopPropagation(), toggleWhy())}
      />
      {isActive && !p.reasoning && entry.structure?.some((s) => s.languageModel) && (
        <div className="card-lm" onClick={(e) => e.stopPropagation()}>
          {entry.structure.map((s, i) => <ModelOutput key={i} s={s} document={p.course.block.document} onHover={p.onHover} />)}
        </div>
      )}
      {isActive && !p.reasoning && failed.map((c, i) => <Failed key={i} check={c} />)}
      {isActive && !p.reasoning && warn.map((f) => (
        <div key={f.id} className="caution"><Sign kind={f.id === 'language-model' ? 'lm' : 'warn'} /> <span>{f.text}</span></div>
      ))}
      {isActive && (review.segments ?? []).map((s, i) => (
        <div key={i} className="human">
          <span className="q">{s.quote.replace(/\s+/g, ' ').slice(0, 120)}</span>
          <span className="who">you</span>
          <IconButton name="close" title="Remove this attribution" onClick={() => p.onReview(path, (r) => ({ ...r, segments: r.segments?.filter((_, j) => j !== i) }))} />
        </div>
      ))}
      {isCtid && (
        <Expand open={detail}>
          <div onClick={(e) => e.stopPropagation()}><CtidDetail course={p.course} /></div>
        </Expand>
      )}
      <Expand open={isActive && p.reasoning}>
        <div onClick={(e) => e.stopPropagation()}>
          <Why course={p.course} path={path} entry={entry} teaching={p.teaching} rules={p.rules} docs={p.docs} level={p.level} setLevel={p.setLevel} onHover={p.onHover} onLocate={(hint) => p.onLocate(path, hint)} />
        </div>
      </Expand>
    </div>
  )
}

// --------------------------------------------------------------------------------------- JSON

export type Line = {
  indent: number
  path: string
  keyName?: string
  open?: string
  close?: string
  scalar?: string
  chip?: string
  text?: string
  comma: boolean
  fold?: 'folded' | 'unfolded'
}

/** The record as lines. Folded, an object is one labelled chip; unfolded, it is exactly what is on disk. */
export function jsonLines(course: Course, unfolded: Set<string>, unfoldAll: boolean): Line[] {
  const lines: Line[] = []
  const walk = (value: unknown, path: string, keyName: string | undefined, indent: number, comma: boolean, inList = false) => {
    // An object directly inside an unfolded list unfolds with the list.
    const expand = unfoldAll || unfolded.has(path) || path === '' || inList
    const canFold = path !== '' && (foldable(value) || isLanguageMap(value))
    if (!expand && canFold) {
      if (isLanguageMap(value)) lines.push({ indent, path, keyName, text: display(value), comma, fold: 'folded' })
      else lines.push({ indent, path, keyName, chip: course.provenance[path]?.chip ?? display(value), comma, fold: 'folded' })
      return
    }
    if (Array.isArray(value) && !(unfoldAll || value.some(isObject))) {
      lines.push({ indent, path, keyName, scalar: JSON.stringify(value).replace(/,/g, ', '), comma })
      return
    }
    if (Array.isArray(value) || isObject(value)) {
      const items: [string, unknown, string | undefined][] = Array.isArray(value)
        ? value.map((v, i) => [`${path}/${i}`, v, undefined])
        : Object.entries(value).map(([k, v]) => [`${path}/${k}`, v, k])
      const [o, c] = Array.isArray(value) ? ['[', ']'] : ['{', '}']
      lines.push({ indent, path, keyName, open: o, comma: false, fold: canFold && !unfoldAll && !inList ? 'unfolded' : undefined })
      items.forEach(([p, v, k], i) => walk(v, p, k, indent + 1, i < items.length - 1, Array.isArray(value)))
      lines.push({ indent, path, close: c, comma })
      return
    }
    lines.push({ indent, path, keyName, scalar: JSON.stringify(value), comma })
  }
  walk(course.record, '', undefined, 0, false)
  return lines
}

export function jsonStops(course: Course, lines: Line[]): string[] {
  const seen = new Set<string>()
  for (const l of lines) if (course.provenance[l.path]) seen.add(l.path)
  return [...seen]
}

type JsonProps = {
  course: Course
  lines: Line[]
  path: string | null
  onSelect: (path: string | null) => void
  onLocate: (path: string, hint?: Omit<Jump, 'tick'>) => void
  onFlip: (path: string) => void
  onTerm: (term: string | null) => void
  onFold: (path: string) => void
  exact: boolean
}

export function JsonView({ course, lines, path, onSelect, onLocate, onFlip, onTerm, onFold, exact }: JsonProps) {
  const selected = useRef<HTMLDivElement>(null)
  useEffect(() => {
    selected.current?.scrollIntoView({ block: 'nearest' })
  }, [path])
  let refGiven = false
  return (
    <div className={'json mono' + (exact ? ' exact' : '')} onClick={() => onSelect(null)}>
      {lines.map((l, i) => {
        const entry = course.provenance[l.path]
        const target = nearest(l.path, course.provenance)
        const owner = target ? course.provenance[target] : undefined
        const sourced = fromSource(owner)
        const quote = l.text ?? (l.scalar?.startsWith('"') ? (JSON.parse(l.scalar) as string) : undefined)
        const isSel = !!path && (l.path === path || l.path.startsWith(path + '/'))
        const flagged = entry?.flags.some((f) => !['placeholder', 'referenced-no-record'].includes(f.id))
        const lm = entry && (entry.method === 'language model' || entry.flags.some((f) => f.id === 'language-model'))
        const first = !l.close
        const ref = isSel && !refGiven ? ((refGiven = true), selected) : undefined
        return (
          <div
            key={i}
            ref={ref}
            className={'jl' + (isSel ? ' sel' : '') + (owner ? ` c-${owner.confidence.level}` : '')}
            title={owner && !l.close ? CONFIDENCE[owner.confidence.level] : undefined}
            onClick={(e) => {
              e.stopPropagation()
              // A value read from a document takes the reader to that place in it.
              if (target && sourced) onLocate(target, { quote })
              else if (target) onSelect(target)
              if (l.chip) onFold(l.path)
            }}
          >
            {/* At most one small mark per line, and only where attention is wanted (JP6). */}
            <span className="g">{first && lm ? <Sign kind="lm" /> : first && flagged ? <Sign kind="warn" title={entry!.flags.map((f) => f.text).join(' ')} /> : null}</span>
            <span className="c" style={{ paddingLeft: l.indent * 16 }}>
              {l.fold && (
                <button className="caret" title={l.fold === 'folded' ? 'Unfold' : 'Fold'} onClick={(e) => (e.stopPropagation(), onFold(l.path))}>
                  {l.fold === 'folded' ? '▸' : '▾'}
                </button>
              )}
              {l.keyName !== undefined && <><span className="k" title="What CTDL says this field is" onClick={(e) => (e.stopPropagation(), onTerm(l.keyName!))}>"{l.keyName}"</span><span className="p">: </span></>}
              {l.open && <span className="p">{l.open}</span>}
              {l.close && <span className="p">{l.close}</span>}
              {l.chip !== undefined && <span className="chip">{l.chip}</span>}
              {l.text !== undefined && <span className={'s' + (sourced ? ' src' : '')}>"{l.text}"</span>}
              {l.scalar !== undefined && <span className={(/^[-\d]/.test(l.scalar) ? 'num' : 's') + (sourced ? ' src' : '')}>{l.scalar}</span>}
              {l.comma && <span className="p">,</span>}
            </span>
            {/* One per field, on the line that names it: the lines inside a field all lead to the same card. */}
            {target && first && l.path.lastIndexOf('/') === 0 && (
              <button className="flip" title="Show this field in Pretty (V)" onClick={(e) => (e.stopPropagation(), onFlip(target))}>
                <Icon name="cards" size={13} />
              </button>
            )}
          </div>
        )
      })}
    </div>
  )
}
