import { useEffect, useMemo, useRef, useState } from 'react'
import { Icon } from './Rich'
import { isDecided } from './state'
import type { CourseRow, DocMeta, Review } from './types'

type Props = {
  courses: CourseRow[]
  docs: Record<string, DocMeta>
  current: string | null
  hidden: boolean
  reviews: Record<string, Record<string, Review>>
  organisation: { name: string; address: string } | null
  onOpen: (id: string) => void
}

/** A row's background fills from the left as its fields are decided, like a progress bar. */
export const fill = (share: number) => (share > 0 ? { backgroundImage: `linear-gradient(to right, #d9f0e2 ${share}%, transparent ${share}%)` } : undefined)

/** Everything under review, by CTDL class: the courses by subject, then what they only refer to. */
export function Sidebar({ courses, docs, current, hidden, reviews, organisation, onOpen }: Props) {
  const [find, setFind] = useState('')
  const currentSubject = courses.find((c) => c.id === current)?.subject
  const [open, setOpen] = useState<Set<string>>(new Set(currentSubject ? [currentSubject] : []))
  const here = useRef<HTMLButtonElement>(null)

  // Walking into another subject opens it, without closing what was opened by hand.
  useEffect(() => {
    if (currentSubject) setOpen((old) => (old.has(currentSubject) ? old : new Set(old).add(currentSubject)))
  }, [currentSubject])
  useEffect(() => {
    here.current?.scrollIntoView({ block: 'nearest' })
  }, [current, open])

  const subjectNames = useMemo(() => {
    const names: Record<string, string> = {}
    for (const d of Object.values(docs)) {
      const m = d.role === 'subject' && d.title?.match(/^(.*?)\s*\(([A-Z0-9]+)\)/)
      if (m) names[m[2]] = m[1]
    }
    return names
  }, [docs])

  // A course is done when every one of its fields has been dealt with: accepted, rejected, or commented on.
  const accepted = (c: CourseRow) => Math.min(c.stops, Object.entries(reviews[c.id] ?? {}).filter(([path, r]) => isDecided(r) && path.lastIndexOf('/') === 0).length)
  const rejected = (c: CourseRow) => Object.entries(reviews[c.id] ?? {}).filter(([path, r]) => r.rejected && path.lastIndexOf('/') === 0).length
  const progress = useMemo(() => {
    const by: Record<string, { fields: number; accepted: number; courses: number; done: number }> = {}
    for (const c of courses) {
      const p = (by[c.subject] ??= { fields: 0, accepted: 0, courses: 0, done: 0 })
      const n = accepted(c)
      p.fields += c.stops
      p.accepted += n
      p.courses += 1
      if (c.stops > 0 && n >= c.stops) p.done += 1
    }
    return by
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [courses, reviews])

  const needle = find.trim().toLowerCase()
  const groups = useMemo(() => {
    const by = new Map<string, CourseRow[]>()
    for (const c of courses) {
      if (needle && !`${c.code} ${c.name}`.toLowerCase().includes(needle)) continue
      by.set(c.subject, [...(by.get(c.subject) ?? []), c])
    }
    return [...by.entries()]
  }, [courses, needle])
  const shown = groups.reduce((n, [, rows]) => n + rows.length, 0)

  return (
    <nav className={'sidebar' + (hidden ? ' closed' : '')} inert={hidden}>
      <input className="find" placeholder="Find a course" value={find} onChange={(e) => setFind(e.target.value)} onKeyDown={(e) => e.key === 'Escape' && (setFind(''), e.currentTarget.blur())} />
      <div className="side-scroll">
        <div className="side-class">
          <span>Course</span>
          <span className="faint">{needle ? `${shown} of ${courses.length}` : courses.length}</span>
        </div>
        {groups.map(([subject, rows]) => {
          const isOpen = !!needle || open.has(subject)
          const p = progress[subject]
          const share = p.fields ? (p.accepted / p.fields) * 100 : 0
          return (
            <div key={subject}>
              <button
                className="side-subject"
                title={`${subjectNames[subject] ?? subject}: ${p.done} of ${p.courses} courses done, ${p.accepted.toLocaleString()} of ${p.fields.toLocaleString()} fields decided`}
                style={{ backgroundImage: `linear-gradient(to right, #cdebd9 ${share}%, transparent ${share}%)` }}
                onClick={() => setOpen((old) => {
                  const next = new Set(old)
                  if (next.has(subject)) next.delete(subject)
                  else next.add(subject)
                  return next
                })}
              >
                <span className="tw">{isOpen ? '▾' : '▸'}</span>
                <b>{subject}</b>
                <span className="clip muted">{subjectNames[subject]}</span>
                <span className="sp" />
                <span className="faint">{p.done > 0 ? `${p.done} / ` : ''}{rows.length}</span>
              </button>
              {isOpen && rows.map((c) => {
                const n = accepted(c)
                const done = c.stops > 0 && n >= c.stops
                return (
                  <button key={c.id} ref={c.id === current ? here : undefined} className={'side-row' + (c.id === current ? ' on' : '') + (done ? ' done' : '')} title={`${c.code} · ${c.name} · ${n} of ${c.stops} fields decided${rejected(c) ? `, ${rejected(c)} rejected` : ''}`} style={fill(c.stops ? (n / c.stops) * 100 : 0)} onClick={() => onOpen(c.id)}>
                    <span className="mono">{c.code.split(' ')[1] ?? c.code}</span>
                    <span className="clip">{c.name}</span>
                    {rejected(c) > 0 && <span className="mark no">✗{rejected(c)}</span>}
                    {done ? <span className="mark">✓</span> : n > 0 && <span className="mark part">{n}/{c.stops}</span>}
                  </button>
                )
              })}
            </div>
          )
        })}
        {needle && !shown && <div className="side-none">No course matches.</div>}

        {organisation && (
          <>
            <div className="side-class">
              <span>Organization</span>
              <span className="faint">1</span>
            </div>
            <a className="side-row ref" href={organisation.address} target="_blank" rel="noreferrer" title="Already in the Credential Registry. The courses only refer to it; it is not under review here.">
              <span className="clip">{organisation.name}</span>
              <Icon name="out" size={13} />
            </a>
            <div className="side-none">Already in the Registry. Referred to, not under review.</div>
          </>
        )}
      </div>
    </nav>
  )
}
