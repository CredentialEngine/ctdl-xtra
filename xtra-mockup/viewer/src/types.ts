// The extract step's output, as the viewer reads it. The viewer writes nothing back.

export type Segment = { start: number; end: number; quote: string; before: string; after: string }

export type Evidence = {
  n: number
  kind: 'text' | 'markup' | 'record' | 'derived' | 'address' | 'none'
  role: string
  says: string
  document?: string
  rule?: string | null
  segments?: Segment[]
  element?: string
  attribute?: string | null
  source?: { start: number; end: number; quote: string; of: string }
  address?: string
  readAt?: string
  fields?: { path: string; value: unknown }[]
  from?: string
  step?: string
  result?: string
  table?: string | null
  matched?: { start: number; end: number; text: string; parts: { name: string; start: number; end: number }[] }
}

export type Check = { id?: string; text: string; status: 'pass' | 'fail' | 'note'; detail?: string | string[] }
export type Flag = { id: string; text: string }
export type Level = 'brief' | 'standard' | 'full'
export type Confidence = { level: 'low' | 'medium' | 'high'; why: string }

export type TreeNode = {
  kind: 'all_of' | 'any_of' | 'course' | 'text'
  start: number
  end: number
  quote: string
  code?: string
  uri?: string
  hasRecord?: boolean
  landed?: { path: string; how: string }
  children?: TreeNode[]
}

export type Structure = {
  sentence: Segment
  builtBy: 'parser' | 'language model' | 'nobody'
  tree: TreeNode | null
  guards: Check[]
  partlyStructured: boolean
  summary: string
  languageModel?: { name: string; promptVersion: string; argument: string }
  discarded?: { structure: unknown; argument: string }
}

export type Entry = {
  slot: string
  method: string
  producedBy: string
  how: string
  evidence: Evidence[]
  checks: Check[]
  flags: Flag[]
  confidence: Confidence
  judgement: boolean
  chip?: string
  choiceOnly?: boolean
  concept?: string
  scheme?: string
  structure?: Structure[]
  normalised?: string
  unstable?: boolean
}

export type Course = {
  id: string
  code: string
  subject: string
  ordinal: number
  documents: string[]
  block: { document: string; start: number; end: number }
  record: Record<string, unknown>
  provenance: Record<string, Entry>
  leftOut: { what: string; reason: string; rule: string; segment: Segment; document: string }[]
  references: Record<string, { code: string; hasRecord: boolean }>
  conformance: Check[]
  unstableTerms: string[]
}

export type CourseRow = {
  id: string
  code: string
  name: string
  uri: string
  subject: string
  credit: string
  requirements: 'none' | 'parser' | 'language model' | 'nobody'
  flags: string[]
  checksFailed: number
  stops: number
  judgementCalls: number
  lowConfidence: number
}

export type DocMeta = {
  digest: string
  role: 'subject' | 'index' | 'registry'
  name: string
  kind: 'page' | 'record'
  address: string
  finalAddress: string
  fetchedAt: string
  status: number
  contentType: string
  size: number
  current: boolean
  file: string
  title?: string
  textLength?: number
  textSha256?: string
}

export type Term = {
  term: string
  label: string
  kind: string
  definition: string
  page: string
  unstable: boolean
  note?: string
  usageNote?: string
  range?: string[]
  scheme?: string
}
export type Scheme = Term & { concepts: { term: string; label: string; definition: string }[] }

export type Slot = {
  label: string
  term?: string
  plain?: string
  choice: string
  examples?: string
  options?: string
  alternatives: { name: string; why_not: string }[]
  ctdl?: Term
}

export type Teaching = {
  schemaCopyDate: string
  slots: Record<string, Slot>
  schemes: Record<string, Scheme>
  glossary: { term: string; text: string; example: string }[]
}

export type RuleInfo = { name: string; feeds: string; where: string; wherePlain: string; pattern: string; description: string; expect: string; leftOutReason?: string }
export type Rules = { rules: RuleInfo[]; tables: TableInfo[]; phrases: { text: string; role: string }[] }
export type TableInfo = { name: string; feeds: string; scheme: string; description: string; rows: { wording: string; concept: string; because: string; loses: string; reviewedByAPerson: boolean }[] }

// What a person has done to one field. Kept in this browser only; there is no backend.
export type Review = {
  accepted?: boolean
  rejected?: boolean
  comment?: string // what the reviewer wrote: the reason for a rejection, or a note left in passing
  value?: unknown // the edited value, as it would be written; null means removed
  property?: string // the field it was moved to, if it was moved
  segments?: { document: string; start: number; end: number; quote: string }[]
}

// What an editing form needs to know about CTDL, read from the schema copy by the extract step.
export type FormProperty = { term: string; label: string; definition: string; range: string[]; languageText: boolean; datatype?: string; unstable: boolean; scheme?: string; page?: string; note?: string; usageNote?: string }
/** One term of the CTDL schema copy, in full, as its page on credreg.net lays it out. */
export type TermDoc = {
  term: string
  uri: string
  page: string
  label: string
  definition: string
  type: string
  status?: string
  history?: string
  standAlone?: boolean
  comment?: string
  usageNote?: string
  domainIncludes?: string[]
  rangeIncludes?: string[]
  subClassOf?: string[]
  subPropertyOf?: string[]
  equivalentClass?: string[]
  equivalentProperty?: string[]
  inverseOf?: string[]
  targetScheme?: string[]
  domainFor?: string[]
  hasConcept?: string[]
  inScheme?: string[]
  broader?: string[]
  narrower?: string[]
  relatedMatch?: string[]
  narrowMatch?: string[]
}
export type Forms = {
  terms?: Record<string, TermDoc>
  prefixes?: Record<string, string>
  root: string
  rootChoices: { term: string; label: string; definition: string }[]
  required: string[]
  requiredOneOf: string[]
  classes: Record<string, { term: string; label: string; definition: string; properties: string[]; page?: string }>
  others?: Record<string, { term: string; label: string; definition: string; page: string }>
  properties: Record<string, FormProperty>
  schemes: Record<string, Scheme>
  standAlone: string[]
}
