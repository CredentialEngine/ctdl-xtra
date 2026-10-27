// Pure helpers of the Records tab (spec §7.3): one course, every in-scope field as a card.
import type { CourseDetail, CourseField } from "../api/types";

export interface CardValue extends CourseField {
  occurrence_key: string; page_stem: string; page_title: string | null; url: string; on_course_page: boolean;
}
export interface Card { n: number; property: string; ctdl_property: string | null; values: CardValue[] }

/** Group a course's fields by property across its occurrences (course page first), numbered in order. */
export function groupCards(d: CourseDetail): Card[] {
  const cards: Card[] = [];
  const by = new Map<string, Card>();
  for (const o of d.occurrences) {
    for (const f of o.fields) {
      const property = f.property_label ?? f.rule_id;
      let card = by.get(property);
      if (!card) {
        card = { n: 0, property, ctdl_property: f.ctdl_property, values: [] };
        by.set(property, card);
        cards.push(card);
      }
      card.values.push({ ...f, occurrence_key: o.occurrence_key, page_stem: o.page_stem, page_title: o.page_title,
                         url: o.url, on_course_page: o.locator_rule_id === "locator-course-page" });
    }
  }
  cards.forEach((c, i) => { c.n = i + 1; });
  return cards;
}

/** "Found on 2 pages: its course page and 1 program page that lists it". */
export function foundOn(d: CourseDetail): string {
  const pages = new Map<string, boolean>();
  for (const o of d.occurrences) pages.set(o.page_stem, (pages.get(o.page_stem) ?? false) || o.locator_rule_id === "locator-course-page");
  const n = pages.size;
  const course = [...pages.values()].filter(Boolean).length;
  const prog = n - course;
  const parts: string[] = [];
  if (course) parts.push(course === 1 ? "its course page" : `${course} course pages`);
  if (prog) parts.push(`${prog} program page${prog > 1 ? "s" : ""} that list${prog > 1 ? "" : "s"} it`);
  return `Found on ${n} page${n === 1 ? "" : "s"}: ${parts.join(" and ")}`;
}

/** The heading: "GEOG 222 · Cartography for Geographic Information Science (GIS)". */
export function courseHeading(cards: Card[], courseKey: string): string {
  const val = (prop: string) => cards.find((c) => c.ctdl_property === prop)?.values.find((v) => v.value)?.value ?? null;
  const code = val("ceterms:codedNotation") ?? courseKey;
  const name = val("ceterms:name");
  return name ? `${code} · ${name}` : code;
}

export const valueKey = (v: { rule_id: string; occurrence_key: string }) => `${v.rule_id}|${v.occurrence_key}`;
