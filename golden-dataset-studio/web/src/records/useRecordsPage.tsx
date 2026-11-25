// The Records tab's state: the address, the record list, the open record's cards, the page pane and the verdicts.
import { useCallback, useEffect, useMemo, useRef, useState, type Dispatch, type RefObject, type SetStateAction } from "react";
import { api } from "../api/client";
import type { CatalogDetail, ClassSummary, CourseDetail, EventBrief, NewEvent } from "../api/types";
import type { Highlight } from "../pagepane";
import { apiX, type Annotators, type CourseHitX } from "../rules/api";
import {
  applyEvent, applyReview, briefOf, canConfirm, isField, keyAction, newDraft, scrollWithin, shortTitle, verdictEvent, type Draft,
} from "../rules/logic";
import { useReviewer, useRole, type Role } from "../shell/reviewer";
import { go, href, type ClassSel, type ClassSlug, type Route } from "../shell/router";
import { toast, useKeyHints } from "../shell/ui";
import { groupCards, splitCards, valueKey, type Card, type CardValue } from "./logic";
import { inClass, recordNoun } from "../shell/klass";

export type RecordsPage = ReturnType<typeof useRecordsPage>;
type Address = ReturnType<typeof readAddress>;
type Selection = ReturnType<typeof useSelection>;
type Cards = ReturnType<typeof useCards>;
type Entry = { card: Card; v: CardValue };
type Verdict = { verdict: "correct" } | { draft: Draft };
type Pick = "correct" | "wrong" | "comment";
interface SaveRequest {
  cat: string; me: string; role: Role | null; v: CardValue; what: Verdict;
  patch: (v: CardValue, ev: EventBrief) => void; setDraft: (d: Draft | null) => void;
}

const HINTS = (
  <span className="key-hints"><kbd>1</kbd>correct <kbd>2</kbd>wrong <kbd>3</kbd>comment <kbd>Enter</kbd>save{" "}
    <kbd>Esc</kbd>cancel · same verdicts as the Rules tab</span>
);

export function useRecordsPage(catalog: CatalogDetail, route: Route) {
  const address = readAddress(catalog.short, route);
  const me = useReviewer();
  const role = useRole();
  const selection = useSelection();
  useKeyHints(HINTS, []);
  const list = useRecordList(catalog, route.cls, address);
  const record = useRecord(address, selection, list.setError);
  const cards = useCards(record.course, address, selection, list.error);
  const cardsRef = useScrollToSelection(list, address.recordKey, selection.sel, record.course);
  const pane = usePane(record.course, cards, selection);
  const actions = useVerdicts(address.cat, me, role, record.setCourse, selection);
  useVerdictKeys((e) => handleVerdictKey(e, cards, selection, actions));
  return { catalog, address, me, role, selection, list, record, cards, cardsRef, pane, actions };
}

function readAddress(cat: string, route: Route) {
  const by = route.params.get("by");
  // with All classes, every class's records, a folding heading per class (approved item 16)
  const allCls = route.cls === "all";
  const openCls = (route.params.get("in") as ClassSlug | null) ?? (allCls ? null : (route.cls as ClassSlug));
  return {
    cat, by, allCls, openCls, recordKey: route.id,
    wantProp: route.params.get("prop") ?? (by ? null : "Description"),
    wantOcc: route.params.get("occ"),
    noun: recordNoun(allCls ? (openCls ?? "course") : (route.cls as ClassSlug)),
  };
}

function useSelection() {
  const [sel, setSel] = useState<string | null>(null);
  const [draft, setDraft] = useState<Draft | null>(null);
  const [activeStem, setActiveStem] = useState<string | null>(null);
  const [showAll, setShowAll] = useState(false);
  const select = useCallback((key: string) => { setSel(key); setDraft(null); setActiveStem(null); }, []);
  const resetForRecord = useCallback(() => { setDraft(null); setActiveStem(null); setShowAll(false); }, []);
  return { sel, setSel, draft, setDraft, activeStem, setActiveStem, showAll, setShowAll, select, resetForRecord };
}

function useRecordList(catalog: CatalogDetail, cls: ClassSel, address: Address) {
  const [q, setQ] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [shut, setShut] = useState<Record<string, boolean>>({});
  const listRef = useRef<HTMLDivElement>(null);
  const people = useAnnotators(address.cat);
  const ruled = useMemo(() => (catalog.classes ?? []).filter((c) => c.ruleset_version), [catalog.classes]);
  const { hits, listLoading } = useHits({ address, cls, q, ruled, error, setError });
  useOpenFirstRecord(address, hits, q, ruled);
  return { q, setQ, error, setError, shut, setShut, listRef, people, ruled, hits, listLoading };
}

function useAnnotators(cat: string): Annotators | null {
  const [people, setPeople] = useState<Annotators | null>(null);
  useEffect(() => { apiX.annotators(cat).then(setPeople, () => setPeople(null)); }, [cat]);
  return people;
}

function useHits({ address: { cat, by, allCls }, cls, q, ruled, error, setError }: {
  address: Address; cls: ClassSel; q: string; ruled: ClassSummary[]; error: string | null; setError: (e: string) => void;
}) {
  const [hits, setHits] = useState<CourseHitX[] | null>(null);
  // the list belongs to one catalog and class: after a switch, a loading preview shows until that list arrives
  // (typing a search keeps the current list; only a switch clears it)
  const listKey = `${cat}|${cls}`;
  const [hitsFor, setHitsFor] = useState<string | null>(null);
  const ruledKey = ruled.map((c) => c.slug).join(",");
  useEffect(() => {
    let live = true;
    const show = (h: CourseHitX[]) => { if (live) { setHits(h); setHitsFor(listKey); } };
    const t = window.setTimeout(() => findRecords(cat, q, by, allCls ? ruled : null).then(show, (e) => setError(String(e))), q ? 120 : 0);
    return () => { live = false; window.clearTimeout(t); };
  }, [cat, q, by, allCls, ruledKey, listKey, setError]);
  return { hits, listLoading: hitsFor !== listKey && !error };
}

function findRecords(cat: string, q: string, by: string | null, classes: ClassSummary[] | null): Promise<CourseHitX[]> {
  if (!classes) return apiX.courses(cat, q || undefined, by);
  return Promise.all(classes.map((c) => inClass(c.slug, () => apiX.courses(cat, q || undefined, by))
    .then((hs) => hs.map((h) => ({ ...h, cls: c.slug }))))).then((xs) => xs.flat());
}

// no record in the address yet: open the first one in the list
function useOpenFirstRecord({ cat, by, recordKey, allCls, openCls }: Address, hits: CourseHitX[] | null, q: string,
                            ruled: ClassSummary[]) {
  useEffect(() => {
    if (recordKey || !hits || !hits.length || q) return;
    const h = hits.find((x) => !allCls || x.cls === (openCls ?? ruled[ruled.length - 1]?.slug)) ?? hits[0];
    go(href(cat, "records", h.record_external_identifier, { by, in: allCls ? h.cls : null }), true);
  }, [recordKey, hits, q, cat, by]);
}

function useRecord({ cat, recordKey, openCls }: Address, { resetForRecord }: Selection, setError: (e: string | null) => void) {
  const [course, setCourse] = useState<CourseDetail | null>(null);
  useEffect(() => {
    if (!recordKey) return;
    let live = true;
    resetForRecord();
    api.course(cat, recordKey).then((d) => { if (live) { setCourse(d); setError(null); } },
      (e) => { if (live) { setCourse(null); setError(String(e)); } });
    return () => { live = false; };
  }, [cat, recordKey, openCls, resetForRecord, setError]);
  return { course, setCourse };
}

function useCards(course: CourseDetail | null, { recordKey, by, wantProp, wantOcc }: Address, selection: Selection,
                  error: string | null) {
  const all = useMemo(() => (course ? groupCards(course) : []), [course]);
  // the record in the address hasn't arrived yet (another record, or a class switch): placeholders, not the last one
  const recordLoading = !!recordKey && !error && course?.record_external_identifier !== recordKey;
  // the pages the record's values come from: only when there are several does each card say which (approved item 16)
  const pages = useMemo(() => new Set(course?.occurrences.map((o) => o.page_stem) ?? []).size, [course]);
  const { mine, folded } = useMemo(() => splitCards(all, by), [all, by]);
  const cards = useMemo(() => (selection.showAll ? [...mine, ...folded] : mine), [mine, folded, selection.showAll]);
  useSelectWantedValue(cards, wantProp, wantOcc, selection.setSel);
  const flat = useMemo(() => cards.flatMap((c) => c.values.map((v) => ({ card: c, v }))), [cards]);
  const cur: Entry | null = flat.find((x) => valueKey(x.v) === selection.sel) ?? flat[0] ?? null;
  return { all, recordLoading, pages, folded, cards, flat, cur };
}

function useSelectWantedValue(cards: Card[], wantProp: string | null, wantOcc: string | null,
                              setSel: (key: string) => void) {
  useEffect(() => {
    if (!cards.length) return;
    const card = cards.find((c) => c.property === wantProp) ?? cards[0];
    // the entry the Rules tab came from (a course can be on several pages), else the first
    setSel(valueKey(card.values.find((v) => v.occurrence_key === wantOcc) ?? card.values[0]));
  }, [cards, wantProp, wantOcc, setSel]);
}

function useScrollToSelection(list: { listRef: RefObject<HTMLDivElement>; hits: CourseHitX[] | null },
                              recordKey: string | null, sel: string | null, course: CourseDetail | null) {
  useScrollListToRecord(list.listRef, list.hits, recordKey);
  return useScrollToSelectedCard(sel, course);
}

function useScrollListToRecord(listRef: RefObject<HTMLDivElement>, hits: CourseHitX[] | null, recordKey: string | null) {
  useEffect(() => {
    const box = listRef.current;
    const el = box?.querySelector<HTMLElement>(".course-item.on");
    if (box && el) scrollWithin(box, el, false);
  }, [hits, recordKey, listRef]);
}

function useScrollToSelectedCard(sel: string | null, course: CourseDetail | null) {
  const cardsRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const box = cardsRef.current;
    const el = box?.querySelector<HTMLElement>(".v.on")?.closest<HTMLElement>(".card");
    if (box && el) box.scrollTop = el.offsetTop - box.offsetTop - 8;
  }, [sel, course]);
  return cardsRef;
}

function usePane(course: CourseDetail | null, { flat, cur }: Cards, { activeStem, draft }: Selection) {
  const tabs = useMemo(() => pageTabs(course), [course]);
  const active = activeStem ?? cur?.v.page_stem ?? tabs[0]?.stem ?? null;
  const highlights = useMemo(() => paneHighlights(flat, active, draft), [flat, active, draft]);
  const focusId = draft?.captures.length ? "capture-0" : cur && cur.v.page_stem === active ? valueKey(cur.v) : null;
  return { tabs, active, highlights, focusId };
}

function useVerdicts(cat: string, me: string, role: Role | null, setCourse: Dispatch<SetStateAction<CourseDetail | null>>,
                     { sel, setSel, setDraft, setActiveStem }: Selection) {
  const patch = useCallback((v: CardValue, ev: EventBrief) => {
    setCourse((d) => d && patchCourse(d, v, ev, role));
  }, [role, setCourse]);
  const save = useCallback((v: CardValue, what: Verdict) => saveVerdict({ cat, me, role, v, what, patch, setDraft }),
    [cat, me, role, patch, setDraft]);
  const pick = useCallback((v: CardValue, k: Pick) => {
    if (valueKey(v) !== sel) { setSel(valueKey(v)); setActiveStem(null); }
    if (k === "correct") { void save(v, { verdict: "correct" }); return; }
    setDraft(newDraft(k, v.verdict, v.state));
  }, [sel, save, setSel, setActiveStem, setDraft]);
  return { save, pick };
}

function useVerdictKeys(handleKey: (e: KeyboardEvent) => void) {
  const keys = useRef<(e: KeyboardEvent) => void>(handleKey);
  keys.current = handleKey;
  useEffect(() => {
    const on = (e: KeyboardEvent) => keys.current(e);
    window.addEventListener("keydown", on);
    return () => window.removeEventListener("keydown", on);
  }, []);
}

function handleVerdictKey(e: KeyboardEvent, { flat, cur }: Cards, { draft, setDraft, select }: Selection,
                          { save, pick }: ReturnType<typeof useVerdicts>): void {
  const a = keyAction(e, isField(e.target));
  if (!a || !cur) return;
  if (a === "save") { if (draft) { e.preventDefault(); void save(cur.v, { draft }); } return; }
  if (a === "cancel") { setDraft(null); return; }
  e.preventDefault();
  if (a === "next" || a === "prev") select(valueKey(neighbour(flat, cur, a === "next" ? 1 : -1).v));
  else pick(cur.v, a === "correct" ? "correct" : a === "comment" ? "comment" : "wrong");
}

async function saveVerdict({ cat, me, role, v, what, patch, setDraft }: SaveRequest): Promise<void> {
  const confirming = "verdict" in what && canConfirm(v, role);
  if ("verdict" in what && v.state === "correct" && !confirming) { toast("Already correct"); return; }
  const ev = verdictEvent(me, matchTarget(v), v.verdict, what);
  try {
    const r = await api.annotate(cat, ev);
    patch(v, briefOf(r.event as Parameters<typeof briefOf>[0]));
    setDraft(null);
    toast(savedMessage(ev, v, confirming));
  } catch (e) {
    toast(`Not saved: ${e instanceof Error ? e.message : String(e)}`);
  }
}

function matchTarget(v: CardValue): NewEvent["target"] {
  return { kind: "match", rule_id: v.rule_id, occurrence_key: v.occurrence_key, page_stem: v.page_stem };
}

function savedMessage(ev: NewEvent, v: CardValue, confirming: boolean): string {
  if (ev.type === "comment") return "Comment saved";
  if (ev.verdict === "question") return "Question for the institution saved";
  return `${confirming ? "Confirmed: human-reviewed" : ev.verdict === "correct" ? "Correct saved" : "Wrong saved"} · ${v.property_label ?? v.rule_id}`;
}

function patchCourse(course: CourseDetail, v: CardValue, ev: EventBrief, role: Role | null): CourseDetail {
  return { ...course, occurrences: course.occurrences.map((o) => o.occurrence_key !== v.occurrence_key ? o
    : { ...o, properties: o.properties.map((f) => (f.rule_id === v.rule_id ? applyReview(applyEvent(f, ev), ev, role) : f)) }) };
}

function neighbour(flat: Entry[], cur: Entry, step: number): Entry {
  return flat[Math.max(0, Math.min(flat.length - 1, flat.indexOf(cur) + step))];
}

function pageTabs(course: CourseDetail | null) {
  const seen = new Map<string, { stem: string; url: string; title: string; course: boolean }>();
  for (const o of course?.occurrences ?? []) {
    if (!seen.has(o.page_stem)) seen.set(o.page_stem, { stem: o.page_stem, url: o.url, title: shortTitle(o.page_title ?? o.page_stem), course: false });
    if (o.locator_rule_id === "locator-course-page") seen.get(o.page_stem)!.course = true;
  }
  return [...seen.values()].sort((a, b) => Number(b.course) - Number(a.course)).map((t, i) => ({ stem: t.stem, url: t.url, title: t.title, badge: i + 1 }));
}

function paneHighlights(flat: Entry[], active: string | null, draft: Draft | null): Highlight[] {
  const hs: Highlight[] = flat.filter(({ v }) => v.page_stem === active && v.css_path).map(({ card, v }) => (
    { id: valueKey(v), kind: "value", cssPath: v.css_path!, charStart: v.char_start, charEnd: v.char_end, text: v.value, badge: card.n }));
  draft?.captures.forEach((c, i) => hs.push({ id: `capture-${i}`, kind: "expected", cssPath: c.css_path, charStart: c.char_start,
    charEnd: c.char_end, text: c.text, removable: true }));
  return hs;
}
