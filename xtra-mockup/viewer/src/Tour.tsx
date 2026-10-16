import { useEffect, useLayoutEffect, useState, type ReactNode } from 'react'
import { Icon } from './Rich'
import { fill } from './Sidebar'

// A step lights one or more areas. `accent` rings the one small thing to click; `side` says where the
// card goes: beside the first area, or beneath it when a second area must stay in view as well.
// `arrive` sets the screen up for the step, as the reader would by hand; what it returns undoes it.
type Step = { targets: string[]; accent?: string; side: 'right' | 'left' | 'below'; title: string; body: ReactNode; arrive?: () => void | (() => void); demo?: Demo }
// What the screen itself is asked to do for a step: click a value, its coloured edge, or its field's name.
export type Demo = 'source' | 'reasoning' | 'definition'

// The same icon the reader will find on a card, so the tour and the screen use one vocabulary.
const I = ({ name }: { name: string }) => <span className="tour-ico"><Icon name={name} size={14} /></span>

const find = (selector: string) => document.querySelector<HTMLElement>(selector)

const STEPS: Step[] = [
  {
    targets: ['.sidebar'],
    side: 'right',
    title: 'These are the proposed CTDL resources',
    body: (
      <>
        <p>xTRA read the catalog pages and proposed one CTDL record for every course it found. They are listed here by subject.</p>
        <p>Nothing has been published. Each record is a proposal waiting for a person to check it.</p>
        <p>As you review, the list keeps score. A little way in, it looks like this:</p>
        {/* Drawn with the sidebar's own rows, so it is what the reader will see. */}
        <div className="tour-demo" aria-hidden="true">
          <div className="side-subject" style={{ backgroundImage: 'linear-gradient(to right, #cdebd9 38%, transparent 38%)' }}>
            <span className="tw">▾</span><b>ACCT</b><span className="clip muted">Accounting</span><span className="sp" /><span className="faint">2 / 46</span>
          </div>
          <div className="side-row done" style={fill(100)}><span className="mono">20103</span><span className="clip">Accounting Principles</span><span className="mark">✓</span></div>
          <div className="side-row done" style={fill(100)}><span className="mono">201H3</span><span className="clip">Honors Accounting Principles</span><span className="mark no">✗1</span><span className="mark">✓</span></div>
          <div className="side-row on" style={fill(67)}><span className="mono">20203</span><span className="clip">Accounting Principles II</span><span className="mark part">12/18</span></div>
          <div className="side-row"><span className="mono">202H3</span><span className="clip">Honors Accounting Principles II</span></div>
        </div>
        <ul className="tour-key">
          <li><b>The green fill behind a course:</b> how many of its fields are decided. It fills as you go.</li>
          <li><b>✓:</b> every field of that course has been accepted or rejected.</li>
          <li><b className="no">✗1:</b> one of its fields was rejected.</li>
          <li><b>12/18:</b> the count, part way through.</li>
          <li><b>The green fill behind the subject:</b> how much of the whole subject is decided.</li>
        </ul>
      </>
    ),
  },
  {
    targets: ['.pane.record'],
    side: 'right',
    title: 'Field by field, accept or reject xTRA’s proposed value',
    body: (
      <>
        <p>Each card is one field of the record: its name, and the value xTRA proposes for it.</p>
        <div className="tour-legend">
          <span><i style={{ background: 'var(--c-high)' }} /> <b>Green</b> xTRA is confident</span>
          <span><i style={{ background: 'var(--c-medium)' }} /> <b>Amber</b> less sure</span>
          <span><i style={{ background: 'var(--c-low)' }} /> <b>Red</b> look closely</span>
          <span><i style={{ background: '#d5d9e2' }} /> <b>Grey</b> no proposal: xTRA left the field blank</span>
        </div>
        <p>The coloured edge on each card is <b>xTRA’s own confidence in its recommendation</b>, not a verdict. Click the edge to see its reasoning.</p>
        <p>Further down, in grey, is every other field CTDL allows on a course that xTRA proposed nothing for. You can fill one in. A faint red <span className="req" style={{ margin: 0 }}>*</span> marks the fields Credential Engine requires.</p>
        <div className="tour-keys">
          <I name="check" /><kbd>A</kbd><span>Accept the selected field</span>
          <I name="close" /><kbd>R</kbd><span>Reject it, and say why</span>
          <I name="comment" /><kbd>C</kbd><span>Leave a comment and move on</span>
          <I name="edit" /><span /><span>Correct the value in a form</span>
          <I name="info" /><span /><span>See xTRA’s reasoning</span>
          <I name="code" /><kbd>V</kbd><span>See the same field as raw CTDL</span>
          <span /><kbd>Tab</kbd><span>Next field</span>
          <span /><kbd>Enter</kbd><span>Next course</span>
        </div>
        <p className="faint">The icons appear beneath a card when you point at it.</p>
      </>
    ),
  },
  {
    targets: ['.pane.record'],
    side: 'right',
    title: 'Reject with a reason, or just leave a comment',
    body: (
      <>
        <p><I name="close" /> or <kbd>R</kbd> rejects the selected field. <b>A rejection always comes with a reason</b>: a box opens with the cursor already in it, and the field is rejected once you have said why.</p>
        {/* Drawn with the real box and the real card, holding an example reason. */}
        <div className="tour-demo pad" aria-hidden="true">
          <div className="reject-head"><span className="x">✗</span> Reject <b>How often offered</b></div>
          <div className="in tour-typed">The page says Fall, Spring and Summer. That is three terms a year, not four.<i className="tour-caret" /></div>
          <div className="reject-foot"><span className="faint"><kbd>Enter</kbd> reject · <kbd>Esc</kbd> cancel</span></div>
        </div>
        <p>After <kbd>Enter</kbd>, the card carries the verdict and your reason, for whoever reads the review next:</p>
        <div className="tour-demo pad" aria-hidden="true">
          <div className="card-head"><span className="fname">How often offered</span><span className="tag no">rejected</span></div>
          <div className="fvalue tour-struck">Quarterly</div>
          <div className="why-rejected"><span className="x">✗</span> The page says Fall, Spring and Summer. That is three terms a year, not four.</div>
        </div>
        <p>A good reason says what the page shows and what the value should have been. <kbd>R</kbd> again withdraws the rejection.</p>
        <p><I name="comment" /> or <kbd>C</kbd> leaves a comment without a verdict, for when you have something to say but are not rejecting. <b>A comment counts as having dealt with the field</b>, just as accepting or rejecting does.</p>
      </>
    ),
  },
  {
    targets: ['.card.active', '.pane.source'],
    accent: '.card.active .fvalue',
    demo: 'source',
    side: 'below',
    title: 'Click a value to see where it came from',
    body: (
      <>
        <p>“Course name” has been clicked for you. On the right, the page has scrolled to the words xTRA read it from and highlighted them.</p>
        <p>What informed a value is one of three kinds:</p>
        <ul>
          <li><b>Words on the page.</b> Highlighted where they stand, as here.</li>
          <li><b>Something not visible on the page, but in its raw HTML.</b> The view switches to HTML and highlights it there. “Language” is one.</li>
          <li><b>The page’s address.</b> The address bar lights up. “Course web page” is one.</li>
        </ul>
        <p>The tabs name every document the course drew on. A few values, such as the identifier, were made by xTRA and have no source; the card says so.</p>
      </>
    ),
  },
  {
    targets: ['.card.active'],
    accent: '.card.active .confbar',
    demo: 'reasoning',
    side: 'right',
    title: 'Click the coloured edge to see xTRA’s reasoning',
    body: (
      <>
        <p>The edge of “Course name” has been clicked for you. The card has opened to show why xTRA set this value the way it did, always in the same labelled rows:</p>
        <ul>
          <li><b>Confidence.</b> How sure xTRA is, and why.</li>
          <li><b>Source.</b> The words it read. Click one to go to it.</li>
          <li><b>Method.</b> The rule that read them: its name, what it does, its pattern, and what the pattern matched here. Point at the pattern to light the match on the page.</li>
          <li><b>CTDL.</b> Why this field and not another.</li>
        </ul>
        <p>Where a language model was involved, or a check failed, the card says so here, in its own box. The <I name="info" /> icon beneath the card opens the same thing.</p>
      </>
    ),
  },
  {
    targets: ['.card.active', '.pane.source'],
    accent: '.card.active .prop',
    demo: 'definition',
    side: 'below',
    title: 'Click a field’s name to see what it is meant to contain',
    body: (
      <>
        <p><span className="mono">ceterms:name</span> has been clicked for you. On the right is what CTDL says that field is for, in CTDL’s own words: its definition, what kind of value it holds, and where it may be used.</p>
        <p>Use it to judge whether xTRA put the right thing in the right field. Every CTDL name on that page is a link to its own page, and the plain name on the card (“Course name”) opens the same page.</p>
        <p>Click any value to go back to the source.</p>
      </>
    ),
  },
  {
    targets: ['.card.active'],
    accent: '.card.active .choices',
    side: 'right',
    title: 'If a value is wrong, correct it in a form',
    arrive: () => {
      // Open the editor on a field that picks from one of CTDL's fixed lists, as the pencil icon would.
      const card = [...document.querySelectorAll<HTMLElement>('.card')].find((c) => c.querySelector('.prop')?.textContent === 'ceterms:offerFrequencyType')
      card?.querySelector<HTMLElement>('.acts .ico[aria-label="Edit the value"]')?.click()
      setTimeout(() => card?.scrollIntoView({ block: 'center' }), 60)
      return () => [...document.querySelectorAll<HTMLElement>('.card.active .editor .btn')].find((b) => b.textContent === 'Cancel')?.click()
    },
    body: (
      <>
        <p>The pencil <I name="edit" /> on “How often offered” has been clicked for you. There is no code to write: every field opens as a form that fits what CTDL allows in it.</p>
        <p>This field must be picked from one of CTDL’s fixed lists, so the form shows <b>every entry of that list</b>. The one xTRA chose is filled in. Click another to change it; point at any entry to read CTDL’s definition of it.</p>
        <ul>
          <li>Where CTDL allows several, you can pick several.</li>
          <li>Text is a text box. Lists of things are rows you add and remove.</li>
          <li>Links to other courses are found by typing a code or a name.</li>
        </ul>
        <p>Your change is kept in this browser. xTRA’s original proposal is never overwritten, and <I name="undo" /> puts it back.</p>
      </>
    ),
  },
  {
    targets: ['.card.ctid'],
    accent: '.card.ctid .stub-tag',
    side: 'right',
    title: 'The CTID: is the course already in the Registry?',
    arrive: () => {
      find('.fields')?.scrollTo({ top: 0 })
      if (find('.card.ctid .stub-body')) return
      find('.card.ctid .stub-tag')?.click()
      return () => void (find('.card.ctid .stub-body') && find('.card.ctid .stub-tag')?.click())
    },
    body: (
      <>
        <p>The first field of every record is its <b>CTID</b>, the identifier the Credential Registry knows it by. It carries a yellow <b>not built yet</b> mark, which has been clicked for you; the <I name="info" /> on that card opens the same thing.</p>
        <p>The identifier shown is a placeholder. Before a course is proposed as new, someone should check that the Registry does not already hold it, and if it does, this field should show the CTID it already has.</p>
        <p><b>The likely approach</b> depends on the kind of resource. For a course: take its course ID from the catalog and see whether Credential Engine’s Credential Finder database already has a course with that ID from the same organization.</p>
        <p>Until that is built, nothing has been looked up and the two verdict buttons cannot be pressed.</p>
      </>
    ),
  },
  {
    targets: ['.pane.record'],
    accent: '.group-label.fold',
    side: 'right',
    title: 'The fields xTRA left blank',
    arrive: () => {
      if (!find('.card.blank')) find('.group-label.fold')?.click()
      setTimeout(() => find('.group-label.fold')?.scrollIntoView({ block: 'start' }), 60)
      return () => find('.fields')?.scrollTo({ top: 0 })
    },
    body: (
      <>
        <p>CTDL allows many more fields on a course than xTRA found anything for. They are all listed here, below the proposed ones, each with an empty box and a <b>grey edge</b>.</p>
        <p>A blank is not a mistake. It means the catalog page gave xTRA nothing to go on. If you know the answer, click the box and fill it in; the field then says “added by you”.</p>
        <p>Click a blank field’s name to see what CTDL means by it. The heading above the list folds it away.</p>
      </>
    ),
  },
]

type Props = { onStep: (demo: Demo | null) => void; onClose: () => void }

/** The walk through the screen that opens with every page load: what is listed, what to do with it, and where the evidence shows. */
export function Tour({ onStep, onClose }: Props) {
  const [at, setAt] = useState(0)
  const [boxes, setBoxes] = useState<DOMRect[]>([])
  const [accent, setAccent] = useState<DOMRect | null>(null)
  const step = STEPS[at]

  const finish = onClose
  const move = (to: number) => (to >= STEPS.length ? finish() : to >= 0 && setAt(to))

  useEffect(() => {
    onStep(STEPS[at].demo ?? null)
    // After the screen has taken the step in, set up what the step needs to show.
    let undo: void | (() => void)
    const timer = setTimeout(() => (undo = STEPS[at].arrive?.()), 80)
    return () => {
      clearTimeout(timer)
      undo?.()
    }
  }, [at, onStep])

  // The sidebar slides open and the example card is selected a moment later, so the areas are measured
  // again while things settle.
  useLayoutEffect(() => {
    const rect = (selector: string) => document.querySelector(selector)?.getBoundingClientRect() ?? null
    const measure = () => {
      setBoxes(step.targets.map(rect).filter((r): r is DOMRect => !!r && r.width > 0))
      setAccent(step.accent ? rect(step.accent) : null)
    }
    measure()
    const timer = setInterval(measure, 80)
    const stop = setTimeout(() => clearInterval(timer), 1200)
    window.addEventListener('resize', measure)
    return () => (clearInterval(timer), clearTimeout(stop), window.removeEventListener('resize', measure))
  }, [step])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') finish()
      else if (e.key === 'Enter' || e.key === 'ArrowRight') move(at + 1)
      else if (e.key === 'ArrowLeft') move(at - 1)
      else return
      e.preventDefault()
      e.stopPropagation()
    }
    window.addEventListener('keydown', onKey, true)
    return () => window.removeEventListener('keydown', onKey, true)
  })

  const first = boxes[0]
  if (!first) return null
  const width = 360
  const fit = (n: number) => Math.min(Math.max(n, 12), window.innerWidth - width - 12)
  const left = fit(step.side === 'right' ? first.right + 14 : step.side === 'left' ? first.left - width - 14 : first.left + 8)
  const top = Math.min(step.side === 'below' ? first.bottom + 14 : Math.max(first.top + 24, 60), Math.max(60, window.innerHeight - 470))
  return (
    <div className="tour" role="dialog" aria-label="A short tour">
      {/* Everything is dimmed except the areas this step is about. */}
      <svg className="tour-dim" width="100%" height="100%">
        <defs>
          <mask id="tour-holes">
            <rect width="100%" height="100%" fill="#fff" />
            {boxes.map((b, i) => <rect key={i} x={b.left + 2} y={b.top + 2} width={b.width - 4} height={b.height - 4} rx="9" fill="#000" />)}
          </mask>
        </defs>
        <rect width="100%" height="100%" fill="rgba(18, 24, 44, .5)" mask="url(#tour-holes)" />
      </svg>
      {boxes.map((b, i) => <div key={i} className="tour-ring" style={{ left: b.left + 2, top: b.top + 2, width: b.width - 4, height: b.height - 4 }} />)}
      {accent && <div className="tour-accent" style={{ left: accent.left - 4, top: accent.top - 4, width: accent.width + 8, height: accent.height + 8 }} />}
      <div className="tour-card" style={{ left, top, width }}>
        <div className="tour-count">{at + 1} of {STEPS.length}</div>
        <h3>{step.title}</h3>
        {step.body}
        <div className="tour-foot">
          <button className="linkish" onClick={finish}>Skip</button>
          <span className="sp" />
          {at > 0 && <button className="btn" onClick={() => move(at - 1)}>Back</button>}
          <button className="btn primary" autoFocus onClick={() => move(at + 1)}>{at === STEPS.length - 1 ? 'Start reviewing' : 'Next'}</button>
        </div>
      </div>
    </div>
  )
}
