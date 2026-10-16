import { useMemo, useState, type ReactNode } from 'react'
import { Icon, IconButton } from './Rich'
import type { CourseRow, FormProperty, Forms } from './types'

// A form for one field of a record, built from the CTDL schema copy: what a property may hold
// decides which control is shown. Nobody has to read or write JSON to change a value.

const LANG = 'en-US'
const ALIGNMENT = 'ceterms:CredentialAlignmentObject'
// The Registry writes these as one value; everything else that can repeat is a list.
const ONE = new Set([
  'ceterms:name', 'ceterms:description', 'ceterms:codedNotation', 'ceterms:ctid', 'ceterms:subjectWebpage', 'ceterms:lifeCycleStatusType',
  'ceterms:inCatalog', 'schema:value', 'schema:minValue', 'schema:maxValue', 'schema:description', 'ceterms:identifierTypeName',
  'ceterms:identifierValueCode', 'ceterms:identifierType', 'ceterms:targetNode', 'ceterms:framework', 'ceterms:frameworkName',
  'ceterms:targetNodeName', 'ceterms:targetNodeDescription', 'ceterms:percentage', 'ceterms:weight', 'ceterms:minimumAge', 'ceterms:yearsOfExperience',
])
const MANY_TEXT = new Set(['ceterms:condition', 'ceterms:keyword', 'ceterms:alternateName', 'ceterms:conditionExcludes'])
// What a reviewer most often wants to add, offered first.
const COMMON: Record<string, string[]> = {
  'ceterms:ConditionProfile': ['ceterms:description', 'ceterms:targetLearningOpportunity', 'ceterms:condition', 'ceterms:alternativeCondition', 'ceterms:name', 'ceterms:creditValue', 'ceterms:audienceLevelType'],
  'ceterms:ValueProfile': ['schema:value', 'schema:minValue', 'schema:maxValue', 'ceterms:creditUnitType', 'schema:description'],
  'ceterms:IdentifierValue': ['ceterms:identifierTypeName', 'ceterms:identifierValueCode', 'ceterms:identifierType'],
}
const PLAIN: Record<string, string> = {
  'ceterms:alternativeCondition': 'Any one of these',
  'ceterms:targetLearningOpportunity': 'Courses',
  'ceterms:condition': 'Other conditions',
  'ceterms:identifierTypeName': 'Kind of identifier',
  'ceterms:identifierValueCode': 'Identifier',
  'schema:value': 'Amount',
  'schema:minValue': 'At least',
  'schema:maxValue': 'At most',
  'ceterms:creditUnitType': 'Unit',
}
const LANGUAGES = ['en', 'es', 'fr', 'de', 'zh', 'ar', 'pt', 'ja', 'ko', 'ru', 'it', 'vi']

export type EditContext = {
  forms: Forms
  courses: CourseRow[]
  references: Record<string, { code: string; hasRecord: boolean }>
  labels: Record<string, string> // our plain labels for terms, where we have one
}

type Kind = 'concept' | 'text' | 'object' | 'reference' | 'number' | 'date' | 'boolean' | 'language' | 'url' | 'string'
const isObject = (v: unknown): v is Record<string, unknown> => typeof v === 'object' && v !== null && !Array.isArray(v)
const list = (v: unknown): unknown[] => (v === undefined || v === null ? [] : Array.isArray(v) ? v : [v])

export function labelOf(term: string, ctx: EditContext): string {
  return PLAIN[term] ?? ctx.labels[term] ?? ctx.forms.properties[term]?.label ?? ctx.forms.classes[term]?.label ?? term.split(':')[1] ?? term
}

/** The classes that have to be written in place under a property (a profile, not a link). */
function inPlace(prop: FormProperty, forms: Forms): string[] {
  const all = prop.range.filter((r) => forms.classes[r] && !forms.standAlone.includes(r))
  return all.length > 1 ? all.filter((c) => c !== ALIGNMENT) : all
}

function kindOf(prop: FormProperty | undefined, forms: Forms, value?: unknown): Kind {
  if (!prop) return 'string'
  if (prop.scheme && forms.schemes[prop.scheme]) return 'concept'
  if (prop.languageText) return 'text'
  const links = prop.range.some((r) => forms.standAlone.includes(r))
  if (inPlace(prop, forms).length) {
    // Some fields may hold either a profile written here or a link to another record.
    const held = list(value)
    const asLinks = held.length ? held.every((v) => typeof v === 'string') : prop.term.startsWith('ceterms:target')
    return links && asLinks ? 'reference' : 'object'
  }
  if (links) return 'reference'
  const t = prop.datatype ?? prop.range[0] ?? ''
  if (/float|integer|decimal/.test(t)) return 'number'
  if (/date/i.test(t)) return 'date'
  if (/boolean/.test(t)) return 'boolean'
  if (/language/.test(t)) return 'language'
  if (t === '@id' || /anyURI/.test(t)) return 'url'
  return 'string'
}

function isMany(term: string, kind: Kind, value: unknown): boolean {
  if (Array.isArray(value)) return true
  if (kind === 'text') return isObject(value) ? Object.values(value).some(Array.isArray) : MANY_TEXT.has(term)
  if (value !== undefined && value !== null && value !== '') return false
  if (ONE.has(term)) return false
  return ['object', 'reference', 'concept', 'language', 'url'].includes(kind)
}

function alignment(forms: Forms, schemeId: string, concept: string): Record<string, unknown> {
  const scheme = forms.schemes[schemeId]
  const c = scheme.concepts.find((x) => x.term === concept)!
  return {
    '@type': ALIGNMENT,
    'ceterms:framework': scheme.page,
    'ceterms:targetNode': concept,
    'ceterms:frameworkName': { [LANG]: scheme.label },
    'ceterms:targetNodeName': { [LANG]: c.label },
    'ceterms:targetNodeDescription': { [LANG]: c.definition },
  }
}

export function emptyFor(term: string, ctx: EditContext): unknown {
  const prop = ctx.forms.properties[term]
  const kind = kindOf(prop, ctx.forms)
  const many = isMany(term, kind, undefined)
  if (kind === 'text') return { [LANG]: many ? [''] : '' }
  if (kind === 'object') return [{ '@type': inPlace(prop, ctx.forms)[0] }]
  if (kind === 'boolean') return false
  return many ? [] : ''
}

/** Drop everything left empty, so a half-filled form never writes blanks into a record. */
export function prune(v: unknown): unknown {
  if (typeof v === 'string') return v.trim() === '' ? undefined : v.trim()
  if (Array.isArray(v)) {
    const kept = v.map(prune).filter((x) => x !== undefined)
    return kept.length ? kept : undefined
  }
  if (isObject(v)) {
    const out: Record<string, unknown> = {}
    for (const [k, x] of Object.entries(v)) {
      const p = prune(x)
      if (p !== undefined) out[k] = p
    }
    const keys = Object.keys(out)
    return !keys.length || (keys.length === 1 && keys[0] === '@type') ? undefined : out
  }
  return v === null ? undefined : v
}

/** A value in a reader's words: "3 · Semester Hour", "ACCT 20203 and one of 2 others". */
export function summarise(v: unknown, ctx: EditContext): string {
  if (v === undefined || v === null || v === '') return '—'
  if (Array.isArray(v)) return v.map((x) => summarise(x, ctx)).join(v.some(isObject) && v.length > 1 ? '\n' : ', ')
  if (!isObject(v)) {
    const known = typeof v === 'string' ? ctx.references[v]?.code ?? ctx.courses.find((c) => c.uri === v)?.code : undefined
    return known ?? ctx.forms.rootChoices.find((c) => c.term === v)?.label ?? String(v)
  }
  const type = v['@type']
  const text = (k: string) => (v[k] === undefined ? '' : summarise(v[k], ctx))
  if (!type) return Object.values(v).flat().join(' · ') // text with a language tag
  if (type === ALIGNMENT) return text('ceterms:targetNodeName') || text('ceterms:targetNode')
  if (type === 'ceterms:ValueProfile') return [text('schema:value') || [text('schema:minValue'), text('schema:maxValue')].filter(Boolean).join('–'), text('ceterms:creditUnitType')].filter(Boolean).join(' · ')
  if (type === 'ceterms:IdentifierValue') return [text('ceterms:identifierTypeName'), text('ceterms:identifierValueCode')].filter(Boolean).join(' · ')
  if (type === 'ceterms:ConditionProfile') {
    if (v['ceterms:description']) return text('ceterms:description')
    const parts = [text('ceterms:targetLearningOpportunity'), text('ceterms:condition')].filter(Boolean)
    const alt = list(v['ceterms:alternativeCondition'])
    if (alt.length) parts.push(`one of: ${alt.map((a) => summarise(a, ctx)).join(' | ')}`)
    return parts.join('; ') || '—'
  }
  return Object.entries(v).filter(([k]) => k !== '@type').map(([k, x]) => `${labelOf(k, ctx)}: ${summarise(x, ctx)}`).join('; ')
}

// ----------------------------------------------------------------------------------- controls

function Text({ value, onChange, placeholder, autoFocus }: { value: string; onChange: (v: string) => void; placeholder?: string; autoFocus?: boolean }) {
  const rows = Math.min(10, Math.max(1, Math.ceil(value.length / 58), value.split('\n').length))
  return <textarea className="in" rows={rows} value={value} placeholder={placeholder} autoFocus={autoFocus} onChange={(e) => onChange(e.target.value)} />
}

/** Several values of the same kind: one row each, with a way to add and to remove. */
function Rows<T>({ items, onChange, blank, render, add }: { items: T[]; onChange: (v: T[]) => void; blank: T; render: (item: T, set: (v: T) => void, i: number) => ReactNode; add: string }) {
  return (
    <div className="rows">
      {items.map((item, i) => (
        <div key={i} className="row-item">
          {render(item, (v) => onChange(items.map((x, j) => (j === i ? v : x))), i)}
          <IconButton name="close" title="Remove" onClick={() => onChange(items.filter((_, j) => j !== i))} />
        </div>
      ))}
      <button className="add" onClick={() => onChange([...items, blank])}><Icon name="plus" size={13} /> {add}</button>
    </div>
  )
}

function Concepts({ prop, value, many, onChange, ctx }: { prop: FormProperty; value: unknown; many: boolean; onChange: (v: unknown) => void; ctx: EditContext }) {
  const scheme = ctx.forms.schemes[prop.scheme!]
  const chosen = list(value).map((v) => (isObject(v) ? String(v['ceterms:targetNode']) : String(v)))
  const toggle = (term: string) => {
    if (!many) return onChange(chosen[0] === term ? undefined : alignment(ctx.forms, prop.scheme!, term))
    const next = chosen.includes(term) ? chosen.filter((c) => c !== term) : [...chosen, term]
    onChange(next.map((c) => (scheme.concepts.some((x) => x.term === c) ? alignment(ctx.forms, prop.scheme!, c) : list(value).find((v) => isObject(v) && v['ceterms:targetNode'] === c))))
  }
  const active = scheme.concepts.find((c) => chosen.includes(c.term))
  return (
    <div>
      <div className="choices" role={many ? 'group' : 'radiogroup'}>
        {scheme.concepts.map((c) => (
          <button key={c.term} className={'choice' + (chosen.includes(c.term) ? ' on' : '')} role={many ? 'checkbox' : 'radio'} aria-checked={chosen.includes(c.term)} title={c.definition} onClick={() => toggle(c.term)}>
            {chosen.includes(c.term) && <Icon name="check" size={12} />} {c.label}
          </button>
        ))}
      </div>
      <div className="hint">{many ? 'Pick any that apply.' : 'Pick one.'}{active && chosen.length === 1 ? <> <b>{active.label}:</b> {active.definition}</> : ' Hover an option for its meaning.'}</div>
    </div>
  )
}

/** Links to other records. Courses are found by code or name; anything else is pasted as an address. */
function References({ prop, value, many, onChange, ctx }: { prop: FormProperty; value: unknown; many: boolean; onChange: (v: unknown) => void; ctx: EditContext }) {
  const [typed, setTyped] = useState('')
  const uris = list(value).map(String)
  const forCourses = prop.range.some((r) => ['ceterms:Course', 'ceterms:LearningOpportunityProfile'].includes(r))
  const needle = typed.trim().toLowerCase()
  const matches = useMemo(
    () => (forCourses && needle.length >= 2 ? ctx.courses.filter((c) => !uris.includes(c.uri) && `${c.code} ${c.name}`.toLowerCase().includes(needle)).slice(0, 7) : []),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [needle, forCourses, uris.join('|')],
  )
  const add = (uri: string) => (onChange(many ? [...uris, uri] : uri), setTyped(''))
  const name = (uri: string) => {
    const row = ctx.courses.find((c) => c.uri === uri)
    return row ? `${row.code} · ${row.name}` : ctx.references[uri]?.code ?? uri.replace(/^https?:\/\//, '')
  }
  const isAddress = /^https?:\/\/\S+$/.test(typed.trim())
  return (
    <div className="refs">
      {uris.map((u) => (
        <span key={u} className="ref" title={u}>
          {name(u)}
          <button aria-label="Remove" onClick={() => onChange(many ? uris.filter((x) => x !== u) : undefined)}>×</button>
        </span>
      ))}
      {(many || !uris.length) && (
        <span className="ref-add">
          <input className="in" value={typed} placeholder={forCourses ? 'Find a course by code or name, or paste an address' : 'Paste the address of its record'} onChange={(e) => setTyped(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && (isAddress ? add(typed.trim()) : matches[0] && add(matches[0].uri))} />
          {(matches.length > 0 || isAddress) && (
            <div className="pop options">
              {matches.map((c) => <button key={c.id} onClick={() => add(c.uri)}><span className="mono">{c.code}</span> {c.name}</button>)}
              {isAddress && <button onClick={() => add(typed.trim())}>Add this address</button>}
            </div>
          )}
        </span>
      )}
    </div>
  )
}

function Scalar({ kind, value, onChange, autoFocus }: { kind: Kind; value: unknown; onChange: (v: unknown) => void; autoFocus?: boolean }) {
  if (kind === 'number') return <input className="in num" type="number" step="any" autoFocus={autoFocus} value={value === undefined || value === '' ? '' : String(value)} onChange={(e) => onChange(e.target.value === '' ? '' : Number(e.target.value))} />
  if (kind === 'date') return <input className="in" type="date" value={String(value ?? '')} onChange={(e) => onChange(e.target.value)} />
  if (kind === 'boolean') return <label className="tick"><input type="checkbox" checked={!!value} onChange={(e) => onChange(e.target.checked)} /> Yes</label>
  if (kind === 'language') return <><input className="in short" list="xtra-languages" value={String(value ?? '')} placeholder="en" onChange={(e) => onChange(e.target.value)} /><datalist id="xtra-languages">{LANGUAGES.map((l) => <option key={l} value={l} />)}</datalist></>
  if (kind === 'url') return <input className="in" type="url" autoFocus={autoFocus} value={String(value ?? '')} placeholder="https://" onChange={(e) => onChange(e.target.value)} />
  return <Text value={String(value ?? '')} onChange={onChange} autoFocus={autoFocus} />
}

/** One profile written in place: its type, the details it has, and a way to add more. */
function SubForm({ prop, value, onChange, onRemove, ctx, depth }: { prop: FormProperty; value: Record<string, unknown>; onChange: (v: Record<string, unknown>) => void; onRemove?: () => void; ctx: EditContext; depth: number }) {
  const types = inPlace(prop, ctx.forms)
  const type = String(value['@type'] ?? types[0])
  const cls = ctx.forms.classes[type]
  const filled = Object.keys(value).filter((k) => k !== '@type')
  const rest = (cls?.properties ?? []).filter((p) => !filled.includes(p))
  const common = (COMMON[type] ?? []).filter((p) => rest.includes(p))
  const sorted = (terms: string[]) => [...terms].sort((a, b) => labelOf(a, ctx).localeCompare(labelOf(b, ctx)))
  return (
    <div className="subform">
      <div className="subform-head">
        {types.length > 1 ? (
          <select className="in type" value={type} title={cls?.definition} onChange={(e) => onChange({ ...value, '@type': e.target.value })}>
            {types.map((t) => <option key={t} value={t}>{ctx.forms.classes[t].label}</option>)}
          </select>
        ) : (
          <span className="type" title={cls?.definition}>{cls?.label ?? type}</span>
        )}
        <span className="sp" />
        {onRemove && <IconButton name="close" title="Remove this one" onClick={onRemove} />}
      </div>
      {filled.map((term) => (
        <Labelled key={term} term={term} ctx={ctx} onRemove={() => onChange(Object.fromEntries(Object.entries(value).filter(([k]) => k !== term)))}>
          <FieldEditor term={term} value={value[term]} onChange={(v) => onChange({ ...value, [term]: v })} ctx={ctx} depth={depth + 1} />
        </Labelled>
      ))}
      {rest.length > 0 && (
        <select className="add-detail" value="" onChange={(e) => e.target.value && onChange({ ...value, [e.target.value]: emptyFor(e.target.value, ctx) })}>
          <option value="">+ Add a detail…</option>
          {common.length > 0 && <optgroup label="Often used">{common.map((p) => <option key={p} value={p}>{labelOf(p, ctx)}</option>)}</optgroup>}
          <optgroup label="Everything CTDL allows here">{sorted(rest.filter((p) => !common.includes(p))).map((p) => <option key={p} value={p}>{labelOf(p, ctx)}</option>)}</optgroup>
        </select>
      )}
    </div>
  )
}

function Labelled({ term, ctx, onRemove, children }: { term: string; ctx: EditContext; onRemove?: () => void; children: ReactNode }) {
  const prop = ctx.forms.properties[term]
  return (
    <div className="lrow">
      <div className="lrow-label" title={prop ? `${prop.definition} (${term})` : term}>
        {labelOf(term, ctx)}
        {onRemove && <button className="lrow-x" title={`Remove “${labelOf(term, ctx)}”`} onClick={onRemove}>×</button>}
      </div>
      <div className="lrow-field">{children}</div>
    </div>
  )
}

/** The control for one property, chosen from what the schema says the property may hold. */
export function FieldEditor({ term, value, onChange, ctx, depth = 0, autoFocus }: { term: string; value: unknown; onChange: (v: unknown) => void; ctx: EditContext; depth?: number; autoFocus?: boolean }) {
  const prop = ctx.forms.properties[term]
  const kind = kindOf(prop, ctx.forms, value)
  const many = isMany(term, kind, value)

  if (kind === 'concept') return <Concepts prop={prop} value={value} many={many} onChange={onChange} ctx={ctx} />
  if (kind === 'reference') return <References prop={prop} value={value} many={many} onChange={onChange} ctx={ctx} />
  if (kind === 'text') {
    const map = isObject(value) ? value : { [LANG]: many ? list(value) : value ?? '' }
    const lang = Object.keys(map)[0] ?? LANG
    if (!many) return <Text value={String(map[lang] ?? '')} autoFocus={autoFocus} onChange={(v) => onChange({ ...map, [lang]: v })} />
    return <Rows items={list(map[lang]).map(String)} blank="" add="Add another" onChange={(v) => onChange({ ...map, [lang]: v })} render={(item, set) => <Text value={item} onChange={set} />} />
  }
  if (kind === 'object') {
    const blank = { '@type': inPlace(prop, ctx.forms)[0] }
    if (!many) return <SubForm prop={prop} value={isObject(value) ? value : blank} onChange={onChange} ctx={ctx} depth={depth} />
    const items = list(value).filter(isObject)
    return (
      <div className="rows">
        {items.map((item, i) => (
          <SubForm key={i} prop={prop} value={item} ctx={ctx} depth={depth} onChange={(v) => onChange(items.map((x, j) => (j === i ? v : x)))} onRemove={() => onChange(items.filter((_, j) => j !== i))} />
        ))}
        <button className="add" onClick={() => onChange([...items, blank])}><Icon name="plus" size={13} /> Add {items.length ? 'another' : 'one'}</button>
      </div>
    )
  }
  if (many) return <Rows items={list(value)} blank="" add="Add another" onChange={onChange} render={(item, set) => <Scalar kind={kind} value={item} onChange={set} />} />
  return <Scalar kind={kind} value={value} onChange={onChange} autoFocus={autoFocus} />
}

// ------------------------------------------------------------------------- one field of a record

type Props = {
  term: string // the property the value sits under, or "@type" for the record's own class
  value: unknown
  ctx: EditContext
  onSave: (value: unknown, property: string) => void
  onCancel: () => void
}

/** The whole editor for one card: the field it belongs under, its value, save and cancel. */
export function ValueEditor({ term, value, ctx, onSave, onCancel, fixed }: Props & { fixed?: boolean }) {
  const [draft, setDraft] = useState<unknown>(() => structuredClone(value))
  const [property, setProperty] = useState(term)
  const [raw, setRaw] = useState<string | null>(null)
  const { forms } = ctx
  const prop = forms.properties[term]

  // Fields that could hold this same value instead: a prerequisite could be a corequisite.
  const cousins = useMemo(() => {
    // A field being filled in from empty stays the field it is.
    if (!prop || fixed) return []
    const mine = inPlace(prop, forms)
    if (!mine.length || kindOf(prop, forms) !== 'object') return []
    return forms.classes[forms.root].properties.filter((p) => inPlace(forms.properties[p], forms).some((c) => mine.includes(c)))
  }, [prop, forms, fixed])

  // A requirement's label that only repeats its kind follows the kind; one worded differently is left alone.
  const move = (next: string) => {
    const was = labelOf(property, ctx)
    const relabel = (v: unknown): unknown => {
      if (Array.isArray(v)) return v.map(relabel)
      if (!v || typeof v !== 'object') return v
      const name = (v as Record<string, unknown>)['ceterms:name']
      if (!name || typeof name !== 'object') return v
      const renamed = Object.fromEntries(Object.entries(name).map(([lang, text]) => [lang, text === was ? labelOf(next, ctx) : text]))
      return { ...v, 'ceterms:name': renamed }
    }
    setDraft((old: unknown) => relabel(old))
    setProperty(next)
  }

  let broken = ''
  if (raw !== null) {
    try {
      JSON.parse(raw)
    } catch (e) {
      broken = (e as Error).message
    }
  }
  const result = broken ? undefined : prune(raw !== null ? JSON.parse(raw) : draft)
  // Not by colour alone: say in words when CTDL will not accept the field left empty.
  const needed = result === undefined && !broken && (forms.required.includes(term) || term === '@type')
  const save = () => !broken && !needed && onSave(result, property)

  return (
    <div
      className="editor"
      onClick={(e) => e.stopPropagation()}
      onKeyDown={(e) => {
        e.stopPropagation()
        if (e.key === 'Escape') onCancel()
        if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) save()
      }}
    >
      {term === '@type' ? (
        <div className="choices column" role="radiogroup">
          {forms.rootChoices.map((c) => (
            <button key={c.term} className={'choice wide' + (draft === c.term ? ' on' : '')} role="radio" aria-checked={draft === c.term} onClick={() => setDraft(c.term)}>
              <b>{c.label}</b> <span>{c.definition}</span>
            </button>
          ))}
        </div>
      ) : raw !== null ? (
        <>
          <textarea className="in mono" rows={Math.min(18, raw.split('\n').length + 1)} value={raw} onChange={(e) => setRaw(e.target.value)} />
          {broken && <div className="hint bad">This is not valid JSON yet: {broken}</div>}
        </>
      ) : (
        <>
          {cousins.length > 1 && (
            <div className="lrow">
              <div className="lrow-label">Kind</div>
              <div className="lrow-field">
                <select className="in" value={property} onChange={(e) => move(e.target.value)}>
                  {cousins.map((p) => <option key={p} value={p}>{labelOf(p, ctx)}</option>)}
                </select>
                <div className="hint">{forms.properties[property]?.definition}</div>
              </div>
            </div>
          )}
          <FieldEditor term={term} value={draft} onChange={setDraft} ctx={ctx} autoFocus />
        </>
      )}
      {needed && <div className="hint bad">CTDL requires this field on every course, so it cannot be left empty.</div>}
      <div className="editor-foot">
        {prop?.definition && <span className="hint clip" title={prop.definition}>{prop.definition}</span>}
        <span className="sp" />
        {term !== '@type' && (
          <IconButton name="code" title={raw === null ? 'For technical users: edit this value as JSON' : 'Back to the form'} on={raw !== null} onClick={() => (raw === null ? setRaw(JSON.stringify(draft, null, 2)) : !broken && (setDraft(JSON.parse(raw)), setRaw(null)))} />
        )}
        <button className="btn" onClick={onCancel}>Cancel</button>
        <button className="btn primary" disabled={!!broken || needed} onClick={save}>Save</button>
      </div>
    </div>
  )
}
