// What the home page shows, kept in the address (#/?v=score&cls=course&c=wvu&p=course:name&rows=props&n=1):
// the view, the ticked classes (all when none is named), the catalog (all when none), the ticked properties
// (`class:column`, all when none), the rows of the all-catalogs score view, and Bars or Numbers.
import { CLASS_SLUGS, go, type ClassSlug } from "../shell/router";

export interface HomeState {
  view: "golden" | "score";
  classes: ClassSlug[];
  catalog: string | null;
  props: Set<string> | null;
  rows: "catalogs" | "properties";
  numbers: boolean;
}

export function readHome(p: URLSearchParams): HomeState {
  const cls = (p.get("cls") ?? "").split(",").filter((c): c is ClassSlug => (CLASS_SLUGS as string[]).includes(c));
  const props = p.get("p");
  return {
    view: p.get("v") === "score" ? "score" : "golden",
    classes: cls.length ? CLASS_SLUGS.filter((c) => cls.includes(c)) : [...CLASS_SLUGS],
    catalog: p.get("c") || null,
    props: props ? new Set(props.split(",").filter(Boolean)) : null,
    rows: p.get("rows") === "props" ? "properties" : "catalogs",
    numbers: p.get("n") === "1",
  };
}

export function homeHref(s: HomeState): string {
  const q = new URLSearchParams();
  if (s.view === "score") q.set("v", "score");
  if (s.classes.length < CLASS_SLUGS.length) q.set("cls", s.classes.join(","));
  if (s.view === "score") {
    if (s.catalog) q.set("c", s.catalog);
    if (s.props) q.set("p", [...s.props].join(","));
    if (s.rows === "properties") q.set("rows", "props");
    if (s.numbers) q.set("n", "1");
  }
  const t = q.toString();
  return `#/${t ? `?${t}` : ""}`;
}

export const goHome = (s: HomeState) => go(homeHref(s), true);
