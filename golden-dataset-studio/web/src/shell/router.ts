// Hash routes: #/ (catalog picker) · #/c/<catalog>/<class>/<tab>/<id>?<params> (LearningProgram spec, item 11)
// <class> is a class slug (course, learningprogram) or `all` (All classes).
// Examples: #/c/avc/course/rules/course-description?row=<occurrence_key> · #/c/avc/course/records/GEOG222
//           #/c/avc/course/compare?a=1&b=2&rule=course-description · #/c/wvu/all/datasets
// A link from before classes (#/c/avc/rules/…) isn't kept: it opens the catalog's Course rules. The old Prompt tab
// (#/c/avc/<class>/prompt…) opens the Rules tab with the prompt modal (?prompt=1).
import { useEffect, useState } from "react";

export type Tab = "rules" | "records" | "compare" | "datasets" | "evals";
export const TABS: Tab[] = ["rules", "records", "compare", "datasets", "evals"];
export const TAB_LABEL: Record<Tab, string> = { rules: "Rules", records: "Records", compare: "Compare", datasets: "Datasets",
                                                evals: "Evals" };
/** Old tab names still open the right tab (the Publish tab, then Golden datasets, are now Datasets). */
const RENAMED: Record<string, Tab> = { publish: "datasets", golden: "datasets" };

/** A CTDL class (its slug), or `all`: the class menu's choice, which every tab to its right follows. */
export type ClassSlug = "course" | "learningprogram";
export type ClassSel = ClassSlug | "all";
export const CLASS_SLUGS: ClassSlug[] = ["course", "learningprogram"];
export const CLASS_NAME: Record<ClassSel, string> = { course: "Course", learningprogram: "LearningProgram", all: "All classes" };

export interface Route { catalog: string | null; cls: ClassSel; tab: Tab; id: string | null; params: URLSearchParams }

export function parseRoute(hash: string): Route {
  const h = hash.replace(/^#/, "") || "/";
  const [path, qs] = h.split("?");
  const p = path.split("/").filter(Boolean).map(decodeURIComponent);
  const params = new URLSearchParams(qs || "");
  if (p[0] !== "c" || !p[1]) return { catalog: null, cls: "course", tab: "rules", id: null, params };
  const cls = p[2] as ClassSel;
  if (!(CLASS_SLUGS as string[]).includes(cls) && cls !== "all")  // a link from before classes: not kept
    return { catalog: p[1], cls: "course", tab: "rules", id: null, params: new URLSearchParams() };
  if (p[3] === "prompt") {  // the Prompt tab became a modal over the Rules tab
    params.delete("rule");
    params.set("prompt", "1");
    return { catalog: p[1], cls, tab: "rules", id: null, params };
  }
  const name = RENAMED[p[3]] ?? p[3];
  const tab = (TABS as string[]).includes(name) ? (name as Tab) : "rules";
  return { catalog: p[1], cls, tab, id: p[4] ?? null, params };
}

/** The class the address bar names now (Course on the picker). */
export function currentClass(): ClassSel {
  return parseRoute(location.hash).cls;
}

/** A tab's address. `cls`: the class (default: the one the address bar names now). */
export function href(catalog: string, tab: Tab, id?: string | null, params?: Record<string, string | number | null | undefined>,
                     cls?: ClassSel): string {
  let h = `#/c/${encodeURIComponent(catalog)}/${cls ?? currentClass()}/${tab}`;
  if (id) h += `/${encodeURIComponent(id)}`;
  const s = new URLSearchParams();
  for (const [k, v] of Object.entries(params ?? {})) if (v !== null && v !== undefined && v !== "") s.set(k, String(v));
  const t = s.toString();
  return t ? `${h}?${t}` : h;
}

export function go(h: string, replace = false): void {
  if (replace) history.replaceState(null, "", h);
  else location.hash = h.replace(/^#/, "");
  if (replace) window.dispatchEvent(new HashChangeEvent("hashchange"));
}

/** Set one query parameter of the current route in the address bar with `history.replaceState` (no new history entry,
 * no hashchange: the tab keeps what it shows). The Rules tab writes `?row=` this way as rows are selected (sme-fixes §2). */
export function replaceParam(name: string, value: string | null): void {
  const h = location.hash.replace(/^#/, "") || "/";
  const [path, qs] = h.split("?");
  const s = new URLSearchParams(qs || "");
  if (value === null || value === "") s.delete(name); else s.set(name, value);
  const t = s.toString();
  const next = `#${path}${t ? `?${t}` : ""}`;
  if (next !== location.hash) history.replaceState(history.state, "", next);
}

export function useRoute(): Route {
  const [route, setRoute] = useState(() => parseRoute(location.hash));
  useEffect(() => {
    const on = () => setRoute(parseRoute(location.hash));
    window.addEventListener("hashchange", on);
    return () => window.removeEventListener("hashchange", on);
  }, []);
  return route;
}
