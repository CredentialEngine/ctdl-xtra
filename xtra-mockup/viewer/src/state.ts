import { useCallback, useEffect, useState } from 'react'
import type { Level, Review } from './types'

export type Route = {
  course: string | null
  stop: string | null
  level: Level
  view: 'fields' | 'json'
  walk: 'everything' | 'judgement'
}

const remembered = <T extends string>(key: string, allowed: readonly T[], fallback: T): T => {
  const v = localStorage.getItem(key) as T | null
  return v && allowed.includes(v) ? v : fallback
}
const LEVELS = ['brief', 'standard', 'full'] as const
const VIEWS = ['fields', 'json'] as const
// Raw is the view for someone who wants everything, so its reasoning opens in full; Pretty starts bare.
const LEVEL_KEY = { fields: 'xtra-level', json: 'xtra-level-raw' } as const
const LEVEL_DEFAULT = { fields: 'brief', json: 'full' } as const
const levelFor = (view: 'fields' | 'json') => remembered(LEVEL_KEY[view], LEVELS, LEVEL_DEFAULT[view])
const WALKS = ['everything', 'judgement'] as const

/** The address reflects the course, the stop and the level of detail, so a view can be bookmarked (WK9). */
export function readRoute(): Route {
  const [path, query = ''] = location.hash.replace(/^#/, '').split('?')
  const q = new URLSearchParams(query)
  const pick = <T extends string>(name: string, allowed: readonly T[], fallback: T) =>
    allowed.includes(q.get(name) as T) ? (q.get(name) as T) : fallback
  const parts = path.split('/').filter(Boolean)
  const view = pick('view', VIEWS, remembered('xtra-view', VIEWS, 'fields'))
  return {
    course: parts[0] === 'course' ? decodeURIComponent(parts[1] ?? '') || null : null,
    stop: q.get('stop'),
    level: pick('level', LEVELS, levelFor(view)),
    view,
    walk: pick('walk', WALKS, 'everything'),
  }
}

export function writeRoute(r: Route, replace = true): void {
  const q = new URLSearchParams()
  if (r.stop) q.set('stop', r.stop)
  if (r.level !== LEVEL_DEFAULT[r.view]) q.set('level', r.level)
  if (r.view !== 'fields') q.set('view', r.view)
  if (r.walk !== 'everything') q.set('walk', r.walk)
  const query = q.toString().replace(/%2F/g, '/').replace(/%3A/g, ':')
  const hash = `#/course/${r.course ?? ''}${query ? '?' + query : ''}`
  localStorage.setItem(LEVEL_KEY[r.view], r.level)
  localStorage.setItem('xtra-view', r.view)
  if (hash !== location.hash) (replace ? history.replaceState : history.pushState).call(history, null, '', hash)
}

export function useRoute(): [Route, (patch: Partial<Route>, push?: boolean) => void] {
  const [route, setRoute] = useState(readRoute)
  useEffect(() => {
    const onChange = () => setRoute(readRoute())
    window.addEventListener('hashchange', onChange)
    window.addEventListener('popstate', onChange)
    return () => {
      window.removeEventListener('hashchange', onChange)
      window.removeEventListener('popstate', onChange)
    }
  }, [])
  const update = useCallback((patch: Partial<Route>, push = false) => {
    setRoute((old) => {
      const next = { ...old, ...patch }
      if (patch.view && patch.view !== old.view && !patch.level) next.level = levelFor(patch.view)
      writeRoute(next, !push)
      return next
    })
  }, [])
  return [route, update]
}

// --- what a person has accepted, edited or re-attributed. Kept in this browser only. ---------

type Reviews = Record<string, Record<string, Review>>
const KEY = 'xtra-reviews'
const readReviews = (): Reviews => {
  try {
    const stored: Reviews = JSON.parse(localStorage.getItem(KEY) ?? '{}')
    // A rejection's reason was once kept under its own name; it is the field's comment now.
    for (const course of Object.values(stored)) {
      for (const r of Object.values(course) as (Review & { reason?: string })[]) {
        if (r.reason !== undefined) ((r.comment ??= r.reason), delete r.reason)
        if (r.rejected && !r.comment) r.comment = 'No reason was given.'
      }
    }
    return stored
  } catch {
    return {}
  }
}

export function useReviews() {
  const [all, setAll] = useState<Reviews>(readReviews)
  const change = useCallback((course: string, path: string, fn: (r: Review) => Review) => {
    setAll((old) => {
      const forCourse = { ...(old[course] ?? {}) }
      const next = fn(forCourse[path] ?? {})
      if (!next.accepted && !next.rejected && !next.comment && next.value === undefined && !next.property && !next.segments?.length) delete forCourse[path]
      else forCourse[path] = next
      const out = { ...old, [course]: forCourse }
      if (!Object.keys(forCourse).length) delete out[course]
      localStorage.setItem(KEY, JSON.stringify(out))
      return out
    })
  }, [])
  return { all, change }
}

/** Accepting and rejecting are the two verdicts on a field; giving one withdraws the other. A rejection
 *  always carries a comment, its reason, which goes when the rejection goes. A comment by itself is a
 *  third way of dealing with a field: it has been looked at, and something was said about it. */
export const toggleAccept = (r: Review): Review => ({ ...r, accepted: !r.accepted, rejected: undefined, comment: r.rejected ? undefined : r.comment })
export const rejectWith = (r: Review, reason: string): Review => ({ ...r, rejected: true, comment: reason, accepted: undefined })
export const unreject = (r: Review): Review => ({ ...r, rejected: undefined, comment: undefined })
export const isDecided = (r: Review | undefined): boolean => !!r && (!!r.accepted || !!r.rejected || !!r.comment)
