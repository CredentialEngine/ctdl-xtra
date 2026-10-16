import { useState, type ReactNode } from 'react'
import { Glossary, isGlossary } from './Glossary'
import type { Forms, TermDoc } from './types'

// Keys a record carries that JSON-LD defines, not CTDL. Said plainly so nothing here passes for a CTDL definition.
const KEYWORDS: Record<string, [string, string]> = {
  '@context': ['Context', 'Says which vocabulary the field names in this record come from. Here, CTDL.'],
  '@id': ['Address of this record', 'The address that identifies this record. Other records refer to it by this address.'],
  '@type': ['Kind of record', 'The CTDL class this record, or this part of it, belongs to.'],
}
const KIND: Record<string, string> = {
  'rdf:Property': 'CTDL property',
  'rdfs:Class': 'CTDL class',
  'skos:ConceptScheme': 'CTDL concept scheme (a fixed list)',
  'skos:Concept': 'CTDL concept (an entry in a fixed list)',
}
const STATUS: Record<string, string> = {
  'vs:stable': 'Stable',
  'vs:unstable': 'Unstable: CTDL may still change it',
  'vs:deprecated': 'Deprecated: CTDL no longer recommends it',
}
const spaced = (term: string) => (term.split(':')[1] ?? term).replace(/([a-z])([A-Z])/g, '$1 $2')

// The full record of a term. A tab still holding data loaded before the full records were exported
// falls back to the shorter description it does have, so a definition is never lost to stale data.
function doc(term: string, forms: Forms): TermDoc | undefined {
  const full = forms.terms?.[term]
  if (full) return full
  const prop = forms.properties[term]
  const cls = forms.classes[term] ?? forms.others?.[term]
  const scheme = forms.schemes[term]
  const known = prop ?? cls ?? scheme
  if (!known) {
    for (const list of Object.values(forms.schemes)) {
      const entry = list.concepts.find((c) => c.term === term)
      if (entry) return { term, uri: term, page: term, label: entry.label, definition: entry.definition, type: 'skos:Concept', inScheme: [list.term] }
    }
    return undefined
  }
  return {
    term,
    uri: term,
    page: known.page ?? term,
    label: known.label,
    definition: known.definition,
    type: prop ? 'rdf:Property' : scheme ? 'skos:ConceptScheme' : 'rdfs:Class',
    rangeIncludes: prop?.range,
    targetScheme: prop?.scheme ? [prop.scheme] : undefined,
    domainFor: forms.classes[term]?.properties,
    hasConcept: scheme?.concepts.map((c) => c.term),
    standAlone: cls ? forms.standAlone.includes(term) || term === forms.root : undefined,
  }
}
const isLanguage = (term: string) => /^[a-z]{2,3}(-[A-Za-z0-9]+)*$/.test(term)

export const termLabel = (term: string, forms: Forms) => (isGlossary(term) ? 'Glossary' : doc(term, forms)?.label ?? KEYWORDS[term]?.[0] ?? term)
export const termAddress = (term: string, forms: Forms) => (isGlossary(term) ? 'The headings on a term page, explained by this tool' : doc(term, forms)?.page ?? term)

/** A long list shows its first few, then the rest on request. */
function Some<T>({ items, first, noun, children }: { items: T[]; first: number; noun: string; children: (item: T) => ReactNode }) {
  const [all, setAll] = useState(false)
  return (
    <>
      {(all ? items : items.slice(0, first)).map(children)}
      {items.length > first && (
        <button className="ti-more" onClick={() => setAll(!all)}>{all ? 'show fewer' : `and ${items.length - first} more ${noun}`}</button>
      )}
    </>
  )
}

/** A CTDL name that leads to its own page. Declared out here so a redraw of the page never replaces a link mid-click. */
function TermLink({ to, forms, onFollow, code }: { to: string; forms: Forms; onFollow: (term: string) => void; code?: boolean }) {
  const there = doc(to, forms)
  const text = code ? to : there?.label ?? spaced(to)
  // A name from another vocabulary (schema:Date, xsd:string) has no page in the schema copy.
  if (!there) return <span className={'ti-chip plain' + (code ? ' mono' : '')} title="Not a CTDL term: it comes from another vocabulary">{to}</span>
  return <button className={'ti-chip' + (code ? ' mono' : '')} title={`${to}\n${there.definition}`} onClick={(e) => (e.stopPropagation(), onFollow(to))}>{text}</button>
}

/** What CTDL states about a name, laid out as the term's page on credreg.net is, with every name on it a link. */
export function TermInfo({ term, forms, used = [], onFollow }: { term: string; forms: Forms; used?: string[]; onFollow: (term: string) => void }) {
  if (isGlossary(term)) return <Glossary at={term.slice('glossary:'.length)} forms={forms} />
  return <TermPage term={term} forms={forms} used={used} onFollow={onFollow} />
}

function TermPage({ term, forms, used, onFollow }: { term: string; forms: Forms; used: string[]; onFollow: (term: string) => void }) {
  const t = doc(term, forms)
  if (!t) {
    const keyword = KEYWORDS[term]
    return (
      <div className="terminfo">
        <div className="ti-kind">{keyword ? 'JSON-LD keyword, not a CTDL term' : isLanguage(term) ? 'Language tag, not a CTDL term' : 'Not in the CTDL schema copy'}</div>
        <h3>{keyword?.[0] ?? term}</h3>
        <div className="mono muted">{term}</div>
        <p className="ti-def">{keyword?.[1] ?? (isLanguage(term) ? `The text beside this tag is written in this language (${term}).` : 'No definition was found for this name.')}</p>
      </div>
    )
  }

  const link = (to: string) => <TermLink key={to} to={to} forms={forms} onFollow={onFollow} />
  const links = (items: string[] | undefined, noun: string, first = 14) => items?.length ? <Some items={items} first={first} noun={noun}>{link}</Some> : null
  // A term named inside a note ("use ceterms:startDate") leads to that term's page.
  const text = (s: string) => (
    <>
      <span className="ti-lang">en-US</span>
      {s.split(/(https?:\/\/[^\s)]+[^\s).,;]|\b[a-z]+:[A-Za-z]\w+)/).map((part, i) =>
        i % 2 === 0 ? part : /^https?:/.test(part) ? <a key={i} href={part} target="_blank" rel="noreferrer">{part}</a> : doc(part, forms) ? <TermLink key={i} to={part} forms={forms} onFollow={onFollow} code /> : part,
      )}
    </>
  )
  const table = (items: string[], noun: string, mark?: (term: string) => ReactNode) => (
    <div className="ti-table">
      <Some items={items} first={12} noun={noun}>
        {(p) => [<span key={p}>{link(p)}{mark?.(p)}</span>, <span key={p + 'd'}>{doc(p, forms)?.definition}</span>]}
      </Some>
    </div>
  )
  // The entries of a fixed list, each with everything CTDL says about it, so a reader can judge whether
  // the right one was picked. The one this record uses is marked.
  const entries = (items: string[]) => (
    <div className="ti-entries">
      {items.map((c) => {
        const e = doc(c, forms)
        return (
          <div key={c} className={'ti-entry' + (used.includes(c) ? ' used' : '')}>
            <div className="ti-entry-head">
              {link(c)}
              <span className="mono faint">{c}</span>
              {used.includes(c) && <span className="ti-used">used in this record</span>}
            </div>
            <div>{e?.definition ?? <span className="faint">The schema copy gives no definition.</span>}</div>
            {e?.comment && <div className="muted"><span className="ti-note">Comment</span>{e.comment}</div>}
            {e?.usageNote && <div className="muted"><span className="ti-note">Usage note</span>{e.usageNote}</div>}
            {e?.broader && <div className="muted"><span className="ti-note">Narrower than</span>{e.broader.map(link)}</div>}
          </div>
        )
      })}
    </div>
  )
  // Each heading leads to the glossary, which says what the heading stands for and whose word it is.
  const row = (label: string, id: string, value: ReactNode, ours?: boolean) =>
    value
      ? [
          <dt key={label}><button className={'ti-head' + (ours ? ' ours' : '')} title="What this heading means" onClick={() => onFollow('glossary:' + id)}>{label}</button></dt>,
          <dd key={label + 'v'}>{value}</dd>,
        ]
      : null

  const isClass = t.type === 'rdfs:Class'
  const isProperty = t.type === 'rdf:Property'
  const inPlace = (c: string) => doc(c, forms)?.type === 'rdfs:Class' && !doc(c, forms)?.standAlone
  const range = t.rangeIncludes ?? []
  const scheme = t.targetScheme?.[0] ? doc(t.targetScheme[0], forms) : undefined
  // Worked out from the copy, not stated on the term itself: which properties can hold this class or list.
  const heldBy = isProperty ? [] : Object.values(forms.terms ?? {}).filter((p) => p.rangeIncludes?.includes(term) || p.targetScheme?.includes(term)).map((p) => p.term)
  // The required list is the one for a course; it says nothing about the classes written inside one.
  const required = (p: string) => term === forms.root && (forms.required.includes(p) ? 'required' : forms.requiredOneOf.includes(p) ? 'one of these required' : '')
  const onCourse = isProperty && (forms.required.includes(term) || forms.requiredOneOf.includes(term))
  const fields = [...(t.domainFor ?? [])].sort((a, b) => Number(!!required(b)) - Number(!!required(a)))

  return (
    <div className="terminfo">
      <div className="ti-kind">{KIND[t.type] ?? t.type}</div>
      <h3>{t.label}</h3>
      <div className="mono muted">{term}</div>
      <p className="ti-def">{t.definition}</p>
      {used.includes(term) && <p className="ti-usedline"><span className="ti-used">used in this record</span></p>}

      <dl>
        {row('URI', 'uri', <a className="mono ti-uri" href={t.uri} target="_blank" rel="noreferrer">{t.uri}</a>)}
        {row('Shorthand URI', 'shorthand', <span className="mono">{term}</span>)}
        {row('Label', 'label', text(t.label))}
        {row('Definition', 'definition', text(t.definition))}
        {row('Comment', 'comment', t.comment && text(t.comment))}
        {row('Usage Note', 'usageNote', t.usageNote && text(t.usageNote))}
        {row('Type of Term', 'type', <span className="mono">{t.type}</span>)}
        {row('Status', 'status', t.status && <><span className="mono">{t.status}</span> <span className="faint">· {STATUS[t.status] ?? ''}</span></>)}
        {row('On a course', 'onACourse', onCourse && (forms.required.includes(term) ? 'Required. Credential Engine will not accept a course without it.' : <>Required, unless the other is given: {forms.requiredOneOf.map(link)}</>), true)}
        {row('Subclass Of', 'subClassOf', links(t.subClassOf, 'classes'))}
        {row('Subproperty Of', 'subPropertyOf', links(t.subPropertyOf, 'properties'))}
        {row('Equivalent To', 'equivalent', links(t.equivalentClass ?? t.equivalentProperty, 'terms'))}
        {row('Inverse Of', 'inverseOf', links(t.inverseOf, 'properties'))}
        {row('Domain Includes', 'domainIncludes', links(t.domainIncludes, 'classes'))}
        {row(
          'Range Includes',
          'rangeIncludes',
          range.length > 0 && (
            <>
              {range.some(inPlace) && <div className="ti-sub">Written here, inside the record</div>}
              {range.filter(inPlace).map(link)}
              {range.some(inPlace) && range.some((r) => !inPlace(r)) && <div className="ti-sub">Or pointed to, by address</div>}
              {links(range.filter((r) => !inPlace(r)), 'kinds of value')}
            </>
          ),
        )}
        {row(
          'Target Scheme',
          'targetScheme',
          scheme && (
            <>
              {link(scheme.term)}
              <div className="ti-sub">Its {scheme.hasConcept?.length ?? 0} entries, as CTDL defines them</div>
              {entries(scheme.hasConcept ?? [])}
            </>
          ),
        )}
        {row('In Scheme', 'inScheme', links(t.inScheme, 'lists'))}
        {row('Broader', 'broader', links(t.broader, 'entries'))}
        {row('Narrower', 'narrower', links(t.narrower, 'entries'))}
        {row('Related', 'related', links([...(t.relatedMatch ?? []), ...(t.narrowMatch ?? [])], 'terms'))}
        {row('Has Concept', 'hasConcept', t.hasConcept && entries(t.hasConcept))}
        {row('Written', 'written', isClass && (t.standAlone ? 'As a record of its own, with its own address and CTID. Other records point to it.' : 'In place, inside the record that uses it. It has no address of its own.'), true)}
        {row('Domain For', 'domainFor', fields.length > 0 && table(fields, 'properties', (p) => required(p) && <span className="ti-req">{required(p)}</span>))}
        {row(t.type === 'skos:ConceptScheme' ? 'Used By' : 'Held By', 'heldBy', links(heldBy, 'properties'), true)}
        {row(
          'History',
          'history',
          t.history && <a href={t.history} target="_blank" rel="noreferrer">Change history on credreg.net ↗</a>,
        )}
      </dl>
      <p className="ti-out">
        <a href={t.page} target="_blank" rel="noreferrer">Open this term on credreg.net ↗</a>
        <span className="faint"> · Everything above is from the stored schema copy, not the live site. Rows with a dotted label are worked out by this tool and are not on CTDL's page.</span>
      </p>
    </div>
  )
}
