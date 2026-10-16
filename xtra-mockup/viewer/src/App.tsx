import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { loadCourse, loadCourses, loadDocuments, loadForms, loadRules, loadTeaching } from './data'
import { Fields, JsonView, display, jsonLines, jsonStops, topLevelStops } from './RecordPane'
import { GlossaryContext, IconButton, Rich, Segmented } from './Rich'
import { Sidebar } from './Sidebar'
import { SourcePane } from './SourcePane'
import { rejectWith, toggleAccept, unreject, useReviews, useRoute } from './state'
import { NoteBox } from './Reject'
import { Tour, type Demo } from './Tour'
import type { Course, CourseRow, DocMeta, Forms, Review, Rules, Teaching } from './types'
import { Why, type Hover, type Jump } from './Why'

type Base = { courses: CourseRow[]; docs: Record<string, DocMeta>; teaching: Teaching; rules: Rules; forms: Forms }

export default function App() {
  const [route, go] = useRoute()
  const [base, setBase] = useState<Base | null>(null)
  const [course, setCourse] = useState<Course | null>(null)
  const [error, setError] = useState('')
  const [unfolded, setUnfolded] = useState<Set<string>>(new Set())
  const [unfoldAll, setUnfoldAll] = useState(false)
  const [reasoning, setReasoning] = useState(false)
  const [jump, setJump] = useState<Jump>({ tick: 0 })
  const [hover, setHover] = useState<Hover>(null)
  const [term, setTerm] = useState<string | null>(null)
  const [noting, setNoting] = useState<{ path: string; mode: 'reject' | 'comment' } | null>(null)
  const [tour, setTour] = useState(true)
  // The definitions opened in the browser, oldest first: following a link inside one adds to the trail.
  const [trail, setTrail] = useState<string[]>([])
  const defined = trail[trail.length - 1] ?? null
  const setDefined = useCallback((t: string | null) => setTrail(t ? [t] : []), [])
  // Clicking a field's name opens its definition in the browser; clicking it again closes it.
  const define = useCallback((t: string | null) => setTrail((old) => (!t || (old.length === 1 && old[0] === t) ? [] : [t])), [])
  const [finished, setFinished] = useState(false)
  const [copied, setCopied] = useState(false)
  const [sidebar, setSidebar] = useState(() => localStorage.getItem('xtra-sidebar') !== 'hidden')
  const [split, setSplit] = useState(() => Number(localStorage.getItem('xtra-record-width')) || 44)
  const [whySplit, setWhySplit] = useState(46)
  const reviews = useReviews()

  useEffect(() => {
    Promise.all([loadCourses(), loadDocuments(), loadTeaching(), loadRules(), loadForms()])
      .then(([courses, docs, teaching, rules, forms]) => setBase({ courses, docs, teaching, rules, forms }))
      .catch((e) => setError(`The extract step's output could not be read (${e.message}). Run “uv run xtra extract” first.`))
  }, [])

  const courseId = route.course ?? base?.courses[0]?.id ?? null
  useEffect(() => {
    if (!courseId) return
    let live = true
    loadCourse(courseId)
      .then((c) => live && (setCourse(c), setUnfolded(new Set()), setUnfoldAll(false), setFinished(false), setHover(null)))
      .catch((e) => setError(`Course ${courseId} could not be read (${e.message}).`))
    return () => {
      live = false
    }
  }, [courseId])

  const ready = course && course.id === courseId ? course : null
  const lines = useMemo(() => (ready ? jsonLines(ready, unfolded, unfoldAll) : []), [ready, unfolded, unfoldAll])
  const everyStop = useMemo(() => (!ready ? [] : route.view === 'fields' ? topLevelStops(ready) : jsonStops(ready, lines)), [ready, route.view, lines])
  const judgement = useMemo(() => everyStop.filter((p) => ready!.provenance[p].judgement), [everyStop, ready])
  const stops = route.walk === 'judgement' ? judgement : everyStop
  const path = ready && route.stop && ready.provenance[route.stop] ? route.stop : null
  const entry = path ? ready!.provenance[path] : null
  const index = base && courseId ? base.courses.findIndex((c) => c.id === courseId) : -1
  const row = index >= 0 ? base!.courses[index] : null

  const select = useCallback((p: string | null) => (setFinished(false), setHover(null), p && setDefined(null), setJump((old) => (old.n || old.quote ? { tick: old.tick } : old)), go({ stop: p })), [go])

  // Clicking a value that was read from a document always brings that place into view, even when
  // the value is already selected or another document is showing.
  const locate = useCallback((p: string, hint: Omit<Jump, 'tick'> = {}) => (select(p), setJump((old) => ({ tick: old.tick + 1, ...hint }))), [select])
  // The same field in the other view: Raw opens it unfolded, Pretty shows the card that holds it.
  const flip = useCallback(
    (p: string | null) => {
      const top = p && '/' + p.split('/')[1]
      if (route.view === 'fields') {
        if (top) setUnfolded((old) => new Set(old).add(top))
        go({ view: 'json', stop: p })
      } else go({ view: 'fields', stop: top && ready?.provenance[top] ? top : p })
      setHover(null)
    },
    [route.view, ready, go],
  )
  const toggleSidebar = () => setSidebar((on) => (localStorage.setItem('xtra-sidebar', on ? 'hidden' : 'shown'), !on))

  const step = useCallback(
    (by: 1 | -1) => {
      if (!stops.length) return setFinished(true)
      const at = path ? stops.indexOf(path) : -1
      const next = at < 0 ? (by > 0 ? 0 : stops.length - 1) : at + by
      // After the last stop, Tab does not wrap around silently (WK6).
      if (next >= stops.length) return setFinished(true)
      if (next < 0) return
      select(stops[next])
    },
    [stops, path, select],
  )

  const openCourse = useCallback(
    (by: 1 | -1) => {
      if (!base || index < 0) return
      for (let i = index + by; i >= 0 && i < base.courses.length; i += by) {
        // Set to judgement calls, Enter skips courses that have none (WK7).
        if (route.walk === 'everything' || base.courses[i].judgementCalls > 0) return go({ course: base.courses[i].id, stop: null }, true)
      }
    },
    [base, index, route.walk, go],
  )

  const review = useCallback((p: string, fn: (r: Review) => Review) => ready && reviews.change(ready.id, p, fn), [ready, reviews])

  // Rejecting asks why straight away; rejecting again withdraws it.
  const reject = useCallback(
    (p: string) => {
      if (!ready) return
      // Nothing is recorded yet: a rejection needs its reason first.
      if (reviews.all[ready.id]?.[p]?.rejected) (reviews.change(ready.id, p, unreject), setNoting(null))
      else setNoting({ path: p, mode: 'reject' })
    },
    [ready, reviews],
  )
  const comment = useCallback((p: string) => setNoting({ path: p, mode: 'comment' }), [])
  // The tour's last step shows evidence, so it selects a field that has some.
  const demoed = useRef(false)
  const tourStep = useCallback(
    (demo: Demo | null) => {
      if (!ready?.provenance['/ceterms:name']) return
      // The tour clicks a value, then its coloured edge, then its field's name, as the reader would.
      // A step with nothing to perform only undoes what an earlier step did, so that the tour, which opens
      // with every page load, leaves a field the address already pointed at selected.
      if (!demo && !demoed.current) return
      demoed.current = !!demo
      setReasoning(demo === 'reasoning')
      if (demo === 'source' || demo === 'reasoning') locate('/ceterms:name')
      else if (demo === 'definition') (select('/ceterms:name'), setTrail(['ceterms:name']))
      else (select(null), setTrail([]))
    },
    [ready, locate, select],
  )

  const keys = useRef({ step, openCourse, select, review, path, flip, reject, comment, tour })
  keys.current = { step, openCourse, select, review, path, flip, reject, comment, tour }
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const el = document.activeElement
      if (el && (['INPUT', 'TEXTAREA', 'SELECT'].includes(el.tagName) || el.closest('.editor'))) return
      const k = keys.current
      if (k.tour) return
      if (e.key === 'Tab') (e.preventDefault(), k.step(e.shiftKey ? -1 : 1))
      else if (e.key === 'Enter') (e.preventDefault(), k.openCourse(e.shiftKey ? -1 : 1))
      else if (e.key === 'Escape') (k.select(null), setNoting(null), setDefined(null), setTerm(null))
      else if ((e.key === 'v' || e.key === 'V') && !e.metaKey && !e.ctrlKey && !e.altKey) k.flip(k.path)
      else if ((e.key === 'a' || e.key === 'A') && !e.metaKey && !e.ctrlKey && k.path) k.review(k.path, toggleAccept)
      else if ((e.key === 'r' || e.key === 'R') && !e.metaKey && !e.ctrlKey && !e.altKey && k.path) (e.preventDefault(), k.reject(k.path))
      else if ((e.key === 'c' || e.key === 'C') && !e.metaKey && !e.ctrlKey && !e.altKey && k.path) (e.preventDefault(), k.comment(k.path))
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  const drag = (set: (n: number) => void, axis: 'x' | 'y', store?: string) => (down: React.MouseEvent) => {
    const box = (down.currentTarget.parentElement as HTMLElement).getBoundingClientRect()
    document.body.classList.add('dragging')
    const move = (e: MouseEvent) => {
      const pct = axis === 'x' ? ((e.clientX - box.left) / box.width) * 100 : ((box.bottom - e.clientY) / box.height) * 100
      const clamped = Math.min(80, Math.max(20, pct))
      set(clamped)
      if (store) localStorage.setItem(store, String(Math.round(clamped)))
    }
    const up = () => (document.body.classList.remove('dragging'), window.removeEventListener('mousemove', move), window.removeEventListener('mouseup', up))
    window.addEventListener('mousemove', move)
    window.addEventListener('mouseup', up)
  }

  if (error) return <div className="fatal">{error}</div>
  if (!base) return <div className="fatal muted">Loading…</div>

  const slotLabel = entry ? base.teaching.slots[entry.slot]?.label ?? path! : ''
  const position = path ? stops.indexOf(path) : -1
  const owner = ready?.provenance['/ceterms:ownedBy']?.evidence.find((e) => e.kind === 'record')
  const organisation = owner?.address ? { name: String(owner.fields?.find((f) => f.path === 'ceterms:name')?.value ?? 'Organization'), address: owner.address } : null
  const courseReviews = ready ? reviews.all[ready.id] ?? {} : {}

  return (
    <GlossaryContext.Provider value={setTerm}>
      <div className="app">
        <header className="topbar">
          <IconButton name="sidebar" title={sidebar ? 'Hide the list of courses' : 'Show the list of courses'} on={sidebar} onClick={toggleSidebar} />
          <span className="brand">xTRA Review</span>
          <IconButton name="left" title="Previous course (Shift+Enter)" onClick={() => openCourse(-1)} disabled={index <= 0} />
          <span className="title">{row ? `${row.code} · ${row.name}` : ''}</span>
          <IconButton name="right" title="Next course (Enter)" onClick={() => openCourse(1)} disabled={index >= base.courses.length - 1} />
          <span className="faint">{index + 1} of {base.courses.length}</span>
          <span className="sp" />
          <button className="btn" onClick={() => setTour(true)}>Show the tour</button>
        </header>

        <div className="main">
          <Sidebar
            hidden={!sidebar && !tour}
            courses={base.courses}
            docs={base.docs}
            current={courseId}
            reviews={reviews.all}
            organisation={organisation}
            onOpen={(id) => go({ course: id, stop: null }, true)}
          />
          {ready && (
            <div className="cols">
            <div style={{ width: `${split}%` }} className="col">
              <div className="pane record">
                <div className="ph">
                  <h2>CTDL record</h2>
                  <button className="typelink mono" title="What CTDL says this kind of record is" onClick={() => define(String(ready.record['@type']))}>{String(ready.record['@type'])}</button>
                  <span className="sp" />
                  <Segmented value={route.view} onChange={(view) => go({ view })} options={[['fields', 'Pretty'], ['json', 'Raw']]} />
                </div>
                {route.view === 'fields' ? (
                  <Fields
                    course={ready}
                    teaching={base.teaching}
                    rules={base.rules}
                    forms={base.forms}
                    courses={base.courses}
                    docs={base.docs}
                    path={path}
                    stops={stops}
                    level={route.level}
                    setLevel={(level) => go({ level })}
                    reasoning={reasoning}
                    setReasoning={setReasoning}
                    reviews={courseReviews}
                    onSelect={select}
                    onLocate={locate}
                    onFlip={flip}
                    onTerm={define}
                    onReject={reject}
                    onComment={comment}
                    onReview={review}
                    onHover={setHover}
                  />
                ) : (
                  <div className="stack">
                    <div className="jsontools">
                      <IconButton name="unfold" title={unfoldAll ? 'Fold everything' : 'Unfold all: the record exactly as written to disk'} on={unfoldAll} onClick={() => setUnfoldAll(!unfoldAll)} />
                      <IconButton
                        name={copied ? 'check' : 'copy'}
                        title="Copy the record exactly as written to disk"
                        onClick={() => navigator.clipboard?.writeText(JSON.stringify(ready.record, null, 2)).then(() => (setCopied(true), setTimeout(() => setCopied(false), 1200)))}
                      />
                    </div>
                    <JsonView
                      course={ready}
                      lines={lines}
                      path={path}
                      exact={unfoldAll}
                      onSelect={select}
                      onLocate={locate}
                      onFlip={flip}
                      onTerm={define}
                      onFold={(p) => setUnfolded((old) => {
                        const next = new Set(old)
                        if (next.has(p)) next.delete(p)
                        else next.add(p)
                        return next
                      })}
                    />
                    {entry && path && (
                      <>
                        <div className="divider y" onMouseDown={drag(setWhySplit, 'y')} />
                        <div className="whybox" style={{ height: `${whySplit}%` }}>
                          <div className="ph">
                            <h2>Why this value</h2>
                            <span className="mono">{path.split('/').pop()}</span>
                            <span className="muted clip">{display(valueAt(ready.record, path), entry)}</span>
                            <span className="sp" />
                            <IconButton name="close" title="Close (Esc)" onClick={() => select(null)} />
                          </div>
                          <Why course={ready} path={path} entry={entry} teaching={base.teaching} rules={base.rules} docs={base.docs} level={route.level} setLevel={(level) => go({ level })} onHover={setHover} onLocate={(hint) => locate(path, hint)} />
                        </div>
                      </>
                    )}
                    {!path && <div className="empty">Click a value, or press <kbd>Tab</kbd>, to see where it came from.</div>}
                  </div>
                )}
                {noting && ready?.provenance[noting.path] && (
                  <NoteBox
                    key={noting.path + noting.mode}
                    mode={noting.mode}
                    label={base.teaching.slots[ready.provenance[noting.path].slot]?.label ?? noting.path}
                    text={courseReviews[noting.path]?.comment ?? ''}
                    rejected={!!courseReviews[noting.path]?.rejected}
                    onSave={(text) => (review(noting.path, (r) => (noting.mode === 'reject' ? rejectWith(r, text) : { ...r, comment: text || undefined })), setNoting(null))}
                    onCancel={() => setNoting(null)}
                    onUndo={() => (review(noting.path, unreject), setNoting(null))}
                  />
                )}
              </div>
            </div>
              <div className="divider x" onMouseDown={drag(setSplit, 'x', 'xtra-record-width')} />
            <div className="col grow">
              <SourcePane
                course={ready}
                docs={base.docs}
                path={path}
                entry={entry}
                label={slotLabel}
                stops={topLevelStops(ready)}
                review={path ? courseReviews[path] : undefined}
                hover={hover}
                jump={jump}
                forms={base.forms}
                defined={defined}
                onDefine={setDefined}
                onFollow={(t) => setTrail((old) => [...old, t])}
                onBack={trail.length > 1 ? () => setTrail((old) => old.slice(0, -1)) : undefined}
                onSelect={select}
                onAttribute={(s) => path && review(path, (r) => ({ ...r, segments: [...(r.segments ?? []), s] }))}
              />
            </div>
            </div>
          )}
        </div>

        <footer className="foot">
          <span><kbd>Tab</kbd> next stop</span>
          <span><kbd>⇧ Tab</kbd> back</span>
          <span><kbd>A</kbd> accept</span>
          <span><kbd>R</kbd> reject</span>
          <span><kbd>C</kbd> comment</span>
          <span><kbd>Enter</kbd> next course</span>
          <span className="sp" />
          {finished ? (
            <b>{stops.length ? 'That was the last stop of this course.' : 'No stops here in this setting.'} Press Enter for the next course.</b>
          ) : (
            position >= 0 && <span>Stop {position + 1} of {stops.length}</span>
          )}
          <span>Walk through</span>
          <Segmented small value={route.walk} onChange={(walk) => (setFinished(false), go({ walk }))} options={[['everything', `Everything · ${everyStop.length}`], ['judgement', `Judgement calls · ${judgement.length}`]]} />
        </footer>

        {term && (
          <div className="pop gloss-pop" onMouseLeave={() => setTerm(null)}>
            {base.teaching.glossary.filter((g) => g.term === term).map((g) => (
              <div key={g.term}><div className="lbl">{g.term}</div><p><Rich text={g.text} /></p><p className="muted">Example: <Rich text={g.example} /></p></div>
            ))}
          </div>
        )}
        {tour && ready && <Tour onStep={tourStep} onClose={() => (setTour(false), setTrail([]), setReasoning(false))} />}
      </div>
    </GlossaryContext.Provider>
  )
}

function valueAt(record: unknown, path: string): unknown {
  return path.split('/').slice(1).reduce<unknown>((v, k) => (v as Record<string, unknown> | undefined)?.[k], record)
}
