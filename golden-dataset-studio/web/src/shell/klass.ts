// The class every API call is for (LearningProgram spec, items 11 and 15): the class the address bar names; with
// All classes, the class of the item on screen (a rule's id says it: `learningprogram-name`; a record's `?in=`),
// else Course. A view that shows every class at once asks per class with `inClass(cls, () => api.x(…))`.
import { CLASS_SLUGS, parseRoute, type ClassSlug } from "./router";

let scoped: ClassSlug | null = null;

/** The class a rule belongs to, from its id (`learningprogram-name`, `locator-learningprogram-page`); null when the
 * id names none (Course's older page rules and locators: `course-page`, `program-page`). */
export function classOfRule(id: string | null | undefined): ClassSlug | null {
  if (!id) return null;
  return CLASS_SLUGS.find((c) => c !== "course" && (id.startsWith(`${c}-`) || id.includes(`-${c}-`) || id.endsWith(`-${c}`)))
    ?? (id.startsWith("course-") || id.includes("-course-") ? "course" : null);
}

export function apiClass(): ClassSlug {
  if (scoped) return scoped;
  const r = parseRoute(location.hash);
  if (r.cls !== "all") return r.cls;
  const inn = r.params.get("in");
  if (inn && (CLASS_SLUGS as string[]).includes(inn)) return inn as ClassSlug;
  return (r.tab === "rules" && classOfRule(r.id)) || "course";
}

/** What a class's records are called: Course's courses, LearningProgram's programs. */
export const NOUN: Record<ClassSlug, [string, string]> = { course: ["course", "courses"], learningprogram: ["program", "programs"] };
export const recordNoun = (cls: ClassSlug = apiClass()) => NOUN[cls];

/** `f()`'s API calls are for `cls` (their paths are built before the first await). */
export function inClass<T>(cls: ClassSlug, f: () => T): T {
  const before = scoped;
  scoped = cls;
  try { return f(); } finally { scoped = before; }
}

/** A catalog API path with its class (`?class=`), unless it names one already. Course is the server's default, so a
 * Course call stays as it always was. */
export function withClass(path: string): string {
  if (!path.startsWith("/api/catalogs/") || /[?&]class=/.test(path)) return path;
  const cls = apiClass();
  return cls === "course" ? path : `${path}${path.includes("?") ? "&" : "?"}class=${cls}`;
}
