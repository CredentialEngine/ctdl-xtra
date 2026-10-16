import { useState, type ReactNode } from 'react'
import { Badge, Rich, Segmented, Sign } from './Rich'
import { textFragment } from './highlight'
import { RuleCard, TableCard } from './RuleCard'
import type { Check, Course, DocMeta, Entry, Level, Rules, Segment, Structure, Teaching, TreeNode } from './types'

export type Hover = { document: string; start: number; end: number } | null
/** A request to bring a piece of evidence into view: by its number, or by the words it quotes. */
export type Jump = { tick: number; n?: number; quote?: string }

/** Was this value read from a stored document, so that there is a place to go to? */
export const fromSource = (entry: Entry | undefined) => !!entry?.evidence.some((e) => e.document && e.kind !== 'none' && e.kind !== 'derived')
export const CONFIDENCE = { low: 'Low confidence', medium: 'Medium confidence', high: 'High confidence' } as const

/** A check is a rule; when it fails, its detail is what was found instead. */
export function Failed({ check }: { check: Check }) {
  const [, rule, aside] = check.text.match(/^(.*?)(?:\s*\(([^()]*)\))?\s*$/s) ?? [null, check.text, undefined]
  // Each finding names the entries at fault, one to a line.
  const found = (Array.isArray(check.detail) ? check.detail : (check.detail ?? '').split('\n')).filter(Boolean)
  return (
    <div className="failed">
      <div className="failed-head">
        <span className="x">✗</span> Check failed{check.id && <code>{check.id}</code>}
        {aside && <span className="faint">{aside.replace(/\.$/, '')}</span>}
      </div>
      <div className="failed-grid">
        <span>Rule</span><span>{rule}</span>
        {found.length > 0 && (
          <>
            <span>Found</span>
            <span className="found">{found.length === 1 ? found[0] : <ul>{found.map((f) => <li key={f}>{f}</li>)}</ul>}</span>
          </>
        )}
      </div>
    </div>
  )
}

type Props = {
  course: Course
  path: string
  entry: Entry
  teaching: Teaching
  rules: Rules
  docs: Record<string, DocMeta>
  level: Level
  setLevel: (l: Level) => void
  onHover: (h: Hover) => void
  onLocate?: (hint: Omit<Jump, 'tick'>) => void
}

const SECTIONS: { id: string; title: string; from: Level }[] = [
  { id: 'ctdl', title: 'What CTDL says', from: 'standard' },
  { id: 'alternatives', title: 'Alternatives', from: 'standard' },
  { id: 'found', title: 'How it was found', from: 'full' },
  { id: 'evidence', title: 'Evidence, in full', from: 'full' },
  { id: 'checks', title: 'Checks', from: 'full' },
]
const RANK: Record<Level, number> = { brief: 0, standard: 1, full: 2 }
const local = (term: string) => term.split(':')[1] ?? term

export function checkCount(checks: Check[]): string {
  const pass = checks.filter((c) => c.status === 'pass').length
  const fail = checks.filter((c) => c.status === 'fail').length
  const note = checks.filter((c) => c.status === 'note').length
  return [`${pass} ✓`, fail ? `${fail} did not pass` : '', note ? `${note} to know about` : ''].filter(Boolean).join(' · ')
}

/** The reasoning behind one value: Value and Choice always, deeper sections on request (section 9.5). */
export function Why({ course, path, entry, teaching, rules, docs, level, setLevel, onHover, onLocate }: Props) {
  const slot = teaching.slots[entry.slot]
  // A section opened or closed by hand stays that way, whatever the level (PD3).
  const [byHand, setByHand] = useState<Record<string, boolean>>({})
  const isOpen = (id: string, from: Level) => byHand[id] ?? RANK[level] >= RANK[from]
  const toggle = (id: string, from: Level) => setByHand((old) => ({ ...old, [id]: !isOpen(id, from) }))
  const failed = entry.checks.filter((c) => c.status === 'fail')
  const mainDoc = course.block.document
  const usedRules = [...new Set(entry.evidence.map((e) => e.rule))].flatMap((name) => rules.rules.find((r) => r.name === name) ?? [])
  const usedTable = rules.tables.find((t) => entry.evidence.some((e) => e.table === t.name))
  const sections = SECTIONS.filter((s) => {
    if (s.id === 'ctdl') return !!slot?.ctdl
    if (s.id === 'alternatives') return !!slot?.alternatives.length
    if (s.id === 'evidence') return entry.evidence.some((e) => e.kind !== 'none')
    if (s.id === 'checks') return entry.checks.length > 0
    // Rules and tables are set out under Method; this section is for what they do not cover.
    if (s.id === 'found') return !!entry.structure || !entry.evidence.some((e) => e.rule || e.table)
    return true
  })

  return (
    <div className="why">
      <div className="why-top">
        <span className={`level ${entry.confidence.level}`}>{CONFIDENCE[entry.confidence.level]}</span>
        <span className="muted">{entry.confidence.why}</span>
        <span className="sp" />
        <Segmented small value={level} onChange={(l) => (setByHand({}), setLevel(l))} options={[['brief', 'Brief'], ['standard', 'Standard'], ['full', 'Full']]} />
      </div>

      <div className="q2">
        <div className="lab">Source</div>
        <div>
          {entry.evidence.map((e) =>
            e.document && e.kind !== 'none' && onLocate ? (
              <button key={e.n} className="evrow" title="Show this on the page" onClick={() => onLocate({ n: e.n })}>
                <Badge n={e.n} />
                <span>
                  {e.says}
                  {e.document !== mainDoc && <span className="faint"> ({docs[e.document]?.name})</span>}
                </span>
              </button>
            ) : (
              <div key={e.n} className="evrow">
                {e.kind !== 'none' ? <Badge n={e.n} /> : <span className="n none">–</span>}
                <span>{e.says}</span>
              </div>
            ),
          )}
          {entry.evidence.filter((e) => e.kind === 'derived').map((e) => (
            <div key={e.n} className="chain">
              <div className="step">{e.from}</div>
              <div className="arrow">↓ {e.step}</div>
              <div className="step">{e.result}</div>
            </div>
          ))}
          {entry.evidence.filter((e) => e.kind === 'record').map((e) => (
            <div key={e.n} className="kv">
              {e.fields?.map((f) => [<span key={f.path + 'k'}>{f.path}</span>, <span key={f.path + 'v'} className="mono">{String(f.value)}</span>])}
            </div>
          ))}
        </div>

        <div className="lab">Method</div>
        <div>
          <p>{entry.how}</p>
          {entry.normalised && <p className="muted">{entry.normalised}</p>}
          {usedRules.map((r) => <RuleCard key={r.name} rule={r} evidence={entry.evidence.filter((e) => e.rule === r.name)} onHover={onHover} onLocate={onLocate} />)}
          {usedTable && <TableCard table={usedTable} evidence={entry.evidence.find((e) => e.table === usedTable.name)!} />}
        </div>

        {entry.structure?.some((s) => s.languageModel) && (
          <>
            <div className="lab lm">Language model</div>
            <div>{entry.structure.map((s, i) => <ModelOutput key={i} s={s} document={mainDoc} onHover={onHover} />)}</div>
          </>
        )}

        {entry.structure?.some((s) => s.tree && s.builtBy === 'parser') && (
          <>
            <div className="lab">Structure</div>
            <div>{entry.structure.filter((s) => s.builtBy === 'parser').map((s, i) => <StructureView key={i} s={s} document={mainDoc} onHover={onHover} />)}</div>
          </>
        )}

        {/* Warnings are never folded away (WH5). */}
        {(entry.flags.length > 0 || failed.length > 0) && (
          <>
            <div className="lab">Caution</div>
            <div>
              {failed.map((c, i) => <Failed key={i} check={c} />)}
              {entry.flags.map((f) => (
                <div key={f.id + f.text} className="caution">
                  <Sign kind={f.id === 'language-model' ? 'lm' : 'warn'} />
                  <span>{f.text}</span>
                </div>
              ))}
            </div>
          </>
        )}

        <div className="lab">CTDL</div>
        <div>
          {slot?.ctdl ? (
            <p>
              CTDL: <q className="def">{slot.ctdl.definition}</q> <Rich text={slot.choice} />
            </p>
          ) : (
            <p>
              <Rich text={slot?.plain ?? ''} /> <Rich text={slot?.choice ?? ''} />
            </p>
          )}
          {entry.concept && <ConceptLine concept={entry.concept} scheme={entry.scheme!} teaching={teaching} />}
          {(entry.unstable || slot?.ctdl?.unstable) && <p className="muted">The schema marks this field unstable: it may still change.</p>}
        </div>
      </div>

      {sections.map((s) =>
        isOpen(s.id, s.from) ? (
          <section key={s.id} className="sec">
            <h4 onClick={() => toggle(s.id, s.from)}>▾ {s.title}</h4>
            {s.id === 'ctdl' && <Ctdl entry={entry} teaching={teaching} />}
            {s.id === 'alternatives' && (
              <div className="alt">
                {slot.alternatives.map((a) => [
                  <b key={a.name}><Rich text={a.name} /></b>,
                  <span key={a.name + 'w'}><Rich text={a.why_not} /></span>,
                ])}
              </div>
            )}
            {s.id === 'found' && <Found entry={entry} />}
            {s.id === 'evidence' && <EvidenceFull entry={entry} docs={docs} code={course.code} />}
            {s.id === 'checks' && entry.checks.map((c, i) => (
              <div key={i} className="chk">
                <span className={c.status}>{c.status === 'pass' ? '✓' : c.status === 'fail' ? '✗' : '○'}</span>
                <span>
                  {c.id && <code>{c.id} </code>}{c.text}
                  {c.detail && c.status === 'fail' ? <span className="found">Found: {Array.isArray(c.detail) ? c.detail.join(' ') : c.detail}</span> : null}
                </span>
              </div>
            ))}
          </section>
        ) : null,
      )}
      {sections.some((s) => !isOpen(s.id, s.from)) && (
        <div className="more">
          {sections.filter((s) => !isOpen(s.id, s.from)).map((s) => (
            <button key={s.id} onClick={() => toggle(s.id, s.from)}>
              ▸ {s.title}{s.id === 'checks' ? ` · ${checkCount(entry.checks)}` : ''}
            </button>
          ))}
        </div>
      )}
      <div className="why-path mono">{path}</div>
    </div>
  )
}

function ConceptLine({ concept, scheme, teaching }: { concept: string; scheme: string; teaching: Teaching }) {
  const c = teaching.schemes[scheme]?.concepts.find((x) => x.term === concept)
  if (!c) return null
  return (
    <p>
      The chosen entry, <b>{c.label}</b>: <q className="def">{c.definition}</q>
    </p>
  )
}

function Ctdl({ entry, teaching }: { entry: Entry; teaching: Teaching }) {
  const slot = teaching.slots[entry.slot]
  const t = slot.ctdl!
  const schemeId = entry.scheme ?? slot.options ?? t.scheme
  const scheme = schemeId ? teaching.schemes[schemeId] : undefined
  const [all, setAll] = useState(false)
  return (
    <>
      <p>
        <code>{t.term}</code> is a {t.kind}: <q className="def">{t.definition}</q>
      </p>
      {t.note && <p className="muted">Note: <q className="def">{t.note}</q></p>}
      {t.usageNote && <p className="muted">Usage: <q className="def">{t.usageNote}</q></p>}
      {t.range && <p className="muted">Allowed kind of value: {t.range.length > 6 ? `${t.range.slice(0, 5).map(local).join(', ')} and ${t.range.length - 5} more` : t.range.map(local).join(', ')}.</p>}
      {slot.examples && <p className="muted">Examples: <Rich text={slot.examples} /></p>}
      <p className="links">
        <a href={t.page} target="_blank" rel="noreferrer">{local(t.term)} ↗</a>
        {scheme && (
          <>
            {' · '}
            <a href={scheme.page} target="_blank" rel="noreferrer">All {scheme.concepts.length} in the {scheme.label} list ↗</a>
            {' · '}
            <button className="linkish" onClick={() => setAll(!all)}>{all ? 'hide them' : 'show them here'}</button>
          </>
        )}
        <span className="faint"> · schema copy of {teaching.schemaCopyDate}</span>
      </p>
      {all && scheme && (
        <div className="alt options">
          {scheme.concepts.map((c) => [
            <b key={c.term} className={c.term === entry.concept ? 'chosen' : ''}>{c.label}</b>,
            <span key={c.term + 'd'}>{c.definition}</span>,
          ])}
        </div>
      )}
    </>
  )
}

function Found({ entry }: { entry: Entry }) {
  const names = entry.evidence.filter((e) => e.rule || e.table)
  return (
    <>
      {entry.structure?.map((s, i) => (
        <p key={i}>
          <b>Structure:</b>{' '}
          {s.builtBy === 'parser' && 'read by the parser, which accepts only course codes, “and”, “or”, commas, brackets and a short list of known phrases, and declines anything else.'}
          {s.builtBy === 'language model' && `proposed by the language model ${s.languageModel?.name} after the parser declined the sentence, and kept because it passed every guard.`}
          {s.builtBy === 'nobody' && (s.languageModel ? 'the parser declined the sentence, and the language model’s proposal failed a guard, so it was discarded.' : 'the parser declined the sentence and no language model answered.')}
        </p>
      ))}
      {!names.length && !entry.structure && <p>{entry.how} <span className="faint">Produced by {entry.producedBy}.</span></p>}
    </>
  )
}

function EvidenceFull({ entry, docs, code }: { entry: Entry; docs: Record<string, DocMeta>; code: string }) {
  const short = (d: string) => `sha256 ${d.slice(0, 4)}…${d.slice(-4)}`
  return (
    <>
      {entry.evidence.filter((e) => e.kind !== 'none').map((e) => {
        const doc = e.document ? docs[e.document] : undefined
        return (
          <div key={e.n} className="ev">
            <Badge n={e.n} />
            <div>
              <div className="muted">{e.role}{doc && <> · {doc.name} · {short(doc.digest)}{!doc.current && <b className="warn"> · a newer copy of this page exists; re-check</b>}</>}</div>
              {e.segments?.slice(0, 14).map((s: Segment, i) => (
                <div key={i} className="where">
                  <span className="mono">“{s.quote.length > 90 ? s.quote.slice(0, 60) + ' … ' + s.quote.slice(-24) : s.quote}”</span>{' '}
                  <span className="faint">characters {s.start.toLocaleString()}–{s.end.toLocaleString()}</span>
                  {doc?.kind === 'page' && <> · <a href={textFragment(doc.finalAddress, s.quote)} target="_blank" rel="noreferrer">open original at this text ↗</a></>}
                </div>
              ))}
              {(e.segments?.length ?? 0) > 14 && <div className="faint">and {e.segments!.length - 14} more</div>}
              {e.kind === 'markup' && <div className="where"><span className="mono">&lt;{e.element}{e.attribute ? ` ${e.attribute}="${e.source?.quote}"` : ''}&gt;</span> <span className="faint">characters {e.source?.start}–{e.source?.end} of {e.source?.of}</span></div>}
              {e.kind === 'record' && <div className="where"><a href={e.address} target="_blank" rel="noreferrer">{e.address} ↗</a> <span className="faint">read {e.readAt}</span></div>}
              {e.kind === 'address' && <div className="where mono">{e.address}</div>}
              {e.kind === 'derived' && <div className="where">{e.from} → {e.result}</div>}
            </div>
          </div>
        )
      })}
      <p className="faint">
        <a href={`https://catalog.uark.edu/search/?P=${encodeURIComponent(code)}`} target="_blank" rel="noreferrer">This course alone, on the live site ↗</a>{' '}
        · Links to the live site are a convenience. The stored copy is the evidence.
      </p>
    </>
  )
}

/** What the language model answered, set apart from everything the rules produced: its reading
 *  of the sentence, its own argument for it, and whether the guards let it into the record. */
export function ModelOutput({ s, document, onHover }: { s: Structure; document: string; onHover: (h: Hover) => void }) {
  const lm = s.languageModel
  if (!lm) return null
  const kept = s.builtBy === 'language model'
  const failed = s.guards.filter((g) => g.status === 'fail')
  return (
    <div className={'lmbox' + (kept ? '' : ' refused')}>
      <div className="lmbox-head">
        <Sign kind="lm" />
        <b>{lm.name}</b> read the sentence as
        <span className="sp" />
        <span className={'verdict ' + (kept ? 'kept' : 'out')}>
          {kept ? `In the record · passed all ${s.guards.length} guards` : `Not in the record · failed ${failed.map((g) => g.id).join(', ')}`}
        </span>
      </div>
      {kept ? <StructureView s={s} document={document} onHover={onHover} /> : <div className="rt"><ProposalView raw={s.discarded?.structure} root /></div>}
      {lm.argument && (
        <div className="lmbox-arg">
          <span>Its argument</span>
          <q>{lm.argument}</q>
        </div>
      )}
      {kept && <p className="faint">Passing the guards shows the reading uses the sentence's own words and links. It does not show the “and” and “or” are right. No person has confirmed it.</p>}
    </div>
  )
}

/** A proposal exactly as the language model wrote it (kind / quote / items), before any check. */
function ProposalView({ raw, root }: { raw: unknown; root?: boolean }): ReactNode {
  if (typeof raw !== 'object' || raw === null) return <span className="txt">{JSON.stringify(raw)}</span>
  const { kind, quote, items } = raw as { kind?: string; quote?: string; items?: unknown[] }
  if (kind === 'course') return <span className="course">{quote}</span>
  if (kind === 'text') return <span className="txt">“{quote}”</span>
  const kids = items ?? []
  const leaf = (k: unknown) => typeof k === 'object' && k !== null && ['course', 'text'].includes((k as { kind?: string }).kind ?? '')
  const leavesOnly = kids.every(leaf)
  return (
    <div className={'group' + (root ? ' root' : '')}>
      <div className="node">
        <span className={'op ' + (kind === 'any_of' ? 'any' : 'all')}>{kind === 'any_of' ? 'ANY ONE OF' : kind === 'all_of' ? 'ALL OF' : String(kind)}</span>
        {leavesOnly && kids.map((k, i) => <ProposalView key={i} raw={k} />)}
        {!kids.length && <span className="faint">nothing</span>}
      </div>
      {!leavesOnly && <div className="kids">{kids.map((k, i) => (leaf(k) ? <div key={i} className="node"><ProposalView raw={k} /></div> : <ProposalView key={i} raw={k} />))}</div>}
    </div>
  )
}

function StructureView({ s, document, onHover }: { s: Structure; document: string; onHover: (h: Hover) => void }) {
  const hover = (n: TreeNode | null) => onHover(n ? { document, start: n.start, end: n.end } : null)
  if (!s.tree) return null
  return (
    <div className="rt" onMouseLeave={() => hover(null)}>
      <NodeView node={s.tree} hover={hover} root />
      <p className="faint">Point at any part to light up its words on the page.</p>
    </div>
  )
}

function NodeView({ node, hover, root }: { node: TreeNode; hover: (n: TreeNode | null) => void; root?: boolean }): ReactNode {
  const over = (e: React.MouseEvent) => (e.stopPropagation(), hover(node))
  if (node.kind === 'course') {
    return <span className={'course' + (node.hasRecord ? '' : ' ext')} title={node.hasRecord ? node.uri : 'Referenced, no record yet'} onMouseOver={over}>{node.code}</span>
  }
  if (node.kind === 'text') {
    return <span className="txt" onMouseOver={over}>“{node.quote.replace(/\s+/g, ' ')}”</span>
  }
  const kids = node.children ?? []
  const leavesOnly = kids.every((k) => k.kind === 'course' || k.kind === 'text')
  const kept = node.landed?.how === 'kept as text'
  return (
    <div className={'group' + (root ? ' root' : '')}>
      <div className="node" onMouseOver={over}>
        <span className={'op ' + (node.kind === 'any_of' ? 'any' : 'all')}>{node.kind === 'any_of' ? 'ANY ONE OF' : 'ALL OF'}</span>
        {leavesOnly && kids.map((k, i) => <NodeView key={i} node={k} hover={hover} />)}
        {kept && <span className="kept" title="CTDL could not carry this part exactly; its words are kept in ceterms:condition">kept as text</span>}
      </div>
      {!leavesOnly && (
        <div className="kids">
          {kids.map((k, i) => (k.kind === 'course' || k.kind === 'text' ? <div key={i} className="node"><NodeView node={k} hover={hover} /></div> : <NodeView key={i} node={k} hover={hover} />))}
        </div>
      )}
    </div>
  )
}
