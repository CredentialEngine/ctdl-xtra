import { useEffect, useRef } from 'react'
import type { Forms } from './types'

// The headings on a term's page. CTDL does not define these words. Each heading stands for a property
// that Credential Engine borrowed from another vocabulary (or, for `meta:`, made for its own schema
// management) to describe CTDL's terms. So the explanations here are this tool's, and say so; what the
// CTDL handbook itself says is quoted where it says anything.
export type Heading = {
  id: string
  heading: string
  stands: string[] // the properties the heading stands for, as written in the schema copy
  plain: string
  handbook?: string
}

const OWNERS: Record<string, string> = {
  rdf: 'RDF (W3C)',
  rdfs: 'RDF Schema (W3C)',
  skos: 'SKOS, the Simple Knowledge Organization System (W3C)',
  owl: 'OWL, the Web Ontology Language (W3C)',
  dct: 'Dublin Core terms',
  vann: 'VANN, a vocabulary for annotating vocabularies',
  vs: 'the W3C vocabulary-status vocabulary',
  schema: 'schema.org',
  meta: 'Credential Engine, for managing its own schemas',
}

export const HEADINGS: Heading[] = [
  { id: 'uri', heading: 'URI', stands: ['@id'], plain: 'The term’s full, permanent address. It is what identifies the term to software, and it does not change when the label is reworded.', handbook: 'The URIs for CTDL concepts all begin https://purl.org/ctdl/vocabs/ , which is followed by a name for the relevant concept scheme.' },
  { id: 'shorthand', heading: 'Shorthand URI', stands: ['@id'], plain: 'The same address written short: a prefix, a colon, and the term’s name. The prefix stands for the first part of the address, so ceterms:name is https://purl.org/ctdl/terms/name. This is the form used inside records.' },
  { id: 'label', heading: 'Label', stands: ['rdfs:label', 'skos:prefLabel'], plain: 'The term’s name for people. Entries of a fixed list use the second property; everything else uses the first.' },
  { id: 'definition', heading: 'Definition', stands: ['rdfs:comment', 'skos:definition'], plain: 'What the term means, in one or two sentences. This is the text this tool quotes wherever it says “CTDL says”.' },
  { id: 'comment', heading: 'Comment', stands: ['dct:description'], plain: 'Further explanation beyond the definition: background, scope, or how the term relates to others. Many terms have none.' },
  { id: 'usageNote', heading: 'Usage Note', stands: ['vann:usageNote'], plain: 'Practical guidance on using the term: the expected format of a value, or when to use a different term. Many terms have none.' },
  { id: 'type', heading: 'Type of Term', stands: ['@type'], plain: 'What kind of thing the term is. rdf:Property: a field. rdfs:Class: a kind of record or part of a record. skos:ConceptScheme: a fixed list. skos:Concept: one entry in a fixed list.' },
  { id: 'status', heading: 'Status', stands: ['vs:term_status'], plain: 'How settled the term is. Stable terms are not expected to change. Unstable terms may still be changed or removed. Deprecated terms are kept but should not be used.', handbook: 'Deprecating a term simply means that, while the term remains in the namespace with the same URI, we do not use it and do not recommend others use it.' },
  { id: 'subClassOf', heading: 'Subclass Of', stands: ['rdfs:subClassOf'], plain: 'A broader class this class is a special case of. Whatever is true of the broader class is true of this one.' },
  { id: 'subPropertyOf', heading: 'Subproperty Of', stands: ['rdfs:subPropertyOf'], plain: 'A broader property this property is a special case of.' },
  { id: 'equivalent', heading: 'Equivalent To', stands: ['owl:equivalentClass', 'owl:equivalentProperty'], plain: 'A term in another vocabulary that means the same thing.' },
  { id: 'inverseOf', heading: 'Inverse Of', stands: ['owl:inverseOf'], plain: 'The property that says the same thing from the other end. If A requires B, then B is required for A.' },
  { id: 'domainIncludes', heading: 'Domain Includes', stands: ['schema:domainIncludes'], plain: 'The classes this property may be used on. A property may only appear on a record whose class is in this list.', handbook: 'Many of the properties in CTDL have multiple domains and ranges. To avoid unintended semantic inferencing, CTDL defines properties using schema.org’s domainIncludes and rangeIncludes instead of RDF Schema’s domain and range.' },
  { id: 'rangeIncludes', heading: 'Range Includes', stands: ['schema:rangeIncludes'], plain: 'The kinds of value this property may hold: a class, or a plain kind of value such as text or a date.', handbook: 'Many of the properties in CTDL have multiple domains and ranges. To avoid unintended semantic inferencing, CTDL defines properties using schema.org’s domainIncludes and rangeIncludes instead of RDF Schema’s domain and range.' },
  { id: 'targetScheme', heading: 'Target Scheme', stands: ['meta:targetScheme'], plain: 'The fixed list this property’s value must be picked from.', handbook: 'Terms and classes used to aid in the management of schemas by the Credential Engine. Not intended for external implementation.' },
  { id: 'hasConcept', heading: 'Has Concept', stands: ['meta:hasConcept'], plain: 'The entries of a fixed list.' },
  { id: 'inScheme', heading: 'In Scheme', stands: ['skos:inScheme'], plain: 'The fixed list an entry belongs to.' },
  { id: 'broader', heading: 'Broader', stands: ['skos:broader'], plain: 'A more general entry in the same list. Teach Out is a kind of Ceasing.' },
  { id: 'narrower', heading: 'Narrower', stands: ['skos:narrower'], plain: 'More specific entries in the same list.' },
  { id: 'related', heading: 'Related', stands: ['skos:relatedMatch', 'skos:narrowMatch'], plain: 'Entries in other lists that are related to this one, or narrower than it.' },
  { id: 'domainFor', heading: 'Domain For', stands: ['meta:domainFor'], plain: 'Every property that may be used on this class. It is Domain Includes read from the class’s side.' },
  { id: 'history', heading: 'History', stands: ['meta:changeHistory'], plain: 'The address of the term’s record of changes on credreg.net.' },
  { id: 'onACourse', heading: 'On a course', stands: [], plain: 'Whether Credential Engine’s Minimum Data Policy requires this property on every course. Worked out by this tool from that policy; it is not on CTDL’s term page.' },
  { id: 'written', heading: 'Written', stands: [], plain: 'Whether a class is written inside the record that uses it, or is a record of its own that others point to by address. Worked out by this tool: a class that can carry a CTID is a record of its own.' },
  { id: 'heldBy', heading: 'Held By / Used By', stands: [], plain: 'The properties whose range includes this class, or whose target scheme is this list. Worked out by this tool by reading every property in the schema copy.' },
]

export const isGlossary = (term: string) => term.startsWith('glossary:')

function expand(name: string, forms: Forms): string | null {
  const [prefix, local] = name.split(':')
  const base = forms.prefixes?.[prefix]
  return base && local ? base + local : null
}

/** The headings of a term page, explained. One page; the heading asked for is brought into view. */
export function Glossary({ at, forms }: { at: string; forms: Forms }) {
  const here = useRef<HTMLDivElement>(null)
  useEffect(() => {
    here.current?.scrollIntoView({ block: 'center' })
  }, [at])
  return (
    <div className="terminfo">
      <div className="ti-kind">Glossary · written for this tool</div>
      <h3>The headings on a term page</h3>
      <p className="ti-def">CTDL does not define these words. Each heading stands for a property that Credential Engine borrowed from another vocabulary to describe its own terms.</p>
      <p className="muted">
        The explanations below are this tool’s, not Credential Engine’s. Where the CTDL handbook says something on the subject, it is quoted. The handbook’s own account:{' '}
        <q className="def">RDFS and terms from many other specifications are used in defining CTDL; these are listed in the references section of the CTDL Schema.</q>
      </p>
      <div className="ti-entries">
        {HEADINGS.map((h) => (
          <div key={h.id} ref={h.id === at ? here : undefined} className={'ti-entry' + (h.id === at ? ' used' : '')}>
            <div className="ti-entry-head"><b>{h.heading}</b></div>
            <div>{h.plain}</div>
            {h.stands.map((s) => {
              const uri = expand(s, forms)
              const owner = OWNERS[s.split(':')[0]] ?? (s.startsWith('@') ? 'JSON-LD' : '')
              return (
                <div key={s} className="muted">
                  <span className="ti-note">Stands for</span>
                  <span className="mono">{s}</span>
                  {owner && <>, from {owner}</>}
                  {uri && <> · <a href={uri} target="_blank" rel="noreferrer">{uri} ↗</a></>}
                </div>
              )
            })}
            {h.handbook && <div className="muted"><span className="ti-note">CTDL handbook</span><q className="def">{h.handbook}</q></div>}
          </div>
        ))}
      </div>
    </div>
  )
}
