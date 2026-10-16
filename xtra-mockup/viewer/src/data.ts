import type { Course, CourseRow, DocMeta, Forms, Rules, Teaching } from './types'

const cache = new Map<string, Promise<unknown>>()

function get<T>(file: string, as: 'json' | 'text' = 'json'): Promise<T> {
  if (!cache.has(file)) {
    cache.set(
      file,
      fetch(`data/${file}`).then((r) => {
        if (!r.ok) throw new Error(`${file}: ${r.status}`)
        return as === 'json' ? r.json() : r.text()
      }),
    )
  }
  return cache.get(file) as Promise<T>
}

export const loadCourses = () => get<CourseRow[]>('courses.json')
export const loadDocuments = () => get<Record<string, DocMeta>>('documents.json')
export const loadTeaching = () => get<Teaching>('teaching.json')
export const loadForms = () => get<Forms>('forms.json')
export const loadRules = () => get<Rules>('rules.json')
export const loadCourse = (id: string) => get<Course>(`courses/${id}.json`)
export const loadDocumentText = (meta: DocMeta) => get<string>(meta.file, 'text')

/** A stored page parsed apart from the screen, for the HTML view and for excerpts. */
const parsed = new Map<string, Promise<Document>>()
export function loadParsed(meta: DocMeta): Promise<Document> {
  if (!parsed.has(meta.digest)) {
    parsed.set(meta.digest, loadDocumentText(meta).then((html) => new DOMParser().parseFromString(html, 'text/html')))
  }
  return parsed.get(meta.digest)!
}
