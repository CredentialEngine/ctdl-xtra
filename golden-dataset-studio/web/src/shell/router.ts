// Hash routes: #/ (catalog picker) · #/c/<catalog>/<tab>/<id>?<params>
// Examples: #/c/avc/rules/course-description?row=<occurrence_key> · #/c/avc/records/GEOG222
//           #/c/avc/compare?a=1&b=2&rule=course-description · #/c/avc/golden
// The old Prompt tab (#/c/avc/prompt…) opens the Rules tab with the prompt modal (?prompt=1).
import { useEffect, useState } from "react";

export type Tab = "rules" | "records" | "compare" | "golden" | "evals";
export const TABS: Tab[] = ["rules", "records", "compare", "golden", "evals"];
export const TAB_LABEL: Record<Tab, string> = { rules: "Rules", records: "Records", compare: "Compare", golden: "Golden datasets",
                                                evals: "Evals" };
/** Old tab names still open the right tab (the Publish tab is now Golden datasets). */
const RENAMED: Record<string, Tab> = { publish: "golden" };

export interface Route { catalog: string | null; tab: Tab; id: string | null; params: URLSearchParams }

export function parseRoute(hash: string): Route {
  const h = hash.replace(/^#/, "") || "/";
  const [path, qs] = h.split("?");
  const p = path.split("/").filter(Boolean).map(decodeURIComponent);
  const params = new URLSearchParams(qs || "");
  if (p[0] !== "c" || !p[1]) return { catalog: null, tab: "rules", id: null, params };
  if (p[2] === "prompt") {  // the Prompt tab became a modal over the Rules tab
    params.delete("rule");
    params.set("prompt", "1");
    return { catalog: p[1], tab: "rules", id: null, params };
  }
  const name = RENAMED[p[2]] ?? p[2];
  const tab = (TABS as string[]).includes(name) ? (name as Tab) : "rules";
  return { catalog: p[1], tab, id: p[3] ?? null, params };
}

export function href(catalog: string, tab: Tab, id?: string | null, params?: Record<string, string | number | null | undefined>): string {
  let h = `#/c/${encodeURIComponent(catalog)}/${tab}`;
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

export function useRoute(): Route {
  const [route, setRoute] = useState(() => parseRoute(location.hash));
  useEffect(() => {
    const on = () => setRoute(parseRoute(location.hash));
    window.addEventListener("hashchange", on);
    return () => window.removeEventListener("hashchange", on);
  }, []);
  return route;
}
