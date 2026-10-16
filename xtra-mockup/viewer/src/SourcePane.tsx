import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { loadDocumentText, loadParsed } from './data'
import { buildIndex, clearMarks, elementAt, excerpt, offsetOf, resolve, wrap } from './highlight'
import { Badge, Icon, IconButton, Segmented } from './Rich'
import { TermInfo, termAddress, termLabel } from './TermInfo'
import type { Course, DocMeta, Entry, Evidence, Forms, Review } from './types'
import type { Hover, Jump } from './Why'

type Props = {
  course: Course
  docs: Record<string, DocMeta>
  path: string | null
  entry: Entry | null
  label: string
  stops: string[]
  review: Review | undefined
  hover: Hover
  jump: Jump
  forms: Forms
  defined: string | null
  onDefine: (term: string | null) => void
  onFollow: (term: string) => void
  onBack?: () => void
  onSelect: (path: string) => void
  onAttribute: (s: { document: string; start: number; end: number; quote: string }) => void
}

// Styles put inside the stored page. The first block is the bundled fallback (decision D13): it
// sits before the live site's stylesheets, so it only shows through when those cannot be loaded.
const FALLBACK = `
html{font:15px/1.55 Roboto,Helvetica,Arial,sans-serif;color:#222;background:#fff}
body{margin:0;padding:18px 26px} h1{font-size:26px;font-weight:500;color:#9d2235}
h3{font-size:18px;border-bottom:1px solid #ddd;padding-bottom:4px}
a{color:#9d2235} .courseblock{margin:0 0 14px} .courseblocktitle{font-weight:700;margin:0 0 2px}
.courseblockdesc{margin:0} .sr-only,.accessible{position:absolute;left:-9999px}
`
const OURS = `
.tab_content{display:block !important}
nav.accessible,.accessible-menu{display:none !important}
body.xtra-dim .courseblock{opacity:.38;transition:opacity .15s}
body.xtra-dim .courseblock.xtra-current{opacity:1}
[data-xtra]{border-radius:2px;-webkit-box-decoration-break:clone;box-decoration-break:clone;cursor:pointer;color:inherit}
.xh1{background:#ffe08a;box-shadow:0 0 0 1px #b8860b}
.xh2{background:#a8e6d9;box-shadow:0 0 0 1px #0f766e}
.xh3{background:#d9c8ff;box-shadow:0 0 0 1px #6d3fd1}
.xh-first[data-n]::before{content:attr(data-n);display:inline-block;min-width:15px;height:15px;margin-right:3px;border-radius:8px;
  font:700 10px/15px -apple-system,Helvetica,Arial,sans-serif;text-align:center;color:#fff;vertical-align:2px;text-indent:0}
.xh1.xh-first::before{background:#b8860b}.xh2.xh-first::before{background:#0f766e}.xh3.xh-first::before{background:#6d3fd1}
.xh-soft{background:#fff6d6}
.xh-human{background:#cfe3ff;box-shadow:0 0 0 1.5px #2a6fdb}
.xh-human.xh-first::before{content:"you";background:#2a6fdb;padding:0 4px;min-width:0;display:inline-block;height:15px;margin-right:3px;border-radius:8px;
  font:700 10px/15px -apple-system,Helvetica,Arial,sans-serif;color:#fff;vertical-align:2px}
@keyframes xtra-flash{0%,60%{outline:3px solid #3b4cca;outline-offset:3px}100%{outline:3px solid transparent;outline-offset:8px}}
.xh-flash{animation:xtra-flash 1.1s ease-out}
.xh-hover{background:#3b4cca !important;color:#fff !important;box-shadow:0 0 0 2px #3b4cca}
body.xtra-pick ::selection{background:#9cc2ff}
body.xtra-pick .courseblock.xtra-current{cursor:text}
`

const PAGE_WIDTH = 1120
const withDoc = (e: Evidence) => !!e.document && e.kind !== 'none'
const tidy = (s: string) => s.replace(/\s+/g, ' ').trim()
/** The piece of evidence a click asked for: by its number, or by the words it quotes. */
const wanted = (evidence: Evidence[], jump: Jump) =>
  jump.n ? evidence.find((e) => e.n === jump.n && withDoc(e)) : jump.quote ? evidence.find((e) => withDoc(e) && e.segments?.some((s) => tidy(s.quote) === tidy(jump.quote!))) : undefined

export function SourcePane({ course, docs, path, entry, label, stops, review, hover, jump, forms, defined, onDefine, onFollow, onBack, onSelect, onAttribute }: Props) {
  const main = course.block.document
  // The entries of CTDL's fixed lists that this record picked, to mark them on the definition pages.
  const used = useMemo(() => [...JSON.stringify(course.record).matchAll(/"ceterms:targetNode":"([^"]+)"/g)].map((m) => m[1]), [course])
  const [active, setActive] = useState(main)
  const [userView, setUserView] = useState<'page' | 'html'>('page')
  const [override, setOverride] = useState<'page' | 'html' | null>(null)
  const [info, setInfo] = useState(false)
  const [loaded, setLoaded] = useState(0)
  const [warnings, setWarnings] = useState<string[]>([])
  const frame = useRef<HTMLIFrameElement>(null)
  const viewport = useRef<HTMLDivElement>(null)
  const [scale, setScale] = useState(1)
  useEffect(() => {
    // The stored page is laid out at a desktop width and scaled to fit, as a browser window would show it.
    const el = viewport.current
    if (!el) return
    const fit = () => setScale(Math.min(1, Math.max(0.55, el.clientWidth / PAGE_WIDTH)))
    fit()
    const observer = new ResizeObserver(fit)
    observer.observe(el)
    return () => observer.disconnect()
  }, [])
  const scrolled = useRef('')
  const settling = useRef<ResizeObserver | null>(null)
  const latest = useRef({ path, stops, course, active, onSelect, onAttribute })
  latest.current = { path, stops, course, active, onSelect, onAttribute }

  const meta = docs[active] ?? docs[main]
  const evidence = entry?.evidence ?? []
  const here = evidence.filter((e) => e.document === meta.digest)
  const markupOnly = here.length > 0 && here.every((e) => e.kind === 'markup')
  const view = meta.kind === 'record' ? 'page' : override ?? (markupOnly ? 'html' : userView)

  // Moving to another stop shows the document its first piece of evidence is in (SP3).
  useEffect(() => {
    setOverride(null)
    const first = wanted(evidence, jump) ?? evidence.find(withDoc)
    setActive(first?.document && docs[first.document] ? first.document : main)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [path, course.id, jump.tick])

  // --- the stored page, in a frame of its own so its styles cannot touch the viewer (SP2) ------
  const onLoad = () => {
    const doc = frame.current?.contentDocument
    if (!doc?.head) return
    const fallback = doc.createElement('style')
    fallback.textContent = FALLBACK
    doc.head.insertBefore(fallback, doc.head.firstChild)
    const ours = doc.createElement('style')
    ours.textContent = OURS
    doc.head.appendChild(ours)
    doc.addEventListener('click', (e) => {
      e.preventDefault() // links in the stored page never navigate the viewer
      const sel = doc.getSelection()
      if (sel && !sel.isCollapsed) return
      const target = e.target as HTMLElement
      const marked = target.closest?.('[data-path]') as HTMLElement | null
      if (marked?.dataset.path) return latest.current.onSelect(marked.dataset.path)
      const range = doc.caretRangeFromPoint?.(e.clientX, e.clientY)
      const at = range ? offsetOf(doc, range.startContainer, range.startOffset) : null
      if (at === null) return
      const found = stopAt(latest.current.course, latest.current.stops, latest.current.active, at)
      if (found) latest.current.onSelect(found)
    })
    doc.addEventListener('mouseup', () => {
      const sel = doc.getSelection()
      if (!sel || sel.isCollapsed || !sel.rangeCount || !latest.current.path) return
      const range = sel.getRangeAt(0)
      const start = offsetOf(doc, range.startContainer, range.startOffset)
      const end = offsetOf(doc, range.endContainer, range.endOffset)
      if (start === null || end === null || end <= start) return
      const quote = buildIndex(doc).text.slice(start, end)
      sel.removeAllRanges()
      if (quote.trim()) latest.current.onAttribute({ document: latest.current.active, start, end, quote })
    })
    doc.addEventListener('keydown', (e) => {
      // Keys pressed while the page has focus still drive the walk.
      window.dispatchEvent(new KeyboardEvent('keydown', { key: e.key, shiftKey: e.shiftKey, bubbles: true }))
      if (['Tab', 'Enter'].includes(e.key)) e.preventDefault()
    })
    setLoaded((n) => n + 1)
  }

  useEffect(() => {
    const doc = frame.current?.contentDocument
    if (!doc?.body || view !== 'page' || meta.kind !== 'page') return
    settling.current?.disconnect()
    clearMarks(doc)
    const notes: string[] = []
    const text = buildIndex(doc).text
    if (meta.textLength !== undefined && text.length !== meta.textLength) {
      notes.push('This browser reads the stored page differently from the extract step, so positions are being re-found from their quotes.')
    }
    doc.body.classList.toggle('xtra-pick', !!path)
    doc.querySelectorAll('.xtra-current').forEach((el) => el.classList.remove('xtra-current'))
    let block: Element | null = null
    if (meta.digest === course.block.document) {
      block = elementAt(doc, course.block.start + 1)?.closest('.courseblock') ?? null
      block?.classList.add('xtra-current')
    }
    doc.body.classList.toggle('xtra-dim', !!block) // other courses on the page are dimmed (SP4)

    type Mark = { start: number; end: number; cls: string; data: Record<string, string> }
    const marks: Mark[] = []
    for (const e of here) {
      for (const s of e.segments ?? []) {
        const r = resolve(text, s)
        if (r.state === 'stale') notes.push(`The stored position for “${s.quote.slice(0, 40)}” no longer holds that text, and the quote was not found. Nothing is highlighted for it.`)
        else {
          if (r.state === 're-found') notes.push(`“${s.quote.slice(0, 40)}” was not at its stored position; it was found again by its quote.`)
          marks.push({ start: r.start, end: r.end, cls: `xh xh${((e.n - 1) % 3) + 1}`, data: { n: String(e.n), path: path ?? '' } })
        }
      }
    }
    for (const s of review?.segments ?? []) {
      if (s.document === meta.digest) marks.push({ start: s.start, end: s.end, cls: 'xh xh-human', data: { path: path ?? '' } })
    }
    if (hover && hover.document === meta.digest) marks.push({ start: hover.start, end: hover.end, cls: 'xh-hover', data: {} })
    // Longest first, so that a link inside a sentence is wrapped inside the sentence's mark.
    marks.sort((a, b) => b.end - b.start - (a.end - a.start) || a.start - b.start)
    const numbered = new Set<string>()
    const asked = wanted(here, jump)
    const askedAt = asked?.segments?.find((s) => jump.quote && tidy(s.quote) === tidy(jump.quote)) ?? asked?.segments?.[0]
    let askedMark: HTMLElement[] = []
    let firstMark: HTMLElement | null = null
    for (const m of marks) {
      const data = { ...m.data }
      if (data.n && numbered.has(m.cls)) delete data.n // one number per piece of evidence
      const made = wrap(doc, m.start, m.end, m.cls, data)
      if (made.length && data.n) numbered.add(m.cls)
      if (askedAt && asked && m.data.n === String(asked.n) && !askedMark.length && resolve(text, askedAt).start === m.start) askedMark = made
      if (made.length && m.cls.startsWith('xh xh') && (!firstMark || made[0].compareDocumentPosition(firstMark) & Node.DOCUMENT_POSITION_FOLLOWING)) firstMark = made[0]
    }
    setWarnings(notes)
    const key = `${course.id}|${path}|${meta.digest}|${loaded}|${jump.tick}`
    if (askedMark.length) firstMark = askedMark[0]
    if (scrolled.current !== key) {
      scrolled.current = key
      const win = doc.defaultView
      const mark = firstMark
      const bring = () => {
        if (mark?.isConnected) mark.scrollIntoView({ block: 'center', behavior: 'auto' })
        // On arrival: the course's block, a little below the top so the site's own fixed header does not cover it.
        else if (!mark && !path && block && win) win.scrollTo(0, block.getBoundingClientRect().top + win.scrollY - win.innerHeight * 0.3)
      }
      bring()
      // The live site's styles can arrive after the stored page does and move everything; follow for a moment.
      if (win && 'ResizeObserver' in win) {
        const observer = new ResizeObserver(bring)
        observer.observe(doc.body)
        settling.current = observer
        setTimeout(() => observer.disconnect(), 1500)
      }
      // A click on a value asked for this place: flash it, so the eye finds it.
      if (jump.tick && firstMark) for (const el of askedMark.length ? askedMark : [firstMark]) el.classList.add('xh-flash')
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [loaded, path, entry, hover, review, view, meta.digest, course.id, jump.tick])

  const numbers = (digest: string) => evidence.filter((e) => e.document === digest).map((e) => e.n)
  const addressEvidence = here.find((e) => e.kind === 'address')
  const elsewhere = evidence.filter((e) => withDoc(e) && e.document !== meta.digest)

  return (
    <div className="pane source">
      <div className="browser">
        <div className="tabs">
          <span className="lights"><i /><i /><i /></span>
          {/* One row naming every document this course drew on, always complete (DC1). */}
          {course.documents.map((d) => (
            <button key={d} className={'tab' + (d === meta.digest && !defined ? ' on' : '')} onClick={() => (setActive(d), setOverride(null), onDefine(null))}>
              {numbers(d).map((n) => <Badge key={n} n={n} />)}
              {docs[d]?.name ?? d.slice(0, 8)}
            </button>
          ))}
          {defined && (
            <span className="tab on info">
              <Icon name="info" size={13} /> {termLabel(defined, forms)}
              <button className="tab-x" title="Close (Esc)" onClick={() => onDefine(null)}><Icon name="close" size={11} /></button>
            </span>
          )}
        </div>
        {/* Laid over the page, not in place of it, so the page keeps its place for when the pointer moves on. */}
        {defined && (
          <div className="definition">
            <div className="bar">
              <IconButton name="left" title="Back" disabled={!onBack} onClick={() => onBack?.()} />
              {/^https?:/.test(termAddress(defined, forms)) ? (
                <a className="address mono" href={termAddress(defined, forms)} target="_blank" rel="noreferrer" title="Open the live page in a new tab">{termAddress(defined, forms)}</a>
              ) : (
                <div className="address mono">{termAddress(defined, forms)}</div>
              )}
            </div>
            <TermInfo key={defined} term={defined} forms={forms} used={used} onFollow={onFollow} />
          </div>
        )}
        <div className="bar">
          <div className={'address mono' + (addressEvidence ? ' hit' : '')} title={meta.finalAddress}>
            {addressEvidence && <Badge n={addressEvidence.n} />}
            {meta.finalAddress}
          </div>
          {meta.kind === 'page' && (
            <Segmented small value={view} onChange={(v) => (setUserView(v), setOverride(v))} options={[['page', 'Page'], ['html', 'HTML']]} />
          )}
          <IconButton name="info" title="About this document" on={info} onClick={() => setInfo(!info)} />
        </div>
        {info && <DocInfo meta={meta} code={course.code} onClose={() => setInfo(false)} />}
        {path && (
          <div className="strip">
            <b>{label}</b>
            {entry && entry.evidence.every((e) => e.kind === 'none') ? <span> — this value has no source on any page.</span> : null}
            {meta.kind === 'page' && view === 'page' && <span className="hint"> — drag across the page to attribute different text to it.</span>}
            {markupOnly && view === 'html' && <span> — its evidence is markup, which the rendered page cannot show, so this is the HTML view.</span>}
          </div>
        )}
        {warnings.map((w, i) => <div key={i} className="strip warn">{w}</div>)}
        <div className="viewport" ref={viewport}>
          {meta.kind === 'record' ? (
            <RecordDoc tick={jump.tick} meta={meta} fields={here.flatMap((e) => (e.fields ?? []).map((f) => ({ key: f.path, n: e.n })))} />
          ) : (
            <>
              <iframe key={meta.digest} ref={frame} src={`data/${meta.file}`} sandbox="allow-same-origin" title={meta.name} onLoad={onLoad} style={{ display: view === 'page' ? 'block' : 'none', width: `${100 / scale}%`, height: `${100 / scale}%`, transform: `scale(${scale})` }} />
              {view === 'html' && <HtmlTree key={meta.digest + path} tick={jump.tick} meta={meta} evidence={here} />}
            </>
          )}
        </div>
      </div>
      {/* Evidence on another document: a short excerpt beneath, never a second full preview (DC4, DC5). */}
      {elsewhere.slice(0, 2).map((e) => <Excerpt key={e.n} e={e} meta={docs[e.document!]} onOpen={() => (setActive(e.document!), setOverride(null))} />)}
      {elsewhere.length > 2 && <div className="peek more-docs">{elsewhere.length - 2} more in the tabs above</div>}
    </div>
  )
}

/** The stop whose evidence most narrowly covers a place on the page (SP5: the link works both ways). */
function stopAt(course: Course, stops: string[], document: string, at: number): string | null {
  let best: { path: string; size: number } | null = null
  for (const p of stops) {
    for (const e of course.provenance[p]?.evidence ?? []) {
      if (e.document !== document) continue
      for (const s of e.segments ?? []) {
        if (at >= s.start && at <= s.end && (!best || s.end - s.start < best.size)) best = { path: p, size: s.end - s.start }
      }
    }
  }
  return best?.path ?? null
}

function DocInfo({ meta, code, onClose }: { meta: DocMeta; code: string; onClose: () => void }) {
  return (
    <div className="pop" onMouseLeave={onClose}>
      <div className="lbl">{meta.name} · the stored copy</div>
      <div className="kv">
        <span>Address</span><span className="mono">{meta.finalAddress}</span>
        <span>Fetched</span><span>{meta.fetchedAt.replace('T', ' ').replace('+00:00', ' UTC')} · HTTP {meta.status}</span>
        <span>Size</span><span>{meta.size.toLocaleString()} bytes · {meta.contentType}</span>
        <span>Digest</span><span className="mono wrap">sha256 {meta.digest}</span>
        {!meta.current && <><span>Note</span><span className="warn">A newer copy of this address is in the page store. Evidence tied to this one needs re-checking.</span></>}
      </div>
      <p>
        <a href={meta.finalAddress} target="_blank" rel="noreferrer">Open the live page ↗</a>
        {meta.role === 'subject' && <> · <a href={`https://catalog.uark.edu/search/?P=${encodeURIComponent(code)}`} target="_blank" rel="noreferrer">This course alone ↗</a></>}
      </p>
      <p className="faint">What you see here is the stored copy, with scripts removed. Links to the live site are a convenience; the stored copy is the evidence.</p>
    </div>
  )
}

function RecordDoc({ meta, fields, tick }: { meta: DocMeta; fields: { key: string; n: number }[]; tick: number }) {
  const [text, setText] = useState('')
  const first = useRef<HTMLDivElement>(null)
  useEffect(() => {
    loadDocumentText(meta).then((raw) => {
      try {
        setText(JSON.stringify(JSON.parse(raw), null, 2))
      } catch {
        setText(raw)
      }
    })
  }, [meta])
  useEffect(() => {
    first.current?.scrollIntoView({ block: 'center' })
  }, [text, fields.length, tick])
  let seen = false
  return (
    <div className="recorddoc mono">
      {text.split('\n').map((line, i) => {
        const hit = fields.find((f) => line.startsWith(`  ${JSON.stringify(f.key)}:`))
        const ref = hit && !seen ? ((seen = true), first) : undefined
        return (
          <div key={i} ref={ref} className={hit ? 'hit' : ''}>
            {hit && <Badge n={hit.n} />}
            {line || ' '}
          </div>
        )
      })}
    </div>
  )
}

function Excerpt({ e, meta, onOpen }: { e: Evidence; meta: DocMeta; onOpen: () => void }) {
  const [body, setBody] = useState<ReactNode>(null)
  useEffect(() => {
    let live = true
    if (e.kind === 'text' && e.segments?.length && meta.kind === 'page') {
      loadParsed(meta).then((doc) => {
        if (!live) return
        const text = buildIndex(doc).text
        const r = resolve(text, e.segments![0])
        if (r.state === 'stale') return setBody(<span className="warn">The quote “{e.segments![0].quote}” was not found in the stored page.</span>)
        const x = excerpt(text, r.start, r.end)
        setBody(<>{x.before}<mark className={`xh${((e.n - 1) % 3) + 1}`}>{x.quote}</mark>{x.after}</>)
      })
    } else setBody(e.says)
    return () => {
      live = false
    }
  }, [e, meta])
  return (
    <div className="peek">
      <div className="pt">
        <Badge n={e.n} /> <b>{meta.name}</b> <span className="faint">{e.role}</span>
        <span className="sp" />
        <button className="linkish" onClick={onOpen}>Open</button>
      </div>
      <div className="pb">{body}</div>
    </div>
  )
}

// --- the HTML view: the stored page as a collapsible tree of elements (HV1 to HV4) -------------

function HtmlTree({ meta, evidence, tick }: { meta: DocMeta; evidence: Evidence[]; tick: number }) {
  const [doc, setDoc] = useState<Document | null>(null)
  const [toggled, setToggled] = useState<Map<Node, boolean>>(new Map())
  const target = useRef<HTMLElement>(null)
  useEffect(() => {
    loadParsed(meta).then(setDoc)
  }, [meta])

  const plan = useMemo(() => {
    if (!doc) return null
    const index = buildIndex(doc)
    const startOf = new Map<Text, number>(index.nodes.map((n, i) => [n, index.starts[i]]))
    const open = new Set<Node>()
    const textHits: { start: number; end: number; n: number }[] = []
    const attrHits = new Map<Element, { attribute: string | null; n: number }>()
    const expose = (node: Node | null) => {
      for (let p = node?.parentNode; p; p = p.parentNode) open.add(p)
    }
    for (const e of evidence) {
      for (const s of e.segments ?? []) {
        const r = resolve(index.text, s)
        if (r.state === 'stale') continue
        textHits.push({ start: r.start, end: r.end, n: e.n })
        index.nodes.forEach((node, i) => {
          if (index.starts[i] < r.end && index.starts[i] + node.data.length > r.start) expose(node)
        })
      }
      if (e.kind === 'markup' && e.element) {
        const el = e.element === 'html' ? doc.documentElement : doc.querySelector(e.element)
        if (el) {
          attrHits.set(el, { attribute: e.attribute ?? null, n: e.n })
          expose(el)
          if (!e.attribute) open.add(el)
        }
      }
    }
    return { startOf, open, textHits, attrHits }
  }, [doc, evidence])

  useEffect(() => {
    target.current?.scrollIntoView({ block: 'center' })
  }, [plan, tick])

  if (!doc || !plan) return <div className="tree" />
  let targetGiven = false
  const giveRef = () => (targetGiven ? undefined : ((targetGiven = true), target))

  const renderText = (node: Text, depth: number): ReactNode => {
    const start = plan.startOf.get(node)
    const data = node.data
    if (!data.trim()) return null
    const hits = start === undefined ? [] : plan.textHits.filter((h) => h.start < start + data.length && h.end > start).sort((a, b) => b.end - b.start - (a.end - a.start))
    const hit = hits[hits.length - 1] // the narrowest piece of evidence on this text
    let body: ReactNode
    if (hit && start !== undefined) {
      const from = Math.max(0, hit.start - start)
      const to = Math.min(data.length, hit.end - start)
      const lead = data.slice(0, from)
      const tail = data.slice(to)
      body = (
        <>
          {lead.length > 80 ? '…' + lead.slice(-80) : lead}
          <mark ref={giveRef()} className={`xh${((hit.n - 1) % 3) + 1}`}>{data.slice(from, to)}</mark>
          {tail.length > 80 ? tail.slice(0, 80) + '…' : tail}
        </>
      )
    } else body = data.trim().length > 140 ? data.trim().slice(0, 140) + '…' : data.trim()
    return <div className="tx" style={{ paddingLeft: depth * 14 + 14 }}>{body}</div>
  }

  const renderElement = (el: Element, depth: number): ReactNode => {
    const kids = [...el.childNodes].filter((n) => n.nodeType === 1 || (n.nodeType === 3 && (n as Text).data.trim()))
    const isOpen = toggled.get(el) ?? true // fully expanded until folded by hand
    const hit = plan.attrHits.get(el)
    const tag = el.tagName.toLowerCase()
    const attrs = [...el.attributes].map((a) => {
      const marked = hit?.attribute === a.name
      const text = <><span className="at"> {a.name}</span>=<span className="v">"{a.value.length > 60 ? a.value.slice(0, 60) + '…' : a.value}"</span></>
      return marked ? <mark key={a.name} ref={giveRef()} className={`xh${((hit!.n - 1) % 3) + 1}`}>{text}</mark> : <span key={a.name}>{text}</span>
    })
    return (
      <div>
        <div className="row" style={{ paddingLeft: depth * 14 }} onClick={() => setToggled(new Map(toggled).set(el, !isOpen))}>
          <span className="tw">{kids.length ? (isOpen ? '▾' : '▸') : ' '}</span>
          <span className={hit && !hit.attribute ? 'elhit' : ''}>
            &lt;<span className="t">{tag}</span>{attrs}&gt;
          </span>
          {!isOpen && kids.length > 0 && <span className="tw"> … &lt;/{tag}&gt;</span>}
        </div>
        {isOpen && kids.map((k, i) => <div key={i}>{k.nodeType === 1 ? renderElement(k as Element, depth + 1) : renderText(k as Text, depth + 1)}</div>)}
      </div>
    )
  }
  return <div className="tree mono">{renderElement(doc.documentElement, 0)}</div>
}
